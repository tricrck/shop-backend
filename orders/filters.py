from django_filters import rest_framework as filters
from .models import Order, OrderReturn, ShippingMethod
from django.db.models import Q
import django_filters


class OrderFilter(filters.FilterSet):
    order_number = filters.CharFilter(field_name='order_number', lookup_expr='icontains')
    customer_email = filters.CharFilter(field_name='customer__user__email', lookup_expr='icontains')
    customer_name = filters.CharFilter(method='filter_customer_name')
    status = filters.MultipleChoiceFilter(choices=Order.ORDER_STATUS)
    payment_status = filters.MultipleChoiceFilter(choices=Order.PAYMENT_STATUS)
    payment_method = filters.MultipleChoiceFilter(choices=Order.PAYMENT_METHODS)
    date_range = filters.DateFromToRangeFilter(field_name='created_at')
    total_min = filters.NumberFilter(field_name='total', lookup_expr='gte')
    total_max = filters.NumberFilter(field_name='total', lookup_expr='lte')
    has_tracking = filters.BooleanFilter(method='filter_has_tracking')
    is_guest = filters.BooleanFilter(field_name='is_guest')
    is_gift = filters.BooleanFilter(field_name='is_gift')
    is_digital = filters.BooleanFilter(field_name='is_digital')
    
    class Meta:
        model = Order
        fields = [
            'order_number',
            'status',
            'payment_status',
            'payment_method',
            'date_range',
            'total_min',
            'total_max',
        ]
    
    def filter_customer_name(self, queryset, name, value):
        return queryset.filter(
            Q(customer__user__first_name__icontains=value) |
            Q(customer__user__last_name__icontains=value)
        )
    
    def filter_has_tracking(self, queryset, name, value):
        if value:
            return queryset.exclude(tracking_number='')
        return queryset.filter(tracking_number='')


class OrderReturnFilter(filters.FilterSet):
    return_number = filters.CharFilter(field_name='return_number', lookup_expr='icontains')
    order_number = filters.CharFilter(field_name='order__order_number', lookup_expr='icontains')
    status = filters.MultipleChoiceFilter(choices=OrderReturn.RETURN_STATUS)
    reason = filters.MultipleChoiceFilter(choices=OrderReturn.RETURN_REASONS)
    date_range = filters.DateFromToRangeFilter(field_name='requested_at')
    
    class Meta:
        model = OrderReturn
        fields = ['return_number', 'status', 'reason', 'date_range']


class ShippingMethodFilter(filters.FilterSet):
    name = filters.CharFilter(lookup_expr='icontains')
    carrier = filters.CharFilter(lookup_expr='icontains')
    is_active = filters.BooleanFilter()
    cost_min = filters.NumberFilter(field_name='cost', lookup_expr='gte')
    cost_max = filters.NumberFilter(field_name='cost', lookup_expr='lte')
    has_free_threshold = filters.BooleanFilter(method='filter_has_free_threshold')
    
    class Meta:
        model = ShippingMethod  # <- Fixed: Should be ShippingMethod
        fields = ['name', 'carrier', 'is_active']
    
    def filter_has_free_threshold(self, queryset, name, value):
        if value:
            return queryset.exclude(free_shipping_threshold__isnull=True)
        return queryset.filter(free_shipping_threshold__isnull=True)