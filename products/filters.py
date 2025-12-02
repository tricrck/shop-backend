import django_filters
from .models import Product

class ProductFilter(django_filters.FilterSet):
    min_price = django_filters.NumberFilter(field_name='price', lookup_expr='gte')
    max_price = django_filters.NumberFilter(field_name='price', lookup_expr='lte')
    category = django_filters.CharFilter(field_name='category__slug')
    brand = django_filters.CharFilter(field_name='brand__slug')
    in_stock = django_filters.BooleanFilter(method='filter_in_stock')
    on_sale = django_filters.BooleanFilter(method='filter_on_sale')

    class Meta:
        model = Product
        fields = ['category', 'brand', 'condition', 'is_featured']

    def filter_in_stock(self, queryset, name, value):
        if value:
            return queryset.filter(stock_quantity__gt=0)
        return queryset

    def filter_on_sale(self, queryset, name, value):
        if value:
            return queryset.filter(discount_percentage__gt=0)
        return queryset