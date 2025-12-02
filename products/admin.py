from django.contrib import admin
from .models import Category, Brand, Product, ProductImage, Review

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'sku', 'category', 'brand', 'price', 'stock_quantity', 'is_active']
    list_filter = ['is_active', 'is_featured', 'category', 'brand', 'condition']
    search_fields = ['name', 'sku', 'description']
    prepopulated_fields = {'slug': ('name', 'sku')}
    inlines = [ProductImageInline]
    readonly_fields = ['created_at', 'updated_at']

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['product', 'customer', 'rating', 'is_approved', 'created_at']
    list_filter = ['is_approved', 'rating', 'created_at']
    search_fields = ['product__name', 'customer__user__email']