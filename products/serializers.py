from rest_framework import serializers
from django.db import models
from .models import Category, Brand, Product, ProductImage, Review

class CategorySerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'description', 'image', 'parent', 'children', 
                  'is_active', 'product_count', 'created_at', 'updated_at']
        read_only_fields = ['slug', 'created_at', 'updated_at']

    def get_children(self, obj):
        if obj.children.exists():
            return CategorySerializer(obj.children.filter(is_active=True), many=True).data
        return []

    def get_product_count(self, obj):
        return obj.products.filter(is_active=True).count()


class BrandSerializer(serializers.ModelSerializer):
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Brand
        fields = ['id', 'name', 'slug', 'logo', 'description', 'website', 
                  'is_active', 'product_count', 'created_at']
        read_only_fields = ['slug', 'created_at']

    def get_product_count(self, obj):
        return obj.products.filter(is_active=True).count()


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'alt_text', 'is_primary', 'order', 'created_at']
        read_only_fields = ['created_at']


class ReviewSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.user.get_full_name', read_only=True)
    customer_email = serializers.EmailField(source='customer.user.email', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = Review
        fields = ['id', 'product', 'product_name', 'customer', 'customer_name', 
                  'customer_email', 'rating', 'title', 'comment', 'is_verified_purchase', 
                  'is_approved', 'created_at', 'updated_at']
        read_only_fields = ['customer', 'customer_name', 'customer_email', 'product_name',
                           'is_verified_purchase', 'is_approved', 'created_at', 'updated_at']

    def validate_rating(self, value):
        """Ensure rating is between 1 and 5"""
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating must be between 1 and 5")
        return value

    def validate(self, data):
        """Check if user has already reviewed this product"""
        request = self.context.get('request')
        if request and request.method == 'POST':
            product = data.get('product')
            if Review.objects.filter(product=product, customer=request.user.customer).exists():
                raise serializers.ValidationError("You have already reviewed this product")
        return data


class ProductListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_slug = serializers.CharField(source='category.slug', read_only=True)
    brand_name = serializers.CharField(source='brand.name', read_only=True)
    brand_slug = serializers.CharField(source='brand.slug', read_only=True)
    primary_image = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['id', 'name', 'slug', 'sku', 'category_name', 'category_slug', 
                  'brand_name', 'brand_slug', 'price', 'discount_percentage', 
                  'final_price', 'primary_image', 'stock_quantity', 'is_in_stock', 
                  'is_low_stock', 'is_featured', 'average_rating', 'review_count', 
                  'created_at']

    def get_primary_image(self, obj):
        primary = obj.images.filter(is_primary=True).first()
        if primary:
            return primary.image.url
        first_image = obj.images.first()
        return first_image.image.url if first_image else None

    def get_average_rating(self, obj):
        reviews = obj.reviews.filter(is_approved=True)
        if reviews.exists():
            return round(reviews.aggregate(models.Avg('rating'))['rating__avg'], 1)
        return None

    def get_review_count(self, obj):
        return obj.reviews.filter(is_approved=True).count()


class ProductDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)
    average_rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = '__all__'
        read_only_fields = ['slug', 'created_at', 'updated_at']

    def get_average_rating(self, obj):
        reviews = obj.reviews.filter(is_approved=True)
        if reviews.exists():
            return round(reviews.aggregate(models.Avg('rating'))['rating__avg'], 1)
        return None

    def get_review_count(self, obj):
        return obj.reviews.filter(is_approved=True).count()


class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating products"""
    
    class Meta:
        model = Product
        fields = ['id', 'name', 'slug', 'sku', 'description', 'category', 'brand', 
                  'price', 'cost_price', 'discount_percentage', 'specifications', 
                  'weight', 'dimensions', 'stock_quantity', 'low_stock_threshold', 
                  'condition', 'is_active', 'is_featured', 'meta_title', 
                  'meta_description', 'created_at', 'updated_at']
        read_only_fields = ['slug', 'created_at', 'updated_at']

    def validate_sku(self, value):
        """Ensure SKU is unique"""
        instance = self.instance
        if instance and instance.sku == value:
            return value
        
        if Product.objects.filter(sku=value).exists():
            raise serializers.ValidationError("Product with this SKU already exists")
        return value

    def validate_price(self, value):
        """Ensure price is positive"""
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than 0")
        return value

    def validate_discount_percentage(self, value):
        """Ensure discount is between 0 and 100"""
        if value < 0 or value > 100:
            raise serializers.ValidationError("Discount percentage must be between 0 and 100")
        return value

    def validate_stock_quantity(self, value):
        """Ensure stock quantity is non-negative"""
        if value < 0:
            raise serializers.ValidationError("Stock quantity cannot be negative")
        return value

    def validate(self, data):
        """Additional validation"""
        # Ensure cost price is less than selling price if provided
        cost_price = data.get('cost_price')
        price = data.get('price')
        
        if cost_price and price and cost_price > price:
            raise serializers.ValidationError({
                'cost_price': 'Cost price cannot be greater than selling price'
            })
        
        return data
# serializers.py - Add these new serializers

class CategoryCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating categories"""
    
    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'image', 'parent', 'is_active']
        read_only_fields = ['slug', 'created_at', 'updated_at']

    def validate_name(self, value):
        """Ensure category name is unique"""
        instance = self.instance
        if instance and instance.name == value:
            return value
        
        if Category.objects.filter(name=value).exists():
            raise serializers.ValidationError("Category with this name already exists")
        return value


class BrandCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating brands"""
    
    class Meta:
        model = Brand
        fields = ['id', 'name', 'logo', 'description', 'website', 'is_active']
        read_only_fields = ['slug', 'created_at']

    def validate_name(self, value):
        """Ensure brand name is unique"""
        instance = self.instance
        if instance and instance.name == value:
            return value
        
        if Brand.objects.filter(name=value).exists():
            raise serializers.ValidationError("Brand with this name already exists")
        return value