from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import (
    MpesaConfiguration, MpesaTransaction, MpesaCallback,
    MpesaRefund, MpesaWebhookLog, MpesaPaymentMethod, MpesaAccessToken
)


@admin.register(MpesaConfiguration)
class MpesaConfigurationAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'environment', 'business_short_code',
        'is_active', 'is_default', 'created_at'
    ]
    list_filter = ['environment', 'is_active', 'is_default']
    search_fields = ['name', 'business_short_code']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'environment', 'is_active', 'is_default')
        }),
        ('API Credentials', {
            'fields': ('consumer_key', 'consumer_secret', 'business_short_code', 'passkey'),
            'classes': ('collapse',)
        }),
        ('Endpoints', {
            'fields': ('api_base_url', 'callback_url', 'timeout_url')
        }),
        ('Settings', {
            'fields': ('max_requests_per_minute',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    actions = ['set_as_default', 'activate', 'deactivate']
    
    def set_as_default(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(request, "Please select only one configuration", level='error')
            return
        
        MpesaConfiguration.objects.update(is_default=False)
        queryset.update(is_default=True)
        self.message_user(request, "Configuration set as default")
    set_as_default.short_description = "Set as default configuration"
    
    def activate(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, f"{queryset.count()} configurations activated")
    activate.short_description = "Activate selected configurations"
    
    def deactivate(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, f"{queryset.count()} configurations deactivated")
    deactivate.short_description = "Deactivate selected configurations"


@admin.register(MpesaTransaction)
class MpesaTransactionAdmin(admin.ModelAdmin):
    list_display = [
        'transaction_id_short', 'transaction_type', 'status_badge',
        'phone_number', 'amount', 'order_link', 'initiated_at'
    ]
    list_filter = [
        'status', 'transaction_type', 'result_code',
        'initiated_at', 'completed_at'
    ]
    search_fields = [
        'transaction_id', 'checkout_request_id', 'merchant_request_id',
        'mpesa_receipt_number', 'phone_number', 'account_reference'
    ]
    readonly_fields = [
        'transaction_id', 'merchant_request_id', 'checkout_request_id',
        'mpesa_receipt_number', 'request_payload_display', 'response_payload_display',
        'callback_payload_display', 'initiated_at', 'completed_at', 'failed_at', 'updated_at'
    ]
    
    fieldsets = (
        ('Transaction Information', {
            'fields': (
                'transaction_id', 'transaction_type', 'status',
                'merchant_request_id', 'checkout_request_id', 'mpesa_receipt_number'
            )
        }),
        ('Payment Details', {
            'fields': (
                'phone_number', 'amount', 'account_reference',
                'transaction_desc', 'transaction_date'
            )
        }),
        ('Related Records', {
            'fields': ('order', 'customer', 'configuration')
        }),
        ('Result', {
            'fields': ('result_code', 'result_desc', 'balance'),
            'classes': ('collapse',)
        }),
        ('Retry Information', {
            'fields': ('retry_count', 'max_retries', 'last_retry_at'),
            'classes': ('collapse',)
        }),
        ('Request/Response Data', {
            'fields': (
                'request_payload_display', 'response_payload_display',
                'callback_payload_display'
            ),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('ip_address', 'user_agent'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('initiated_at', 'completed_at', 'failed_at', 'updated_at')
        })
    )
    
    actions = ['mark_as_completed', 'mark_as_failed', 'retry_transaction']
    
    def transaction_id_short(self, obj):
        return str(obj.transaction_id)[:8] + '...'
    transaction_id_short.short_description = 'Transaction ID'
    
    def status_badge(self, obj):
        colors = {
            'completed': 'green',
            'processing': 'blue',
            'pending': 'orange',
            'failed': 'red',
            'cancelled': 'gray',
            'timeout': 'darkred',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def order_link(self, obj):
        if obj.order:
            url = reverse('admin:orders_order_change', args=[obj.order.id])
            return format_html('<a href="{}">{}</a>', url, obj.order.order_number)
        return '-'
    order_link.short_description = 'Order'
    
    def request_payload_display(self, obj):
        import json
        if obj.request_payload:
            formatted = json.dumps(obj.request_payload, indent=2)
            return mark_safe(f'<pre>{formatted}</pre>')
        return '-'
    request_payload_display.short_description = 'Request Payload'
    
    def response_payload_display(self, obj):
        import json
        if obj.response_payload:
            formatted = json.dumps(obj.response_payload, indent=2)
            return mark_safe(f'<pre>{formatted}</pre>')
        return '-'
    response_payload_display.short_description = 'Response Payload'
    
    def callback_payload_display(self, obj):
        import json
        if obj.callback_payload:
            formatted = json.dumps(obj.callback_payload, indent=2)
            return mark_safe(f'<pre>{formatted}</pre>')
        return '-'
    callback_payload_display.short_description = 'Callback Payload'
    
    def mark_as_completed(self, request, queryset):
        count = queryset.filter(status='processing').update(status='completed')
        self.message_user(request, f"{count} transactions marked as completed")
    mark_as_completed.short_description = "Mark as completed"
    
    def mark_as_failed(self, request, queryset):
        from django.utils import timezone
        count = queryset.filter(status='processing').update(
            status='failed',
            failed_at=timezone.now()
        )
        self.message_user(request, f"{count} transactions marked as failed")
    mark_as_failed.short_description = "Mark as failed"


@admin.register(MpesaCallback)
class MpesaCallbackAdmin(admin.ModelAdmin):
    list_display = [
        'callback_id_short', 'callback_type', 'checkout_request_id',
        'is_processed', 'transaction_link', 'received_at'
    ]
    list_filter = ['callback_type', 'is_processed', 'received_at']
    search_fields = ['callback_id', 'checkout_request_id', 'merchant_request_id']
    readonly_fields = [
        'callback_id', 'raw_payload_display', 'received_at',
        'processed_at', 'ip_address'
    ]
    
    def callback_id_short(self, obj):
        return str(obj.callback_id)[:8] + '...'
    callback_id_short.short_description = 'Callback ID'
    
    def transaction_link(self, obj):
        if obj.transaction:
            url = reverse('admin:payments_mpesatransaction_change', args=[obj.transaction.id])
            return format_html('<a href="{}">View Transaction</a>', url)
        return '-'
    transaction_link.short_description = 'Transaction'
    
    def raw_payload_display(self, obj):
        import json
        if obj.raw_payload:
            formatted = json.dumps(obj.raw_payload, indent=2)
            return mark_safe(f'<pre>{formatted}</pre>')
        return '-'
    raw_payload_display.short_description = 'Raw Payload'


@admin.register(MpesaRefund)
class MpesaRefundAdmin(admin.ModelAdmin):
    list_display = [
        'refund_id_short', 'amount', 'status_badge',
        'original_transaction_link', 'initiated_at', 'completed_at'
    ]
    list_filter = ['status', 'initiated_at', 'completed_at']
    search_fields = ['refund_id', 'reversal_id', 'reason']
    readonly_fields = [
        'refund_id', 'initiated_at', 'completed_at',
        'result_code', 'result_desc', 'reversal_id'
    ]
    
    def refund_id_short(self, obj):
        return str(obj.refund_id)[:8] + '...'
    refund_id_short.short_description = 'Refund ID'
    
    def status_badge(self, obj):
        colors = {
            'completed': 'green',
            'processing': 'blue',
            'pending': 'orange',
            'failed': 'red',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def original_transaction_link(self, obj):
        url = reverse('admin:payments_mpesatransaction_change', 
                     args=[obj.original_transaction.id])
        return format_html('<a href="{}">View Transaction</a>', url)
    original_transaction_link.short_description = 'Original Transaction'


@admin.register(MpesaWebhookLog)
class MpesaWebhookLogAdmin(admin.ModelAdmin):
    list_display = [
        'webhook_id_short', 'endpoint', 'method',
        'status_code', 'is_valid', 'received_at'
    ]
    list_filter = ['method', 'is_valid', 'status_code', 'received_at']
    search_fields = ['webhook_id', 'endpoint']
    readonly_fields = [
        'webhook_id', 'headers_display', 'body_display',
        'response_body_display', 'received_at'
    ]
    
    def webhook_id_short(self, obj):
        return str(obj.webhook_id)[:8] + '...'
    webhook_id_short.short_description = 'Webhook ID'
    
    def headers_display(self, obj):
        import json
        if obj.headers:
            formatted = json.dumps(obj.headers, indent=2)
            return mark_safe(f'<pre>{formatted}</pre>')
        return '-'
    headers_display.short_description = 'Headers'
    
    def body_display(self, obj):
        import json
        if obj.body:
            formatted = json.dumps(obj.body, indent=2)
            return mark_safe(f'<pre>{formatted}</pre>')
        return '-'
    body_display.short_description = 'Request Body'
    
    def response_body_display(self, obj):
        import json
        if obj.response_body:
            formatted = json.dumps(obj.response_body, indent=2)
            return mark_safe(f'<pre>{formatted}</pre>')
        return '-'
    response_body_display.short_description = 'Response Body'


@admin.register(MpesaPaymentMethod)
class MpesaPaymentMethodAdmin(admin.ModelAdmin):
    list_display = [
        'customer_link', 'phone_number', 'is_default',
        'is_verified', 'successful_transactions', 'failed_transactions',
        'last_used_at'
    ]
    list_filter = ['is_default', 'is_verified', 'created_at']
    search_fields = ['phone_number', 'customer__user__email']
    readonly_fields = [
        'successful_transactions', 'failed_transactions',
        'last_used_at', 'created_at', 'updated_at'
    ]
    
    def customer_link(self, obj):
        url = reverse('admin:customers_customer_change', args=[obj.customer.id])
        return format_html('<a href="{}">{}</a>', url, obj.customer.user.email)
    customer_link.short_description = 'Customer'


@admin.register(MpesaAccessToken)
class MpesaAccessTokenAdmin(admin.ModelAdmin):
    list_display = ['configuration', 'expires_at', 'is_valid', 'created_at']
    list_filter = ['created_at', 'expires_at']
    readonly_fields = ['token', 'created_at']
    
    def is_valid(self, obj):
        return not obj.is_expired
    is_valid.boolean = True
    is_valid.short_description = 'Is Valid'