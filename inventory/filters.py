from django_filters import rest_framework as filters
from .models import WarehouseStock, StockMovement, InventoryTransfer, StockAlert


class WarehouseStockFilter(filters.FilterSet):
    warehouse = filters.NumberFilter(field_name='warehouse__id')
    product = filters.NumberFilter(field_name='product__id')
    low_stock = filters.BooleanFilter(method='filter_low_stock')
    out_of_stock = filters.BooleanFilter(method='filter_out_of_stock')
    needs_reorder = filters.BooleanFilter(method='filter_needs_reorder')
    category = filters.NumberFilter(field_name='product__category__id')
    brand = filters.NumberFilter(field_name='product__brand__id')
    zone = filters.CharFilter(field_name='zone', lookup_expr='icontains')
    
    class Meta:
        model = WarehouseStock
        fields = ['warehouse', 'product', 'zone']
    
    def filter_low_stock(self, queryset, name, value):
        if value:
            return queryset.filter(quantity__lte=F('reorder_point'), quantity__gt=0)
        return queryset
    
    def filter_out_of_stock(self, queryset, name, value):
        if value:
            return queryset.filter(quantity=0)
        return queryset
    
    def filter_needs_reorder(self, queryset, name, value):
        if value:
            return queryset.filter(
                quantity__lte=F('reorder_point'),
                reorder_quantity__gt=0
            )
        return queryset


class StockMovementFilter(filters.FilterSet):
    warehouse = filters.NumberFilter(field_name='warehouse__id')
    product = filters.NumberFilter(field_name='product__id')
    movement_type = filters.MultipleChoiceFilter(choices=StockMovement.MOVEMENT_TYPES)
    date_from = filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    date_to = filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    created_by = filters.NumberFilter(field_name='created_by__id')
    reference_type = filters.CharFilter()
    has_cost = filters.BooleanFilter(method='filter_has_cost')
    
    class Meta:
        model = StockMovement
        fields = ['warehouse', 'product', 'movement_type', 'created_by']
    
    def filter_has_cost(self, queryset, name, value):
        if value:
            return queryset.exclude(unit_cost__isnull=True)
        return queryset.filter(unit_cost__isnull=True)


class InventoryTransferFilter(filters.FilterSet):
    from_warehouse = filters.NumberFilter(field_name='from_warehouse__id')
    to_warehouse = filters.NumberFilter(field_name='to_warehouse__id')
    status = filters.MultipleChoiceFilter(choices=InventoryTransfer.TRANSFER_STATUS)
    requested_by = filters.NumberFilter(field_name='requested_by__id')
    date_from = filters.DateTimeFilter(field_name='requested_at', lookup_expr='gte')
    date_to = filters.DateTimeFilter(field_name='requested_at', lookup_expr='lte')
    pending_approval = filters.BooleanFilter(method='filter_pending_approval')
    in_transit = filters.BooleanFilter(method='filter_in_transit')
    
    class Meta:
        model = InventoryTransfer
        fields = ['from_warehouse', 'to_warehouse', 'status']
    
    def filter_pending_approval(self, queryset, name, value):
        if value:
            return queryset.filter(status='draft')
        return queryset
    
    def filter_in_transit(self, queryset, name, value):
        if value:
            return queryset.filter(status='in_transit')
        return queryset


class StockAlertFilter(filters.FilterSet):
    warehouse = filters.NumberFilter(field_name='warehouse__id')
    product = filters.NumberFilter(field_name='product__id')
    alert_type = filters.MultipleChoiceFilter(choices=StockAlert.ALERT_TYPES)
    priority = filters.MultipleChoiceFilter(choices=StockAlert.ALERT_PRIORITY)
    is_resolved = filters.BooleanFilter()
    date_from = filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    date_to = filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    unresolved = filters.BooleanFilter(method='filter_unresolved')
    critical = filters.BooleanFilter(method='filter_critical')
    
    class Meta:
        model = StockAlert
        fields = ['warehouse', 'product', 'alert_type', 'priority', 'is_resolved']
    
    def filter_unresolved(self, queryset, name, value):
        if value:
            return queryset.filter(is_resolved=False)
        return queryset
    
    def filter_critical(self, queryset, name, value):
        if value:
            return queryset.filter(priority='critical', is_resolved=False)
        return queryset
