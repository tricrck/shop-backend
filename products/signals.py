from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.db.models import Sum
from .models import Product


@receiver(pre_save, sender=Product)
def track_stock_changes(sender, instance, **kwargs):
    """Track if stock_quantity has changed"""
    if instance.pk:
        try:
            old_instance = Product.objects.get(pk=instance.pk)
            instance._stock_changed = old_instance.stock_quantity != instance.stock_quantity
            instance._old_stock = old_instance.stock_quantity
        except Product.DoesNotExist:
            instance._stock_changed = False
    else:
        instance._stock_changed = True
        instance._old_stock = 0


@receiver(post_save, sender=Product)
def sync_warehouse_stock(sender, instance, created, **kwargs):
    """
    Synchronize warehouse stock when product stock_quantity changes.
    
    Distribution Strategy:
    - If product stock increases: Add to primary/first warehouse
    - If product stock decreases: Proportionally reduce from all warehouses
    """
    # Check if stock actually changed
    if not getattr(instance, '_stock_changed', False):
        return
    
    try:
        from inventory.models import WarehouseStock, Warehouse
        
        old_stock = getattr(instance, '_old_stock', 0)
        new_stock = instance.stock_quantity
        stock_diff = new_stock - old_stock
        
        if stock_diff == 0:
            return
        
        # Get all warehouse stocks for this product
        warehouse_stocks = WarehouseStock.objects.filter(product=instance)
        
        if stock_diff > 0:
            # Stock increased - add to primary warehouse or create new entry
            handle_stock_increase(instance, warehouse_stocks, stock_diff)
        else:
            # Stock decreased - proportionally reduce from warehouses
            handle_stock_decrease(instance, warehouse_stocks, abs(stock_diff))
            
    except ImportError:
        # Inventory app not available
        pass


def handle_stock_increase(product, warehouse_stocks, amount):
    """Handle stock increase by adding to primary warehouse"""
    from inventory.models import WarehouseStock, Warehouse
    
    # Try to find a primary warehouse stock entry
    primary_stock = warehouse_stocks.filter(warehouse__is_primary=True).first()
    
    if primary_stock:
        # Add to existing primary warehouse
        primary_stock.quantity += amount
        primary_stock.save(update_fields=['quantity'])
    else:
        # Try to find any existing warehouse stock
        existing_stock = warehouse_stocks.first()
        
        if existing_stock:
            # Add to first available warehouse
            existing_stock.quantity += amount
            existing_stock.save(update_fields=['quantity'])
        else:
            # No warehouse stock exists - find or create primary warehouse
            primary_warehouse = Warehouse.objects.filter(is_primary=True).first()
            
            if not primary_warehouse:
                # Get any active warehouse
                primary_warehouse = Warehouse.objects.filter(is_active=True).first()
            
            if primary_warehouse:
                # Create new warehouse stock entry
                WarehouseStock.objects.create(
                    product=product,
                    warehouse=primary_warehouse,
                    quantity=amount,
                    reserved_quantity=0,
                    damaged_quantity=0
                )


def handle_stock_decrease(product, warehouse_stocks, amount):
    """Handle stock decrease by proportionally reducing from warehouses"""
    if not warehouse_stocks.exists():
        return
    
    # Calculate total available stock across warehouses
    total_warehouse_stock = sum(ws.quantity for ws in warehouse_stocks)
    
    if total_warehouse_stock == 0:
        return
    
    remaining_to_deduct = amount
    
    # Sort by quantity descending to deduct from largest stocks first
    for warehouse_stock in warehouse_stocks.order_by('-quantity'):
        if remaining_to_deduct <= 0:
            break
        
        # Calculate proportional deduction
        if warehouse_stock.quantity > 0:
            deduction = min(warehouse_stock.quantity, remaining_to_deduct)
            warehouse_stock.quantity -= deduction
            warehouse_stock.save(update_fields=['quantity'])
            remaining_to_deduct -= deduction


@receiver(post_save, sender=Product)
def update_product_from_warehouses(sender, instance, created, **kwargs):
    """
    Optional: Sync product stock from warehouse totals.
    This ensures product.stock_quantity always reflects warehouse reality.
    
    Note: This is commented out by default to prevent circular updates.
    Enable only if you want warehouse to be the single source of truth.
    """
    pass
    # Uncomment below if you want warehouses to be the source of truth
    # if not getattr(instance, '_updating_from_warehouse', False):
    #     try:
    #         from inventory.models import WarehouseStock
    #         from django.db.models import Sum
    #         
    #         total = WarehouseStock.objects.filter(product=instance).aggregate(
    #             total=Sum('quantity')
    #         )['total'] or 0
    #         
    #         if total != instance.stock_quantity:
    #             instance._updating_from_warehouse = True
    #             instance.stock_quantity = total
    #             instance.save(update_fields=['stock_quantity'])
    #     except ImportError:
    #         pass