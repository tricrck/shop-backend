from rest_framework import serializers
from .models import Category, Brand, Product, ProductImage, Review

class CategorySerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'description', 'image', 'parent', 'children', 'is_active', 'product_count', 'created_at']
        read_only_fields = ['slug', 'created_at']

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
        fields = ['id', 'name', 'slug', 'logo', 'description', 'website', 'is_active', 'product_count', 'created_at']
        read_only_fields = ['slug', 'created_at']

    def get_product_count(self, obj):
        return obj.products.filter(is_active=True).count()


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'alt_text', 'is_primary', 'order']


class ReviewSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.user.get_full_name', read_only=True)

    class Meta:
        model = Review
        fields = ['id', 'customer', 'customer_name', 'rating', 'title', 'comment', 'is_verified_purchase', 'is_approved', 'created_at', 'updated_at']
        read_only_fields = ['customer', 'is_verified_purchase', 'is_approved', 'created_at', 'updated_at']


class ProductListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    brand_name = serializers.CharField(source='brand.name', read_only=True)
    primary_image = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['id', 'name', 'slug', 'sku', 'category_name', 'brand_name', 'price', 'discount_percentage', 
                  'final_price', 'primary_image', 'is_in_stock', 'is_featured', 'average_rating']

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