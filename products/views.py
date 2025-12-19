from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Avg, Count, F
from django.db import models
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from .models import Category, Brand, Product, ProductImage, Review
from .serializers import (CategorySerializer, BrandSerializer, ProductListSerializer, 
                          ProductDetailSerializer, ProductImageSerializer, ReviewSerializer,
                          ProductCreateUpdateSerializer, CategoryCreateUpdateSerializer,
                          BrandCreateUpdateSerializer)
from .filters import ProductFilter
from .permissions import IsAdminOrReadOnly
from django.core.cache import cache

class CategoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Category CRUD operations.
    List and Retrieve are public, Create/Update/Delete require admin.
    """
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']  # Explicit default ordering

    @method_decorator(cache_page(60 * 15))
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_serializer_class(self):
        """Use different serializers for different actions"""
        if self.action in ['create', 'update', 'partial_update']:
            return CategoryCreateUpdateSerializer
        return CategorySerializer

    def perform_create(self, serializer):
        """Create a new category"""
        serializer.save()

    def perform_update(self, serializer):
        """Update an existing category"""
        serializer.save()

    def perform_destroy(self, instance):
        """Soft delete by setting is_active to False"""
        instance.is_active = False
        instance.save()

    @action(detail=True, methods=['get'])
    def products(self, request, slug=None):
        """Get all products for a specific category"""
        category = self.get_object()
        products = Product.objects.filter(category=category, is_active=True)
        serializer = ProductListSerializer(products, many=True)
        return Response(serializer.data)


class BrandViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Brand CRUD operations.
    List and Retrieve are public, Create/Update/Delete require admin.
    """
    queryset = Brand.objects.filter(is_active=True)
    serializer_class = BrandSerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']  # FIX: Add explicit default ordering

    @method_decorator(cache_page(60 * 15))
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_serializer_class(self):
        """Use different serializers for different actions"""
        if self.action in ['create', 'update', 'partial_update']:
            return BrandCreateUpdateSerializer
        return BrandSerializer

    def perform_create(self, serializer):
        """Create a new brand"""
        serializer.save()

    def perform_update(self, serializer):
        """Update an existing brand"""
        serializer.save()

    def perform_destroy(self, instance):
        """Soft delete by setting is_active to False"""
        instance.is_active = False
        instance.save()

    @action(detail=True, methods=['get'])
    def products(self, request, slug=None):
        """Get all products for a specific brand"""
        brand = self.get_object()
        products = Product.objects.filter(brand=brand, is_active=True)
        serializer = ProductListSerializer(products, many=True)
        return Response(serializer.data)


class ProductViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Product CRUD operations.
    List and Retrieve are public, Create/Update/Delete require admin.
    """
    queryset = Product.objects.filter(is_active=True).select_related(
        'category', 'brand'  # Use select_related for foreign keys
    ).prefetch_related(
        'images',  # Prefetch images
        models.Prefetch(  # Prefetch reviews with aggregation
            'reviews',
            queryset=Review.objects.filter(is_approved=True),
            to_attr='approved_reviews'
        )
    )
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ['name', 'description', 'sku', 'brand__name']
    ordering_fields = ['price', 'created_at', 'name', 'stock_quantity']
    ordering = ['-created_at']  # Explicit default ordering

    def get_serializer_class(self):
        """Use different serializers for different actions"""
        if self.action == 'list':
            return ProductListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ProductCreateUpdateSerializer
        return ProductDetailSerializer

    @method_decorator(cache_page(60 * 5))
    def list(self, request, *args, **kwargs):
        # Add cache key based on query params
        cache_key = f"products_list_{hash(str(request.GET))}"
        cached_data = cache.get(cache_key)
        
        if cached_data is not None:
            return Response(cached_data)
        
        response = super().list(request, *args, **kwargs)
        cache.set(cache_key, response.data, timeout=60 * 5)
        return response

    def perform_create(self, serializer):
        """Create a new product"""
        serializer.save()

    def perform_update(self, serializer):
        """Update an existing product"""
        serializer.save()

    def perform_destroy(self, instance):
        """Soft delete by setting is_active to False"""
        instance.is_active = False
        instance.save()

    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get featured products"""
        products = self.queryset.filter(is_featured=True)[:10]
        serializer = ProductListSerializer(products, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        """Get products with low stock"""
        products = Product.objects.filter(
            stock_quantity__lte=F('low_stock_threshold'),
            is_active=True
        ).order_by('-created_at')  # Explicit ordering for consistency
        serializer = ProductListSerializer(products, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def on_sale(self, request):
        """Get products that are on sale"""
        products = self.queryset.filter(discount_percentage__gt=0)
        serializer = ProductListSerializer(products, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def add_image(self, request, slug=None):
        """Add an image to a product"""
        product = self.get_object()
        serializer = ProductImageSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(product=product)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['delete'], permission_classes=[IsAuthenticated])
    def remove_image(self, request, slug=None):
        """Remove an image from a product"""
        product = self.get_object()
        image_id = request.data.get('image_id')
        
        try:
            image = ProductImage.objects.get(id=image_id, product=product)
            image.delete()
            return Response(
                {'message': 'Image deleted successfully'}, 
                status=status.HTTP_204_NO_CONTENT
            )
        except ProductImage.DoesNotExist:
            return Response(
                {'error': 'Image not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=['patch'], permission_classes=[IsAuthenticated])
    def update_stock(self, request, slug=None):
        """Update product stock quantity"""
        product = self.get_object()
        quantity = request.data.get('stock_quantity')
        
        if quantity is None:
            return Response(
                {'error': 'stock_quantity is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            quantity = int(quantity)
            if quantity < 0:
                return Response(
                    {'error': 'stock_quantity must be non-negative'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            product.stock_quantity = quantity
            product.save()
            
            return Response({
                'message': 'Stock updated successfully',
                'stock_quantity': product.stock_quantity,
                'is_in_stock': product.is_in_stock,
                'is_low_stock': product.is_low_stock
            })
        except ValueError:
            return Response(
                {'error': 'Invalid stock_quantity value'}, 
                status=status.HTTP_400_BAD_REQUEST
            )


class ReviewViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Review CRUD operations.
    Only authenticated users can create reviews.
    Users can only update/delete their own reviews.
    """
    queryset = Review.objects.filter(is_approved=True)
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['product', 'rating']
    ordering_fields = ['created_at', 'rating']
    ordering = ['-created_at']

    def get_queryset(self):
        queryset = self.queryset
        
        # Annotate with review stats to avoid N+1 queries
        queryset = queryset.annotate(
            review_count=models.Count('reviews', filter=models.Q(reviews__is_approved=True)),
            average_rating=models.Avg('reviews__rating', filter=models.Q(reviews__is_approved=True))
        )
        
        return queryset

    def perform_create(self, serializer):
        """Create a new review for authenticated user"""
        serializer.save(customer=self.request.user.customer)

    def perform_update(self, serializer):
        """Update review - only by owner or admin"""
        review = self.get_object()
        if review.customer != self.request.user.customer and not self.request.user.is_staff:
            return Response(
                {'error': 'You can only update your own reviews'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        serializer.save()

    def perform_destroy(self, instance):
        """Delete review - only by owner or admin"""
        if instance.customer != self.request.user.customer and not self.request.user.is_staff:
            return Response(
                {'error': 'You can only delete your own reviews'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        instance.delete()

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def approve(self, request, pk=None):
        """Approve a review (admin only)"""
        if not request.user.is_staff:
            return Response(
                {'error': 'Only admins can approve reviews'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        review = self.get_object()
        review.is_approved = True
        review.save()
        
        return Response({
            'message': 'Review approved successfully',
            'review': ReviewSerializer(review).data
        })

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_reviews(self, request):
        """Get all reviews by the current user"""
        reviews = Review.objects.filter(customer=request.user.customer)
        serializer = self.get_serializer(reviews, many=True)
        return Response(serializer.data)