from rest_framework import serializers
from django.contrib.auth.models import User
from decimal import Decimal
from .models import (
    Order, OrderItem, OrderStatusHistory, ShippingMethod, 
    OrderReturn, ReturnItem, OrderNote
)
from customers.serializers import AddressSerializer, CustomerSerializer
from products.serializers import ProductListSerializer
from products.models import Product
from customers.models import Address
import uuid


class OrderItemSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True), 
        write_only=True,
        source='product'
    )
    variant_details = serializers.SerializerMethodField()
    can_download = serializers.BooleanField(read_only=True)
    download_count = serializers.IntegerField(read_only=True)
    download_limit = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = OrderItem
        fields = [
            'id', 'product', 'product_id', 'variant', 'variant_details',
            'quantity', 'price', 'original_price', 'discount', 'tax_rate', 'total',
            'digital_file', 'download_key', 'download_limit', 'download_count',
            'can_download', 'is_digital', 'created_at'
        ]
        read_only_fields = [
            'id', 'product', 'variant_details', 'price', 'original_price', 
            'total', 'can_download', 'is_digital', 'created_at'
        ]
    
    def get_variant_details(self, obj):
        """Get human-readable variant details"""
        if obj.variant:
            details = []
            for key, value in obj.variant.items():
                details.append(f"{key.title()}: {value}")
            return ", ".join(details)
        return ""


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = OrderStatusHistory
        fields = ['id', 'old_status', 'new_status', 'changed_by', 
                 'changed_by_name', 'notes', 'ip_address', 'created_at']
        read_only_fields = fields
    
    def get_changed_by_name(self, obj):
        if obj.changed_by:
            return obj.changed_by.get_full_name() or obj.changed_by.username
        return "System"


class ShippingMethodSerializer(serializers.ModelSerializer):
    estimated_delivery_text = serializers.SerializerMethodField()
    
    class Meta:
        model = ShippingMethod
        fields = [
            'id', 'name', 'carrier', 'code', 'description', 'cost',
            'free_shipping_threshold', 'is_active', 'estimated_days_min',
            'estimated_days_max', 'estimated_delivery_text', 'max_weight',
            'allowed_countries', 'created_at', 'updated_at'
        ]
    
    def get_estimated_delivery_text(self, obj):
        if obj.estimated_days_min == obj.estimated_days_max:
            return f"{obj.estimated_days_min} business days"
        return f"{obj.estimated_days_min}-{obj.estimated_days_max} business days"


class OrderNoteSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    
    class Meta:
        model = OrderNote
        fields = ['id', 'user', 'user_name', 'note', 
                 'is_customer_visible', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'user_name', 'created_at', 'updated_at']
    
    def get_user_name(self, obj):
        if obj.user:
            return obj.user.get_full_name() or obj.user.username
        return "System"
    
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class OrderListSerializer(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()
    customer_email = serializers.SerializerMethodField()
    items_count = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)
    shipping_address_summary = serializers.SerializerMethodField()
    
    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'customer', 'customer_name', 'customer_email',
            'status', 'status_display', 'payment_status', 'payment_status_display',
            'subtotal', 'tax_amount', 'shipping_cost', 'discount_amount', 'total',
            'currency', 'items_count', 'shipping_address_summary',
            'tracking_number', 'carrier', 'estimated_delivery',
            'created_at', 'updated_at'
        ]
        read_only_fields = fields
    
    def get_customer_name(self, obj):
        if obj.customer:
            return f"{obj.customer.user.first_name} {obj.customer.user.last_name}"
        return "Guest"
    
    def get_customer_email(self, obj):
        if obj.customer:
            return obj.customer.user.email
        return obj.guest_email or ""
    
    def get_items_count(self, obj):
        return obj.items.count()
    
    def get_shipping_address_summary(self, obj):
        if obj.shipping_address:
            addr = obj.shipping_address
            return f"{addr.city}, {addr.state}, {addr.country}"
        return ""


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    notes = OrderNoteSerializer(many=True, read_only=True)
    billing_address = AddressSerializer(read_only=True)
    shipping_address = AddressSerializer(read_only=True)
    customer_details = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    is_cancellable = serializers.BooleanField(read_only=True)
    days_since_ordered = serializers.IntegerField(read_only=True)
    weight_total = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    
    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'customer', 'customer_details',
            'status', 'status_display', 'payment_status', 'payment_status_display',
            'payment_method', 'payment_method_display', 'payment_id', 'mpesa_checkout_request_id',
            'mpesa_transaction_id',
            
            # Addresses
            'billing_address', 'shipping_address',
            
            # Pricing
            'subtotal', 'tax_amount', 'tax_rate', 'shipping_cost', 
            'discount_amount', 'discount_code', 'total', 'currency',
            
            # Shipping
            'shipping_method', 'tracking_number', 'tracking_url', 'carrier',
            'estimated_delivery', 'shipped_date', 'delivered_date',
            'requires_shipping',
            
            # Items
            'items', 'weight_total',
            
            # Customer info
            'customer_notes', 'is_gift', 'gift_message',
            'is_digital', 'is_recurring', 'is_guest',
            'guest_email', 'guest_phone',
            
            # Audit
            'ip_address', 'user_agent',
            
            # History & Notes
            'status_history', 'notes',
            
            # Flags
            'is_cancellable', 'days_since_ordered',
            
            # Timestamps
            'created_at', 'updated_at', 'paid_at', 'cancelled_at', 'refunded_at',
        ]
        read_only_fields = fields
    
    def get_customer_details(self, obj):
        if obj.is_guest:
            return {
                'email': obj.guest_email,
                'phone': obj.guest_phone,
                'is_guest': True
            }
        if obj.customer:
            return {
                'id': obj.customer.id,
                'email': obj.customer.user.email,
                'first_name': obj.customer.user.first_name,
                'last_name': obj.customer.user.last_name,
                'phone': obj.customer.phone,
                'is_guest': False
            }
        return None


class OrderCreateSerializer(serializers.ModelSerializer):
    items = serializers.JSONField(write_only=True)
    shipping_method_id = serializers.PrimaryKeyRelatedField(
        queryset=ShippingMethod.objects.filter(is_active=True),
        write_only=True,
        required=False
    )
    use_default_address = serializers.BooleanField(write_only=True, default=True)
    billing_address_id = serializers.PrimaryKeyRelatedField(
        queryset=Address.objects.all(),
        write_only=True,
        required=False,
        allow_null=True
    )
    shipping_address_id = serializers.PrimaryKeyRelatedField(
        queryset=Address.objects.all(),
        write_only=True,
        required=False,
        allow_null=True
    )
    
    class Meta:
        model = Order
        fields = [
            'items', 'shipping_method_id', 'use_default_address',
            'billing_address_id', 'shipping_address_id',
            'customer_notes', 'is_gift', 'gift_message',
            'payment_method', 'discount_code'
        ]
    
    def validate_items(self, value):
        if not value or not isinstance(value, list):
            raise serializers.ValidationError("Items must be a non-empty list")
        
        validated_items = []
        
        for item in value:
            if 'product_id' not in item or 'quantity' not in item:
                raise serializers.ValidationError("Each item must have product_id and quantity")
            
            if item['quantity'] < 1:
                raise serializers.ValidationError("Quantity must be at least 1")
            
            try:
                product = Product.objects.get(id=item['product_id'], is_active=True)
            except Product.DoesNotExist:
                raise serializers.ValidationError(
                    f"Product with id {item['product_id']} does not exist or is not active"
                )
            
            # Check stock
            if product.stock_quantity < item['quantity']:
                raise serializers.ValidationError(
                    f"Insufficient stock for {product.name}. Available: {product.stock_quantity}"
                )
            
            validated_items.append({
                'product': product,
                'quantity': item['quantity'],
                'variant': item.get('variant', {})
            })
        
        return validated_items
    
    def create(self, validated_data):
        request = self.context['request']
        items_data = validated_data.pop('items')
        shipping_method = validated_data.pop('shipping_method_id', None)
        use_default_address = validated_data.pop('use_default_address', True)
        
        # Get customer
        customer = None
        if request.user.is_authenticated:
            try:
                customer = request.user.customer
            except:
                raise serializers.ValidationError("User does not have a customer profile")
        
        # Get addresses - IMPROVED LOGIC
        billing_address = None
        shipping_address = None
        
        if customer and use_default_address:
            # Try to get default addresses first
            billing_address = customer.addresses.filter(
                address_type='billing', is_default=True
            ).first()
            shipping_address = customer.addresses.filter(
                address_type='shipping', is_default=True
            ).first()
            
            # If no billing address, try to use any address
            if not billing_address:
                billing_address = customer.addresses.filter(is_default=True).first()
            
            # If no shipping address, try to use any address
            if not shipping_address:
                shipping_address = customer.addresses.filter(is_default=True).first()
        else:
            # Use provided address IDs
            billing_address_id = validated_data.pop('billing_address_id', None)
            shipping_address_id = validated_data.pop('shipping_address_id', None)
            
            if billing_address_id:
                billing_address = billing_address_id
            if shipping_address_id:
                shipping_address = shipping_address_id
            
            # If only one address provided, use it for both
            if billing_address and not shipping_address:
                shipping_address = billing_address
            elif shipping_address and not billing_address:
                billing_address = shipping_address
        
        # Final validation - addresses must exist
        if not billing_address:
            raise serializers.ValidationError({
                "billing_address": "Billing address is required. Please add an address to your profile."
            })
        if not shipping_address:
            raise serializers.ValidationError({
                "shipping_address": "Shipping address is required. Please add an address to your profile."
            })
        
        # Calculate totals
        subtotal = Decimal('0')
        
        for item_data in items_data:
            product = item_data['product']
            quantity = item_data['quantity']
            price = product.final_price
            subtotal += price * quantity
        
        # Calculate shipping
        shipping_cost = Decimal('0')
        shipping_name = ''
        carrier_name = ''
        
        if shipping_method:
            shipping_cost = shipping_method.cost
            shipping_name = shipping_method.name
            carrier_name = shipping_method.carrier
            
            # Check for free shipping threshold
            if (shipping_method.free_shipping_threshold and 
                subtotal >= shipping_method.free_shipping_threshold):
                shipping_cost = Decimal('0')
        
        # Calculate tax
        tax_rate = Decimal('10.0')
        tax_amount = subtotal * (tax_rate / 100)
        
        # Calculate total
        total = subtotal + tax_amount + shipping_cost
        
        # Apply discount if any
        discount_amount = Decimal('0')
        if validated_data.get('discount_code'):
            # TODO: Implement discount code logic
            pass
        
        total -= discount_amount
        
        # Create order
        order = Order.objects.create(
            customer=customer,
            billing_address=billing_address,
            shipping_address=shipping_address,
            subtotal=subtotal,
            tax_amount=tax_amount,
            tax_rate=tax_rate,
            shipping_cost=shipping_cost,
            discount_amount=discount_amount,
            total=total,
            shipping_method=shipping_name,
            carrier=carrier_name,
            payment_method=validated_data.get('payment_method', ''),
            customer_notes=validated_data.get('customer_notes', ''),
            is_gift=validated_data.get('is_gift', False),
            gift_message=validated_data.get('gift_message', ''),
            discount_code=validated_data.get('discount_code', ''),
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            is_guest=not request.user.is_authenticated,
            guest_email=request.data.get('email', '') if not request.user.is_authenticated else '',
            guest_phone=request.data.get('phone', '') if not request.user.is_authenticated else '',
        )
        
        # Create order items and update stock
        for item_data in items_data:
            product = item_data['product']
            quantity = item_data['quantity']
            variant = item_data.get('variant', {})
            price = product.final_price
            
            OrderItem.objects.create(
                order=order,
                product=product,
                variant=variant,
                quantity=quantity,
                price=price,
                original_price=product.price,
                discount=product.price - price if product.discount_percentage > 0 else Decimal('0'),
                tax_rate=tax_rate,
            )
            
            # Update product stock
            product.stock_quantity -= quantity
            product.save()
        
        # Create initial status history
        OrderStatusHistory.objects.create(
            order=order,
            old_status='',
            new_status='pending',
            changed_by=request.user if request.user.is_authenticated else None,
            ip_address=request.META.get('REMOTE_ADDR'),
            notes='Order created'
        )
        
        return order


class OrderUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = [
            'status', 'payment_status', 'tracking_number', 'tracking_url',
            'carrier', 'shipped_date', 'delivered_date', 'admin_notes'
        ]
        read_only_fields = ['order_number', 'customer', 'total']


class OrderCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False)
    refund_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    restock_items = serializers.BooleanField(default=True)
    
    def validate(self, data):
        order = self.context['order']
        
        if not order.is_cancellable:
            raise serializers.ValidationError("This order cannot be cancelled.")
        
        if data.get('refund_amount') and data['refund_amount'] > order.total:
            raise serializers.ValidationError("Refund amount cannot exceed order total.")
        
        return data


# Return Serializers
class ReturnItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='order_item.product.name', read_only=True)
    
    class Meta:
        model = ReturnItem
        fields = ['id', 'order_item', 'product_name', 'quantity', 
                 'condition', 'refund_amount', 'notes']


class OrderReturnSerializer(serializers.ModelSerializer):
    items = ReturnItemSerializer(many=True, read_only=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    customer_email = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    reason_display = serializers.CharField(source='get_reason_display', read_only=True)
    
    class Meta:
        model = OrderReturn
        fields = [
            'id', 'return_number', 'order', 'order_number', 'customer_email',
            'status', 'status_display', 'reason', 'reason_display', 'reason_details',
            'items', 'return_shipping_label', 'return_tracking', 'return_carrier',
            'refund_amount', 'refund_method', 'refund_id', 'refunded_at',
            'notes', 'restocking_fee', 'requested_at', 'approved_at',
            'received_at', 'completed_at'
        ]
        read_only_fields = ['id', 'return_number', 'order', 'order_number', 
                           'customer_email', 'requested_at']
    
    def get_customer_email(self, obj):
        if obj.order.customer:
            return obj.order.customer.user.email
        return obj.order.guest_email or ""


class ReturnCreateSerializer(serializers.Serializer):
    order_id = serializers.PrimaryKeyRelatedField(queryset=Order.objects.filter(status='delivered'))
    reason = serializers.ChoiceField(choices=OrderReturn.RETURN_REASONS)
    reason_details = serializers.CharField(required=False)
    items = serializers.JSONField()
    
    def validate_items(self, value):
        if not value or not isinstance(value, list):
            raise serializers.ValidationError("Items must be a non-empty list")
        
        for item in value:
            if 'order_item_id' not in item or 'quantity' not in item or 'condition' not in item:
                raise serializers.ValidationError(
                    "Each item must have order_item_id, quantity, and condition"
                )
        
        return value
    
    def validate(self, data):
        order = data['order_id']
        
        from django.utils import timezone
        if not order.delivered_date:
            raise serializers.ValidationError("Order has not been delivered yet")
        
        days_since_delivery = (timezone.now() - order.delivered_date).days
        if days_since_delivery > 30:
            raise serializers.ValidationError("Return window (30 days) has expired")
        
        return data


class ShippingQuoteSerializer(serializers.Serializer):
    shipping_method_id = serializers.PrimaryKeyRelatedField(
        queryset=ShippingMethod.objects.filter(is_active=True)
    )
    items = serializers.JSONField()
    country = serializers.CharField(max_length=100)
    postal_code = serializers.CharField(max_length=20)
    
    def validate_items(self, value):
        if not value or not isinstance(value, list):
            raise serializers.ValidationError("Items must be a non-empty list")
        
        for item in value:
            if 'product_id' not in item or 'quantity' not in item:
                raise serializers.ValidationError("Each item must have product_id and quantity")
        
        return value