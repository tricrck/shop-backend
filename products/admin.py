from django.contrib import admin
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
                    'stock_quantity', 'is_in_stock', 'is_featured', 'is_active']
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
            'fields': ('stock_quantity', 'low_stock_threshold', 'condition')
        }),
        ('Status', {
            'fields': ('is_active', 'is_featured')
        }),
        ('SEO', {
            'fields': ('meta_title', 'meta_description'),
            'classes': ('collapse',)
        }),
    )

    def final_price(self, obj):
        return f"${obj.final_price:.2f}"
    final_price.short_description = 'Final Price'

    def is_in_stock(self, obj):
        return obj.is_in_stock
    is_in_stock.boolean = True
    is_in_stock.short_description = 'In Stock'


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