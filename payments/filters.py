class MpesaTransactionFilter(filters.FilterSet):
    """Filter for M-Pesa transactions"""
    
    status = filters.MultipleChoiceFilter(
        choices=MpesaTransaction.STATUS_CHOICES
    )
    transaction_type = filters.MultipleChoiceFilter(
        choices=MpesaTransaction.TRANSACTION_TYPE_CHOICES
    )
    amount_min = filters.NumberFilter(field_name='amount', lookup_expr='gte')
    amount_max = filters.NumberFilter(field_name='amount', lookup_expr='lte')
    phone_number = filters.CharFilter(lookup_expr='icontains')
    order = filters.NumberFilter(field_name='order__id')
    customer = filters.NumberFilter(field_name='customer__id')
    date_from = filters.DateTimeFilter(field_name='initiated_at', lookup_expr='gte')
    date_to = filters.DateTimeFilter(field_name='initiated_at', lookup_expr='lte')
    is_successful = filters.BooleanFilter(method='filter_successful')
    
    class Meta:
        model = MpesaTransaction
        fields = [
            'status', 'transaction_type', 'amount_min', 'amount_max',
            'phone_number', 'order', 'customer', 'date_from', 'date_to',
            'is_successful'
        ]
    
    def filter_successful(self, queryset, name, value):
        if value:
            return queryset.filter(status='completed', result_code=0)
        return queryset.exclude(status='completed', result_code=0)


class MpesaCallbackFilter(filters.FilterSet):
    """Filter for M-Pesa callbacks"""
    
    callback_type = filters.ChoiceFilter(
        choices=MpesaCallback.CALLBACK_TYPE_CHOICES
    )
    is_processed = filters.BooleanFilter()
    date_from = filters.DateTimeFilter(field_name='received_at', lookup_expr='gte')
    date_to = filters.DateTimeFilter(field_name='received_at', lookup_expr='lte')
    
    class Meta:
        model = MpesaCallback
        fields = ['callback_type', 'is_processed', 'date_from', 'date_to']
