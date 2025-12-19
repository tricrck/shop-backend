from django.contrib import admin
from django.db.models import Sum, F
from django.utils.html import format_html
from .models import (
    Warehouse, WarehouseStock, StockMovement, InventoryTransfer,
    TransferItem, StockAlert, StockCount, StockCountItem
)


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'town', 'county', 'is_active', 'is_primary', 
                   'priority', 'capacity_usage']
    list_filter = ['is_active', 'is_primary', 'county', 'country']
    search_fields = ['name', 'code', 'town', 'street_address']
    ordering = ['-priority', 'name']
    readonly_fields = ['created_at', 'updated_at', 'current_capacity']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'code', 'street_address', 'town', 'county', 'country', 'postal_code')
        }),
        ('Contact', {
            'fields': ('phone', 'email', 'manager')
        }),
        ('Settings', {
            'fields': ('is_active', 'is_primary', 'priority')
        }),
        ('Capacity', {
            'fields': ('max_capacity', 'current_capacity')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def capacity_usage(self, obj):
        try:
            if obj.max_capacity and obj.max_capacity > 0:
                percentage = obj.capacity_percentage
                color = 'green' if percentage < 70 else 'orange' if percentage < 90 else 'red'
                return format_html(
                    '<span style="color: {};">{:.1f}%</span>',
                    color, percentage
                )
        except Exception:
            pass
        return 'N/A'
    capacity_usage.short_description = 'Capacity Usage'


@admin.register(WarehouseStock)
class WarehouseStockAdmin(admin.ModelAdmin):
    list_display = ['product_info', 'warehouse', 'quantity', 'reserved_quantity', 
                   'damaged_quantity', 'available', 'location', 'needs_reorder_indicator']
    list_filter = ['warehouse', 'zone', 'last_counted']
    search_fields = ['product__name', 'product__sku', 'location']
    ordering = ['warehouse', 'product__name']
    readonly_fields = ['updated_at']
    
    fieldsets = (
        ('Product & Warehouse', {
            'fields': ('warehouse', 'product')
        }),
        ('Quantities', {
            'fields': ('quantity', 'reserved_quantity', 'damaged_quantity')
        }),
        ('Location', {
            'fields': ('location', 'zone')
        }),
        ('Reorder Settings', {
            'fields': ('reorder_point', 'reorder_quantity')
        }),
        ('Tracking', {
            'fields': ('last_counted', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def product_info(self, obj):
        try:
            return f"{obj.product.name} ({obj.product.sku})"
        except Exception:
            return "N/A"
    product_info.short_description = 'Product'
    
    def available(self, obj):
        try:
            avail = obj.available_quantity
            color = 'green' if avail > obj.reorder_point else 'orange' if avail > 0 else 'red'
            return format_html('<span style="color: {};">{}</span>', color, avail)
        except Exception:
            return "N/A"
    available.short_description = 'Available'
    
    def needs_reorder_indicator(self, obj):
        try:
            if obj.needs_reorder:
                return format_html('<span style="color: red;">⚠️ Yes</span>')
            return format_html('<span style="color: green;">✓ No</span>')
        except Exception:
            return "N/A"
    needs_reorder_indicator.short_description = 'Needs Reorder'


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ['movement_number', 'warehouse', 'product_info', 'movement_type', 
                   'quantity_change', 'created_at', 'created_by']
    list_filter = ['movement_type', 'warehouse', 'created_at']
    search_fields = ['movement_number', 'product__name', 'product__sku', 'notes']
    ordering = ['-created_at']
    readonly_fields = ['movement_number', 'created_at', 'quantity_before', 'quantity_after']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Movement Details', {
            'fields': ('movement_number', 'warehouse', 'product', 'movement_type')
        }),
        ('Quantities', {
            'fields': ('quantity', 'quantity_before', 'quantity_after')
        }),
        ('Cost', {
            'fields': ('unit_cost', 'total_cost'),
            'classes': ('collapse',)
        }),
        ('Reference', {
            'fields': ('reference_type', 'reference_id', 'order', 'transfer'),
            'classes': ('collapse',)
        }),
        ('Notes & Audit', {
            'fields': ('notes', 'created_by', 'approved_by', 'created_at', 'movement_date')
        }),
    )
    
    def product_info(self, obj):
        try:
            return f"{obj.product.name} ({obj.product.sku})"
        except Exception:
            return "N/A"
    product_info.short_description = 'Product'
    
    def quantity_change(self, obj):
        try:
            color = 'green' if obj.quantity > 0 else 'red'
            symbol = '+' if obj.quantity > 0 else ''
            return format_html('<span style="color: {};">{}{}</span>', color, symbol, obj.quantity)
        except Exception:
            return "N/A"
    quantity_change.short_description = 'Change'


class TransferItemInline(admin.TabularInline):
    model = TransferItem
    extra = 1
    fields = ['product', 'quantity', 'received_quantity', 'notes']
    readonly_fields = ['received_quantity']


@admin.register(InventoryTransfer)
class InventoryTransferAdmin(admin.ModelAdmin):
    list_display = ['transfer_number', 'from_warehouse', 'to_warehouse', 'status', 
                   'requested_at', 'requested_by']
    list_filter = ['status', 'from_warehouse', 'to_warehouse', 'requested_at']
    search_fields = ['transfer_number', 'tracking_number', 'notes']
    ordering = ['-requested_at']
    readonly_fields = ['transfer_number', 'requested_at', 'shipped_at', 
                      'received_at', 'requested_by', 'approved_by', 'received_by']
    date_hierarchy = 'requested_at'
    inlines = [TransferItemInline]
    
    fieldsets = (
        ('Transfer Information', {
            'fields': ('transfer_number', 'from_warehouse', 'to_warehouse', 'status')
        }),
        ('Tracking', {
            'fields': ('tracking_number', 'expected_arrival')
        }),
        ('Dates', {
            'fields': ('requested_at', 'shipped_at', 'received_at')
        }),
        ('Users', {
            'fields': ('requested_by', 'approved_by', 'received_by')
        }),
        ('Notes', {
            'fields': ('notes', 'rejection_reason'),
            'classes': ('collapse',)
        }),
    )


@admin.register(StockAlert)
class StockAlertAdmin(admin.ModelAdmin):
    list_display = ['alert_type', 'priority', 'warehouse', 'product_info', 
                   'current_quantity', 'is_resolved', 'created_at']
    list_filter = ['alert_type', 'priority', 'is_resolved', 'warehouse', 'created_at']
    search_fields = ['product__name', 'product__sku', 'message']
    ordering = ['-priority', '-created_at']
    readonly_fields = ['created_at', 'resolved_at', 'resolved_by']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Alert Details', {
            'fields': ('alert_type', 'priority', 'warehouse', 'product', 'message')
        }),
        ('Quantities', {
            'fields': ('current_quantity', 'threshold_quantity')
        }),
        ('Resolution', {
            'fields': ('is_resolved', 'resolved_at', 'resolved_by', 'resolution_notes')
        }),
        ('Created', {
            'fields': ('created_at',)
        }),
    )
    
    def product_info(self, obj):
        try:
            return f"{obj.product.name} ({obj.product.sku})"
        except Exception:
            return "N/A"
    product_info.short_description = 'Product'
    
    actions = ['resolve_alerts']
    
    def resolve_alerts(self, request, queryset):
        for alert in queryset:
            alert.resolve(request.user, 'Resolved via admin action')
        self.message_user(request, f'{queryset.count()} alerts resolved')
    resolve_alerts.short_description = 'Resolve selected alerts'


class StockCountItemInline(admin.TabularInline):
    model = StockCountItem
    extra = 0
    fields = ['product', 'expected_quantity', 'counted_quantity', 'discrepancy', 
             'has_discrepancy', 'notes']
    readonly_fields = ['discrepancy', 'has_discrepancy']


@admin.register(StockCount)
class StockCountAdmin(admin.ModelAdmin):
    list_display = ['count_number', 'warehouse', 'count_type', 'status', 
                   'scheduled_date', 'assigned_to']
    list_filter = ['status', 'count_type', 'warehouse', 'scheduled_date']
    search_fields = ['count_number', 'notes']
    ordering = ['-scheduled_date']
    readonly_fields = ['count_number', 'started_at', 'completed_at', 'completed_by']
    date_hierarchy = 'scheduled_date'
    inlines = [StockCountItemInline]
    
    fieldsets = (
        ('Count Information', {
            'fields': ('count_number', 'warehouse', 'count_type', 'status')
        }),
        ('Schedule', {
            'fields': ('scheduled_date', 'started_at', 'completed_at')
        }),
        ('Assignment', {
            'fields': ('assigned_to', 'completed_by')
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )