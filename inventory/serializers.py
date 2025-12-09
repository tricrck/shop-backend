from rest_framework import serializers
from .models import (
    Warehouse, WarehouseStock, StockMovement, InventoryTransfer,
    TransferItem, StockAlert, StockCount, StockCountItem
)
from products.models import Product
from products.serializers import ProductListSerializer


class WarehouseSerializer(serializers.ModelSerializer):
    manager_name = serializers.CharField(source='manager.get_full_name', read_only=True)
    total_products = serializers.IntegerField(read_only=True)
    capacity_percentage = serializers.FloatField(read_only=True)
    
    class Meta:
        model = Warehouse
        fields = [
            'id', 'name', 'code', 'address', 'city', 'state', 'country',
            'postal_code', 'phone', 'email', 'manager', 'manager_name',
            'is_active', 'is_primary', 'priority', 'max_capacity',
            'current_capacity', 'capacity_percentage', 'total_products',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'current_capacity']


class WarehouseStockSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    warehouse_code = serializers.CharField(source='warehouse.code', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    product_details = ProductListSerializer(source='product', read_only=True)
    available_quantity = serializers.IntegerField(read_only=True)
    needs_reorder = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = WarehouseStock
        fields = [
            'id', 'warehouse', 'warehouse_name', 'warehouse_code',
            'product', 'product_name', 'product_sku', 'product_details',
            'quantity', 'reserved_quantity', 'damaged_quantity',
            'available_quantity', 'location', 'zone',
            'reorder_point', 'reorder_quantity', 'needs_reorder',
            'last_counted', 'updated_at'
        ]
        read_only_fields = ['updated_at']


class StockMovementSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.get_full_name', read_only=True)
    movement_type_display = serializers.CharField(source='get_movement_type_display', read_only=True)
    
    class Meta:
        model = StockMovement
        fields = [
            'id', 'movement_number', 'warehouse', 'warehouse_name',
            'product', 'product_name', 'product_sku',
            'movement_type', 'movement_type_display',
            'quantity', 'quantity_before', 'quantity_after',
            'unit_cost', 'total_cost',
            'reference_type', 'reference_id', 'order', 'transfer',
            'notes', 'created_by', 'created_by_name',
            'approved_by', 'approved_by_name',
            'created_at', 'movement_date'
        ]
        read_only_fields = ['movement_number', 'created_at']


class StockMovementCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockMovement
        fields = [
            'warehouse', 'product', 'movement_type', 'quantity',
            'unit_cost', 'reference_type', 'reference_id',
            'notes', 'movement_date'
        ]
    
    def validate(self, data):
        warehouse = data.get('warehouse')
        product = data.get('product')
        quantity = data.get('quantity')
        movement_type = data.get('movement_type')
        
        # Check if stock exists
        try:
            warehouse_stock = WarehouseStock.objects.get(
                warehouse=warehouse,
                product=product
            )
        except WarehouseStock.DoesNotExist:
            # Create if doesn't exist (for new products)
            warehouse_stock = WarehouseStock.objects.create(
                warehouse=warehouse,
                product=product,
                quantity=0
            )
        
        # For movements that decrease stock, check available quantity
        if quantity < 0:
            if abs(quantity) > warehouse_stock.available_quantity:
                raise serializers.ValidationError(
                    f"Insufficient stock. Available: {warehouse_stock.available_quantity}"
                )
        
        return data
    
    def create(self, validated_data):
        warehouse = validated_data['warehouse']
        product = validated_data['product']
        quantity = validated_data['quantity']
        
        # Get current stock
        warehouse_stock = WarehouseStock.objects.get(
            warehouse=warehouse,
            product=product
        )
        
        quantity_before = warehouse_stock.quantity
        warehouse_stock.quantity += quantity
        warehouse_stock.save()
        
        # Create movement with quantity tracking
        validated_data['quantity_before'] = quantity_before
        validated_data['quantity_after'] = warehouse_stock.quantity
        validated_data['created_by'] = self.context['request'].user
        
        movement = StockMovement.objects.create(**validated_data)
        
        # Update product's main stock_quantity
        product.stock_quantity = WarehouseStock.objects.filter(
            product=product
        ).aggregate(total=models.Sum('quantity'))['total'] or 0
        product.save()
        
        return movement


class TransferItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    
    class Meta:
        model = TransferItem
        fields = [
            'id', 'product', 'product_name', 'product_sku',
            'quantity', 'received_quantity', 'notes'
        ]


class InventoryTransferSerializer(serializers.ModelSerializer):
    from_warehouse_name = serializers.CharField(source='from_warehouse.name', read_only=True)
    to_warehouse_name = serializers.CharField(source='to_warehouse.name', read_only=True)
    requested_by_name = serializers.CharField(source='requested_by.get_full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    items = TransferItemSerializer(many=True, read_only=True)
    total_items = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = InventoryTransfer
        fields = [
            'id', 'transfer_number', 'from_warehouse', 'from_warehouse_name',
            'to_warehouse', 'to_warehouse_name', 'status', 'status_display',
            'tracking_number', 'items', 'total_items',
            'requested_at', 'shipped_at', 'received_at', 'expected_arrival',
            'requested_by', 'requested_by_name', 'approved_by', 'received_by',
            'notes', 'rejection_reason'
        ]
        read_only_fields = [
            'transfer_number', 'requested_at', 'shipped_at', 
            'received_at', 'requested_by', 'approved_by', 'received_by'
        ]


class InventoryTransferCreateSerializer(serializers.Serializer):
    from_warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    to_warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    items = serializers.ListField(child=serializers.DictField())
    notes = serializers.CharField(required=False, allow_blank=True)
    expected_arrival = serializers.DateTimeField(required=False, allow_null=True)
    
    def validate(self, data):
        if data['from_warehouse'] == data['to_warehouse']:
            raise serializers.ValidationError("Source and destination warehouses must be different")
        
        if not data.get('items'):
            raise serializers.ValidationError("At least one item is required")
        
        # Validate each item
        for item in data['items']:
            if 'product_id' not in item or 'quantity' not in item:
                raise serializers.ValidationError("Each item must have product_id and quantity")
            
            try:
                product = Product.objects.get(id=item['product_id'])
                quantity = int(item['quantity'])
                
                if quantity <= 0:
                    raise serializers.ValidationError("Quantity must be positive")
                
                # Check if source warehouse has enough stock
                try:
                    warehouse_stock = WarehouseStock.objects.get(
                        warehouse=data['from_warehouse'],
                        product=product
                    )
                    if warehouse_stock.available_quantity < quantity:
                        raise serializers.ValidationError(
                            f"Insufficient stock for {product.name}. Available: {warehouse_stock.available_quantity}"
                        )
                except WarehouseStock.DoesNotExist:
                    raise serializers.ValidationError(f"Product {product.name} not found in source warehouse")
                    
            except Product.DoesNotExist:
                raise serializers.ValidationError(f"Product with id {item['product_id']} not found")
            except ValueError:
                raise serializers.ValidationError("Invalid quantity")
        
        return data
    
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        user = self.context['request'].user
        
        # Create transfer
        transfer = InventoryTransfer.objects.create(
            from_warehouse=validated_data['from_warehouse'],
            to_warehouse=validated_data['to_warehouse'],
            notes=validated_data.get('notes', ''),
            expected_arrival=validated_data.get('expected_arrival'),
            requested_by=user
        )
        
        # Create transfer items
        for item_data in items_data:
            product = Product.objects.get(id=item_data['product_id'])
            TransferItem.objects.create(
                transfer=transfer,
                product=product,
                quantity=item_data['quantity'],
                notes=item_data.get('notes', '')
            )
        
        return transfer


class StockAlertSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    alert_type_display = serializers.CharField(source='get_alert_type_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    resolved_by_name = serializers.CharField(source='resolved_by.get_full_name', read_only=True)
    
    class Meta:
        model = StockAlert
        fields = [
            'id', 'alert_type', 'alert_type_display', 'priority', 'priority_display',
            'warehouse', 'warehouse_name', 'product', 'product_name', 'product_sku',
            'message', 'current_quantity', 'threshold_quantity',
            'is_resolved', 'resolved_at', 'resolved_by', 'resolved_by_name',
            'resolution_notes', 'created_at'
        ]
        read_only_fields = ['created_at', 'resolved_at', 'resolved_by']


class StockCountItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    counted_by_name = serializers.CharField(source='counted_by.get_full_name', read_only=True)
    
    class Meta:
        model = StockCountItem
        fields = [
            'id', 'product', 'product_name', 'product_sku',
            'expected_quantity', 'counted_quantity', 'discrepancy',
            'is_counted', 'has_discrepancy', 'notes',
            'counted_by', 'counted_by_name', 'counted_at'
        ]
        read_only_fields = ['discrepancy', 'is_counted', 'has_discrepancy']


class StockCountSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    assigned_to_name = serializers.CharField(source='assigned_to.get_full_name', read_only=True)
    completed_by_name = serializers.CharField(source='completed_by.get_full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    count_type_display = serializers.CharField(source='get_count_type_display', read_only=True)
    items = StockCountItemSerializer(many=True, read_only=True)
    total_items = serializers.IntegerField(read_only=True)
    discrepancy_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = StockCount
        fields = [
            'id', 'count_number', 'warehouse', 'warehouse_name',
            'count_type', 'count_type_display', 'status', 'status_display',
            'scheduled_date', 'started_at', 'completed_at',
            'assigned_to', 'assigned_to_name', 'completed_by', 'completed_by_name',
            'notes', 'items', 'total_items', 'discrepancy_count',
            'created_at'
        ]
        read_only_fields = ['count_number', 'started_at', 'completed_at', 'completed_by', 'created_at']


class StockCountCreateSerializer(serializers.Serializer):
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    count_type = serializers.ChoiceField(choices=StockCount.COUNT_TYPES)
    scheduled_date = serializers.DateField()
    assigned_to = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    notes = serializers.CharField(required=False, allow_blank=True)
    products = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text="List of product IDs to count. If empty, counts all products in warehouse."
    )
    
    def create(self, validated_data):
        products_ids = validated_data.pop('products', [])
        
        # Create stock count
        stock_count = StockCount.objects.create(**validated_data)
        
        # Add items
        if products_ids:
            # Count specific products
            warehouse_stocks = WarehouseStock.objects.filter(
                warehouse=validated_data['warehouse'],
                product_id__in=products_ids
            )
        else:
            # Count all products in warehouse
            warehouse_stocks = WarehouseStock.objects.filter(
                warehouse=validated_data['warehouse']
            )
        
        for warehouse_stock in warehouse_stocks:
            StockCountItem.objects.create(
                stock_count=stock_count,
                product=warehouse_stock.product,
                expected_quantity=warehouse_stock.quantity
            )
        
        return stock_count


# Bulk Operations Serializers
class BulkStockUpdateSerializer(serializers.Serializer):
    updates = serializers.ListField(child=serializers.DictField())
    
    def validate_updates(self, value):
        for update in value:
            if 'product_id' not in update or 'warehouse_id' not in update or 'quantity' not in update:
                raise serializers.ValidationError(
                    "Each update must have product_id, warehouse_id, and quantity"
                )
        return value