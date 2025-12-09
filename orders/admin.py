from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from django.db.models import Sum, Count, Avg
from rangefilter.filters import DateRangeFilter
from import_export.admin import ImportExportModelAdmin
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget

from .models import (
    Order, OrderItem, OrderStatusHistory, ShippingMethod,
    OrderReturn, ReturnItem, OrderNote
)


# Import/Export Resources
class OrderResource(resources.ModelResource):
    customer_email = fields.Field(
        column_name='customer_email',
        attribute='customer__user__email'
    )
    customer_name = fields.Field(
        column_name='customer_name',
        attribute=lambda obj: f"{obj.customer.user.first_name} {obj.customer.user.last_name}"
    )
    
    class Meta:
        model = Order
        fields = (
            'order_number', 'customer_email', 'customer_name', 'status',
            'payment_status', 'subtotal', 'tax_amount', 'shipping_cost',
            'discount_amount', 'total', 'created_at', 'tracking_number'
        )
        export_order = fields


class OrderItemResource(resources.ModelResource):
    product_name = fields.Field(
        column_name='product_name',
        attribute='product__name'
    )
    product_sku = fields.Field(
        column_name='product_sku',
        attribute='product__sku'
    )
    order_number = fields.Field(
        column_name='order_number',
        attribute='order__order_number'
    )
    
    class Meta:
        model = OrderItem
        fields = (
            'order_number', 'product_name', 'product_sku',
            'quantity', 'price', 'discount', 'total'
        )


# Inline Admins
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['product_link', 'price', 'total']
    fields = ['product_link', 'quantity', 'price', 'discount', 'total']
    
    def product_link(self, obj):
        if obj.product:
            url = reverse('admin:products_product_change', args=[obj.product.id])
            return format_html('<a href="{}">{}</a>', url, obj.product.name)
        return "-"
    product_link.short_description = 'Product'
    
    def has_add_permission(self, request, obj=None):
        return False


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ['old_status', 'new_status', 'changed_by', 'created_at']
    fields = ['old_status', 'new_status', 'changed_by', 'notes', 'created_at']
    
    def has_add_permission(self, request, obj=None):
        return False


class OrderNoteInline(admin.TabularInline):
    model = OrderNote
    extra = 1
    fields = ['user', 'note', 'is_customer_visible']


class ReturnItemInline(admin.TabularInline):
    model = ReturnItem
    extra = 0
    readonly_fields = ['order_item', 'refund_amount']
    fields = ['order_item', 'quantity', 'condition', 'refund_amount', 'notes']


# Main Admins
@admin.register(Order)
class OrderAdmin(ImportExportModelAdmin):
    resource_class = OrderResource
    list_display = [
        'order_number', 'customer_info', 'status_badge', 'payment_status_badge',
        'total_display', 'created_at', 'tracking_link', 'quick_actions'
    ]
    list_filter = [
        'status', 'payment_status', 'payment_method',
        ('created_at', DateRangeFilter),
        'is_guest', 'is_gift', 'is_digital'
    ]
    search_fields = [
        'order_number', 'customer__user__email',
        'customer__user__first_name', 'customer__user__last_name',
        'tracking_number', 'guest_email'
    ]
    readonly_fields = [
        'order_number', 'created_at', 'updated_at', 'paid_at',
        'cancelled_at', 'refunded_at', 'ip_address', 'status_history_link'
    ]
    fieldsets = (
        ('Order Information', {
            'fields': ('order_number', 'status', 'payment_status', 'payment_method')
        }),
        ('Customer Information', {
            'fields': ('customer', 'is_guest', 'guest_email', 'guest_phone')
        }),
        ('Addresses', {
            'fields': ('billing_address', 'shipping_address')
        }),
        ('Financial', {
            'fields': (
                'subtotal', 'tax_amount', 'tax_rate',
                'shipping_cost', 'discount_amount', 'discount_code',
                'total', 'currency'
            )
        }),
        ('Shipping', {
            'fields': (
                'shipping_method', 'carrier',
                'tracking_number', 'tracking_url',
                'estimated_delivery', 'shipped_date', 'delivered_date',
                'requires_shipping'
            )
        }),
        ('Notes & Messages', {
            'fields': ('customer_notes', 'admin_notes', 'gift_message')
        }),
        ('Flags', {
            'fields': ('is_gift', 'is_digital', 'is_recurring')
        }),
        ('Audit', {
            'fields': (
                'created_at', 'updated_at', 'paid_at',
                'cancelled_at', 'refunded_at', 'ip_address', 'user_agent'
            )
        }),
        ('Status History', {
            'fields': ('status_history_link',)
        }),
    )
    inlines = [OrderItemInline, OrderStatusHistoryInline, OrderNoteInline]
    actions = [
        'mark_as_processing', 'mark_as_shipped', 'mark_as_delivered',
        'mark_as_cancelled', 'export_selected_orders', 'send_tracking_email'
    ]
    list_per_page = 50
    
    def customer_info(self, obj):
        if obj.is_guest:
            return format_html(
                '<span style="color: #999;">Guest: {}</span>',
                obj.guest_email
            )
        
        url = reverse('admin:customers_customer_change', args=[obj.customer.id])
        name = f"{obj.customer.user.first_name} {obj.customer.user.last_name}"
        return format_html(
            '<a href="{}">{}<br/><small>{}</small></a>',
            url, name, obj.customer.user.email
        )
    customer_info.short_description = 'Customer'
    
    def status_badge(self, obj):
        colors = {
            'pending': '#ffc107',
            'processing': '#17a2b8',
            'shipped': '#007bff',
            'delivered': '#28a745',
            'cancelled': '#dc3545',
            'refunded': '#6c757d',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; '
            'border-radius: 12px; font-size: 12px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def payment_status_badge(self, obj):
        colors = {
            'pending': '#ffc107',
            'paid': '#28a745',
            'failed': '#dc3545',
            'refunded': '#6c757d',
        }
        color = colors.get(obj.payment_status, '#6c757d')
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; '
            'border-radius: 12px; font-size: 12px;">{}</span>',
            color, obj.get_payment_status_display()
        )
    payment_status_badge.short_description = 'Payment'
    
    def total_display(self, obj):
        return format_html(
            '<strong>${}</strong>',
            obj.total
        )
    total_display.short_description = 'Total'
    
    def tracking_link(self, obj):
        if obj.tracking_number:
            if obj.tracking_url:
                return format_html(
                    '<a href="{}" target="_blank">{}</a>',
                    obj.tracking_url, obj.tracking_number
                )
            return obj.tracking_number
        return "-"
    tracking_link.short_description = 'Tracking'
    
    def status_history_link(self, obj):
        count = obj.status_history.count()
        return format_html(
            '{} status change{} recorded',
            count, '' if count == 1 else 's'
        )
    status_history_link.short_description = 'Status History'
    
    def quick_actions(self, obj):
        links = []
        
        if obj.is_cancellable:
            url = reverse('admin:orders_order_cancel', args=[obj.pk])
            links.append(f'<a href="{url}" class="button">Cancel</a>')
        
        if not obj.tracking_number and obj.status in ['processing', 'ready_to_ship']:
            url = reverse('admin:orders_order_add_tracking', args=[obj.pk])
            links.append(f'<a href="{url}" class="button">Add Tracking</a>')
        
        return format_html(' '.join(links))
    quick_actions.short_description = 'Actions'  # Keep the display name as "Actions"
    
    # Keep the actions attribute as a list of strings for admin actions
    actions = [
        'mark_as_processing', 'mark_as_shipped', 'mark_as_delivered',
        'mark_as_cancelled', 'export_selected_orders', 'send_tracking_email'
    ]
    
    # Custom Actions
    def mark_as_processing(self, request, queryset):
        updated = queryset.update(status='processing')
        self.message_user(request, f"{updated} orders marked as processing.")
    mark_as_processing.short_description = "Mark selected as processing"
    
    def mark_as_shipped(self, request, queryset):
        for order in queryset:
            order.status = 'shipped'
            order.shipped_date = timezone.now()
            order.save()
        self.message_user(request, f"{queryset.count()} orders marked as shipped.")
    mark_as_shipped.short_description = "Mark selected as shipped"
    
    def mark_as_delivered(self, request, queryset):
        queryset.update(status='delivered', delivered_date=timezone.now())
        self.message_user(request, f"{queryset.count()} orders marked as delivered.")
    mark_as_delivered.short_description = "Mark selected as delivered"
    
    def mark_as_cancelled(self, request, queryset):
        queryset.update(status='cancelled', cancelled_at=timezone.now())
        self.message_user(request, f"{queryset.count()} orders marked as cancelled.")
    mark_as_cancelled.short_description = "Mark selected as cancelled"
    
    def export_selected_orders(self, request, queryset):
        # Implementation for exporting selected orders
        pass
    export_selected_orders.short_description = "Export selected orders"
    
    def send_tracking_email(self, request, queryset):
        # Implementation for sending tracking emails
        pass
    send_tracking_email.short_description = "Send tracking email"
    
    # Custom change view
    change_form_template = 'admin/orders/order/change_form.html'
    
    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('<path:object_id>/cancel/', self.admin_site.admin_view(self.cancel_order_view),
                 name='orders_order_cancel'),
            path('<path:object_id>/add-tracking/', self.admin_site.admin_view(self.add_tracking_view),
                 name='orders_order_add_tracking'),
        ]
        return custom_urls + urls
    
    def cancel_order_view(self, request, object_id):
        # Custom cancel view
        pass
    
    def add_tracking_view(self, request, object_id):
        # Custom add tracking view
        pass


@admin.register(OrderItem)
class OrderItemAdmin(ImportExportModelAdmin):
    resource_class = OrderItemResource
    list_display = ['order_link', 'product_link', 'quantity', 'price', 'total']
    list_filter = [('order__created_at', DateRangeFilter)]
    search_fields = ['order__order_number', 'product__name', 'product__sku']
    readonly_fields = ['order', 'product', 'price', 'total']
    
    def order_link(self, obj):
        url = reverse('admin:orders_order_change', args=[obj.order.id])
        return format_html('<a href="{}">{}</a>', url, obj.order.order_number)
    order_link.short_description = 'Order'
    
    def product_link(self, obj):
        if obj.product:
            url = reverse('admin:products_product_change', args=[obj.product.id])
            return format_html('<a href="{}">{}</a>', url, obj.product.name)
        return "-"
    product_link.short_description = 'Product'


@admin.register(ShippingMethod)
class ShippingMethodAdmin(admin.ModelAdmin):
    list_display = ['name', 'carrier', 'code', 'cost', 'is_active', 'estimated_delivery_text']
    list_filter = ['carrier', 'is_active']
    search_fields = ['name', 'carrier', 'code']
    list_editable = ['is_active', 'cost']
    
    def estimated_delivery_text(self, obj):
        return f"{obj.estimated_days_min}-{obj.estimated_days_max} days"
    estimated_delivery_text.short_description = 'Delivery Time'


@admin.register(OrderReturn)
class OrderReturnAdmin(admin.ModelAdmin):
    list_display = [
        'return_number', 'order_link', 'status_badge', 'reason',
        'refund_amount', 'requested_at'
    ]
    list_filter = ['status', 'reason', ('requested_at', DateRangeFilter)]
    search_fields = ['return_number', 'order__order_number']
    inlines = [ReturnItemInline]
    readonly_fields = ['return_number', 'requested_at']
    
    def order_link(self, obj):
        url = reverse('admin:orders_order_change', args=[obj.order.id])
        return format_html('<a href="{}">{}</a>', url, obj.order.order_number)
    order_link.short_description = 'Order'
    
    def status_badge(self, obj):
        colors = {
            'requested': '#ffc107',
            'approved': '#17a2b8',
            'received': '#007bff',
            'refunded': '#28a745',
            'rejected': '#dc3545',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; '
            'border-radius: 12px; font-size: 12px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ['order_link', 'old_status', 'new_status', 'changed_by', 'created_at']
    list_filter = ['new_status', ('created_at', DateRangeFilter)]
    search_fields = ['order__order_number']
    readonly_fields = ['order', 'old_status', 'new_status', 'changed_by', 'created_at']
    
    def order_link(self, obj):
        url = reverse('admin:orders_order_change', args=[obj.order.id])
        return format_html('<a href="{}">{}</a>', url, obj.order.order_number)
    order_link.short_description = 'Order'


# Admin Site Customization
class OrderAdminSite(admin.AdminSite):
    site_header = "SoundWaveAudio Order Management"
    site_title = "Order Admin"
    index_title = "Order Dashboard"


# Register analytics view in admin
class OrderAnalyticsAdmin(admin.ModelAdmin):
    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('analytics/', self.admin_site.admin_view(self.analytics_view),
                 name='orders_analytics'),
        ]
        return custom_urls + urls
    
    def analytics_view(self, request):
        from django.shortcuts import render
        from .models import Order
        
        # Calculate analytics
        total_orders = Order.objects.count()
        total_revenue = Order.objects.aggregate(Sum('total'))['total__sum'] or 0
        avg_order_value = Order.objects.aggregate(Avg('total'))['total__avg'] or 0
        
        context = {
            'total_orders': total_orders,
            'total_revenue': total_revenue,
            'avg_order_value': avg_order_value,
        }
        
        return render(request, 'admin/orders/analytics.html', context)


# Add analytics to order admin
OrderAdmin.analytics_view = OrderAnalyticsAdmin.analytics_view