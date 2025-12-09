from django.db.models import Sum, F, Q
from .models import Warehouse, WarehouseStock, StockAlert
from products.models import Product


def get_available_stock(product, warehouse=None):
    """Get available stock for a product (total or per warehouse)"""
    if warehouse:
        try:
            stock = WarehouseStock.objects.get(warehouse=warehouse, product=product)
            return stock.available_quantity
        except WarehouseStock.DoesNotExist:
            return 0
    else:
        # Total across all warehouses
        total = WarehouseStock.objects.filter(
            product=product
        ).aggregate(
            available=Sum(F('quantity') - F('reserved_quantity') - F('damaged_quantity'))
        )['available']
        return total or 0


def find_warehouse_with_stock(product, quantity_needed):
    """Find warehouse with sufficient stock for an order"""
    warehouses = WarehouseStock.objects.filter(
        product=product,
        warehouse__is_active=True
    ).annotate(
        available=F('quantity') - F('reserved_quantity') - F('damaged_quantity')
    ).filter(
        available__gte=quantity_needed
    ).order_by('-warehouse__priority')
    
    return warehouses.first().warehouse if warehouses.exists() else None


def split_order_across_warehouses(product, quantity_needed):
    """Split order fulfillment across multiple warehouses"""
    allocation = []
    remaining = quantity_needed
    
    warehouses = WarehouseStock.objects.filter(
        product=product,
        warehouse__is_active=True
    ).annotate(
        available=F('quantity') - F('reserved_quantity') - F('damaged_quantity')
    ).filter(
        available__gt=0
    ).order_by('-warehouse__priority')
    
    for stock in warehouses:
        if remaining <= 0:
            break
        
        allocate = min(stock.available_quantity, remaining)
        allocation.append({
            'warehouse': stock.warehouse,
            'quantity': allocate
        })
        remaining -= allocate
    
    return allocation, remaining == 0


def generate_reorder_report():
    """Generate report of products needing reordering"""
    low_stock = WarehouseStock.objects.filter(
        Q(quantity__lte=F('reorder_point')) & Q(reorder_quantity__gt=0),
        warehouse__is_active=True
    ).select_related('warehouse', 'product', 'product__brand')
    
    report = []
    for stock in low_stock:
        report.append({
            'warehouse': stock.warehouse.name,
            'product': stock.product.name,
            'sku': stock.product.sku,
            'brand': stock.product.brand.name,
            'current_stock': stock.quantity,
            'reorder_point': stock.reorder_point,
            'suggested_order_qty': stock.reorder_quantity,
            'available': stock.available_quantity,
            'reserved': stock.reserved_quantity,
            'cost_per_unit': stock.product.cost_price,
            'total_cost': stock.product.cost_price * stock.reorder_quantity if stock.product.cost_price else 0
        })
    
    return report


def calculate_inventory_turnover(product, days=30):
    """Calculate inventory turnover for a product"""
    from datetime import timedelta
    from django.utils import timezone
    from .models import StockMovement
    
    start_date = timezone.now() - timedelta(days=days)
    
    # Sales movements
    sales = StockMovement.objects.filter(
        product=product,
        movement_type='sale',
        created_at__gte=start_date
    ).aggregate(total=Sum('quantity'))['total'] or 0
    
    # Average inventory
    avg_stock = WarehouseStock.objects.filter(
        product=product
    ).aggregate(avg=Sum('quantity'))['quantity__sum'] or 0
    
    if avg_stock > 0:
        turnover = abs(sales) / avg_stock
        return round(turnover, 2)
    return 0


def reconcile_inventory(warehouse, user):
    """Reconcile system inventory with physical count"""
    from .models import StockCount, StockCountItem
    
    # Create a full count
    stock_count = StockCount.objects.create(
        warehouse=warehouse,
        count_type='full',
        scheduled_date=timezone.now().date(),
        assigned_to=user
    )
    
    # Add all products
    warehouse_stocks = WarehouseStock.objects.filter(warehouse=warehouse)
    for stock in warehouse_stocks:
        StockCountItem.objects.create(
            stock_count=stock_count,
            product=stock.product,
            expected_quantity=stock.quantity
        )
    
    return stock_count