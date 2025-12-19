from django.contrib import admin
from django.db.models import Sum, F
from .models import Category, Brand, Product, ProductImage, Review

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'parent', 'is_active', 'created_at']
    list_filter = ['is_active', 'parent', 'created_at']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ['is_active']
    date_hierarchy = 'created_at'


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'website', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ['is_active']
    date_hierarchy = 'created_at'


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ['image', 'alt_text', 'is_primary', 'order']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'sku', 'category', 'brand', 'price', 'final_price', 
                    'stock_quantity', 'warehouse_total', 'is_in_stock', 'is_featured', 'is_active']
    list_filter = ['category', 'brand', 'condition', 'is_featured', 'is_active', 'created_at']
    search_fields = ['name', 'sku', 'description']
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ['price', 'stock_quantity', 'is_featured', 'is_active']
    inlines = [ProductImageInline]
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'sku', 'description', 'category', 'brand')
        }),
        ('Pricing', {
            'fields': ('price', 'cost_price', 'discount_percentage')
        }),
        ('Specifications', {
            'fields': ('specifications', 'weight', 'dimensions')
        }),
        ('Inventory', {
            'fields': ('stock_quantity', 'low_stock_threshold', 'condition'),
            'description': 'Note: Updating stock_quantity will automatically sync with warehouse stocks.'
        }),
        ('Status', {
            'fields': ('is_active', 'is_featured')
        }),
        ('SEO', {
            'fields': ('meta_title', 'meta_description'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['warehouse_stock_info']

    def get_fieldsets(self, request, obj=None):
        """Add warehouse info for existing products"""
        fieldsets = super().get_fieldsets(request, obj)
        
        if obj and obj.pk:  # Only for existing products
            # Add warehouse info to Inventory section
            inventory_fields = list(fieldsets[3][1]['fields'])
            if 'warehouse_stock_info' not in inventory_fields:
                inventory_fields.append('warehouse_stock_info')
                fieldsets[3][1]['fields'] = tuple(inventory_fields)
        
        return fieldsets

    def final_price(self, obj):
        return f"${obj.final_price:.2f}"
    final_price.short_description = 'Final Price'

    def is_in_stock(self, obj):
        return obj.is_in_stock
    is_in_stock.boolean = True
    is_in_stock.short_description = 'In Stock'

    def warehouse_total(self, obj):
        """Display total stock across all warehouses"""
        try:
            from inventory.models import WarehouseStock
            total = WarehouseStock.objects.filter(product=obj).aggregate(
                total=Sum('quantity')
            )['total'] or 0
            return total
        except ImportError:
            return 'N/A'
    warehouse_total.short_description = 'Warehouse Total'

    def warehouse_stock_info(self, obj):
        """Display detailed warehouse stock information"""
        try:
            from inventory.models import WarehouseStock
            from django.utils.html import format_html
            
            stocks = WarehouseStock.objects.filter(product=obj).select_related('warehouse')
            
            if not stocks.exists():
                return format_html('<p style="color: orange;">No warehouse stocks found</p>')
            
            html = '<table style="width: 100%; border-collapse: collapse;">'
            html += '<tr style="background-color: #f0f0f0;"><th>Warehouse</th><th>Quantity</th><th>Reserved</th><th>Damaged</th><th>Available</th></tr>'
            
            for stock in stocks:
                available = stock.quantity - stock.reserved_quantity - stock.damaged_quantity
                html += f'''<tr style="border-bottom: 1px solid #ddd;">
                    <td>{stock.warehouse.name}</td>
                    <td>{stock.quantity}</td>
                    <td>{stock.reserved_quantity}</td>
                    <td>{stock.damaged_quantity}</td>
                    <td><strong>{available}</strong></td>
                </tr>'''
            
            html += '</table>'
            return format_html(html)
        except ImportError:
            return format_html('<p style="color: gray;">Inventory module not available</p>')
    
    warehouse_stock_info.short_description = 'Warehouse Stock Details'

    def save_model(self, request, obj, form, change):
        """Override save to handle warehouse sync"""
        super().save_model(request, obj, form, change)
        
        if change and 'stock_quantity' in form.changed_data:
            self.message_user(
                request, 
                f'Product stock updated. Warehouse stocks have been synchronized.',
                level='success'
            )


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ['product', 'alt_text', 'is_primary', 'order', 'created_at']
    list_filter = ['is_primary', 'created_at']
    search_fields = ['product__name', 'alt_text']
    list_editable = ['is_primary', 'order']


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['product', 'customer', 'rating', 'title', 'is_verified_purchase', 
                    'is_approved', 'created_at']
    list_filter = ['rating', 'is_verified_purchase', 'is_approved', 'created_at']
    search_fields = ['product__name', 'customer__user__email', 'title', 'comment']
    list_editable = ['is_approved']
    date_hierarchy = 'created_at'
    readonly_fields = ['customer', 'product', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Review Information', {
            'fields': ('product', 'customer', 'rating', 'title', 'comment')
        }),
        ('Status', {
            'fields': ('is_verified_purchase', 'is_approved')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def has_add_permission(self, request):
        # Reviews should only be created through the API
        return False