from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.db.models import Sum
from .models import WarehouseStock, StockAlert, StockMovement, InventoryTransfer
from orders.models import Order, OrderItem
from products.models import Product


@receiver(post_save, sender=WarehouseStock)
def check_stock_levels(sender, instance, created, **kwargs):
    """Automatically create alerts for low/out of stock"""
    
    # Out of stock alert
    if instance.quantity == 0:
        StockAlert.objects.get_or_create(
            alert_type='out_of_stock',
            warehouse=instance.warehouse,
            product=instance.product,
            is_resolved=False,
            defaults={
                'priority': 'critical',
                'message': f'{instance.product.name} is out of stock',
                'current_quantity': 0,
                'threshold_quantity': instance.reorder_point
            }
        )
    
    # Low stock alert
    elif instance.quantity <= instance.reorder_point and instance.reorder_point > 0:
        StockAlert.objects.get_or_create(
            alert_type='low_stock',
            warehouse=instance.warehouse,
            product=instance.product,
            is_resolved=False,
            defaults={
                'priority': 'high',
                'message': f'{instance.product.name} is below reorder point',
                'current_quantity': instance.quantity,
                'threshold_quantity': instance.reorder_point
            }
        )
    else:
        # Resolve alerts if stock is replenished
        StockAlert.objects.filter(
            warehouse=instance.warehouse,
            product=instance.product,
            alert_type__in=['low_stock', 'out_of_stock'],
            is_resolved=False
        ).update(is_resolved=True, resolution_notes='Stock replenished automatically')
    
    # Damaged stock alert
    if instance.damaged_quantity > 0:
        existing_alert = StockAlert.objects.filter(
            alert_type='damaged',
            warehouse=instance.warehouse,
            product=instance.product,
            is_resolved=False
        ).first()
        
        if not existing_alert:
            StockAlert.objects.create(
                alert_type='damaged',
                priority='medium',
                warehouse=instance.warehouse,
                product=instance.product,
                message=f'{instance.damaged_quantity} units of {instance.product.name} are damaged',
                current_quantity=instance.damaged_quantity,
                threshold_quantity=0
            )


@receiver(post_save, sender=StockMovement)
def sync_product_total_stock(sender, instance, created, **kwargs):
    """Sync product's total stock across all warehouses"""
    if created:
        product = instance.product
        total_stock = WarehouseStock.objects.filter(
            product=product
        ).aggregate(total=Sum('quantity'))['total'] or 0
        
        product.stock_quantity = total_stock
        product.save(update_fields=['stock_quantity'])


@receiver(post_save, sender=Order)
def handle_order_inventory(sender, instance, created, **kwargs):
    """Reserve or release inventory based on order status"""
    
    # Only process if status changed
    if not created and hasattr(instance, '_previous_status'):
        old_status = instance._previous_status
        new_status = instance.status
        
        # When order is confirmed/processing, reserve stock
        if old_status in ['pending'] and new_status in ['confirmed', 'processing']:
            # Get primary warehouse or first active warehouse
            warehouse = Warehouse.objects.filter(is_primary=True).first() or \
                       Warehouse.objects.filter(is_active=True).first()
            
            if warehouse:
                for item in instance.items.all():
                    try:
                        warehouse_stock = WarehouseStock.objects.get(
                            warehouse=warehouse,
                            product=item.product
                        )
                        warehouse_stock.reserve_stock(item.quantity)
                    except WarehouseStock.DoesNotExist:
                        # Create alert for missing stock
                        StockAlert.objects.create(
                            alert_type='out_of_stock',
                            priority='critical',
                            warehouse=warehouse,
                            product=item.product,
                            message=f'Order {instance.order_number} requires {item.quantity} units but product not in warehouse',
                            current_quantity=0
                        )
        
        # When order is shipped, fulfill reservation (remove from inventory)
        elif old_status in ['confirmed', 'processing', 'ready_to_ship'] and new_status == 'shipped':
            warehouse = Warehouse.objects.filter(is_primary=True).first() or \
                       Warehouse.objects.filter(is_active=True).first()
            
            if warehouse:
                for item in instance.items.all():
                    try:
                        warehouse_stock = WarehouseStock.objects.get(
                            warehouse=warehouse,
                            product=item.product
                        )
                        warehouse_stock.fulfill_reservation(item.quantity)
                        
                        # Create stock movement
                        StockMovement.objects.create(
                            warehouse=warehouse,
                            product=item.product,
                            movement_type='sale',
                            quantity=-item.quantity,
                            quantity_before=warehouse_stock.quantity + item.quantity,
                            quantity_after=warehouse_stock.quantity,
                            reference_type='order',
                            reference_id=str(instance.id),
                            order=instance,
                            notes=f'Fulfilled order {instance.order_number}',
                            created_by=instance.customer.user if instance.customer else None
                        )
                    except WarehouseStock.DoesNotExist:
                        pass
        
        # When order is cancelled, release reservation
        elif new_status in ['cancelled', 'refunded']:
            warehouse = Warehouse.objects.filter(is_primary=True).first() or \
                       Warehouse.objects.filter(is_active=True).first()
            
            if warehouse:
                for item in instance.items.all():
                    try:
                        warehouse_stock = WarehouseStock.objects.get(
                            warehouse=warehouse,
                            product=item.product
                        )
                        warehouse_stock.release_reservation(item.quantity)
                    except WarehouseStock.DoesNotExist:
                        pass


@receiver(pre_save, sender=Order)
def track_order_status_change(sender, instance, **kwargs):
    """Track previous status for signal processing"""
    if instance.pk:
        try:
            previous = Order.objects.get(pk=instance.pk)
            instance._previous_status = previous.status
        except Order.DoesNotExist:
            instance._previous_status = None
    else:
        instance._previous_status = None