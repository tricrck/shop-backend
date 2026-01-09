from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Avg, Count, F, Prefetch, Sum, Case, When, DecimalField
from django.db import models
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.core.cache import cache
from .models import Category, Brand, Product, ProductImage, Review
from .serializers import (CategorySerializer, BrandSerializer, ProductListSerializer, 
                          ProductDetailSerializer, ProductImageSerializer, ReviewSerializer,
                          ProductCreateUpdateSerializer, CategoryCreateUpdateSerializer,
                          BrandCreateUpdateSerializer)
from .filters import ProductFilter
from .permissions import IsAdminOrReadOnly
from backend.pagination import (
    StandardResultsSetPagination, 
    ProductCursorPagination,
    SmallResultsSetPagination,
    LargeResultsSetPagination
)


class CategoryViewSet(viewsets.ModelViewSet):
    """ViewSet for Category CRUD operations."""
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    
    # Use standard pagination
    pagination_class = StandardResultsSetPagination

    @method_decorator(cache_page(60 * 15))
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return CategoryCreateUpdateSerializer
        return CategorySerializer

    def perform_destroy(self, instance):
        """Soft delete by setting is_active to False"""
        instance.is_active = False
        instance.save()

    @action(detail=True, methods=['get'])
    def products(self, request, slug=None):
        """Get all products for a specific category"""
        category = self.get_object()
        products = Product.objects.filter(
            category=category, 
            is_active=True
        ).select_related('category', 'brand').prefetch_related(
            'images',
            Prefetch('reviews', queryset=Review.objects.filter(is_approved=True))
        ).annotate(
            annotated_avg_rating=Avg('reviews__rating', filter=Q(reviews__is_approved=True)),
            annotated_review_count=Count('reviews', filter=Q(reviews__is_approved=True))
        )
        
        # Use pagination for category products
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(products, request)
        serializer = ProductListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class BrandViewSet(viewsets.ModelViewSet):
    """ViewSet for Brand CRUD operations."""
    queryset = Brand.objects.filter(is_active=True)
    serializer_class = BrandSerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    
    # Use standard pagination
    pagination_class = StandardResultsSetPagination

    @method_decorator(cache_page(60 * 15))
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return BrandCreateUpdateSerializer
        return BrandSerializer

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save()

    @action(detail=True, methods=['get'])
    def products(self, request, slug=None):
        """Get all products for a specific brand"""
        brand = self.get_object()
        products = Product.objects.filter(
            brand=brand, 
            is_active=True
        ).select_related('category', 'brand').prefetch_related(
            'images',
            Prefetch('reviews', queryset=Review.objects.filter(is_approved=True))
        ).annotate(
            annotated_avg_rating=Avg('reviews__rating', filter=Q(reviews__is_approved=True)),
            annotated_review_count=Count('reviews', filter=Q(reviews__is_approved=True))
        )
        
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(products, request)
        serializer = ProductListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class ProductViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Product CRUD operations with optimized queries.
    Uses cursor pagination for better performance with large datasets.
    """
    queryset = Product.objects.filter(is_active=True)
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ['name', 'description', 'sku', 'brand__name']
    ordering_fields = ['price', 'created_at', 'name', 'stock_quantity']
    ordering = ['-created_at']
    
    # CRITICAL: Use cursor pagination for products (handles large datasets better)
    pagination_class = ProductCursorPagination

    def get_queryset(self):
        """
        Optimized queryset with all necessary prefetching.
        Eliminates N+1 queries completely.
        """
        queryset = super().get_queryset()
        
        # Select related for foreign keys
        queryset = queryset.select_related('category', 'brand')
        
        # Prefetch images efficiently
        queryset = queryset.prefetch_related(
            Prefetch(
                'images',
                queryset=ProductImage.objects.order_by('-is_primary', 'order')
            )
        )
        
        # Prefetch approved reviews
        queryset = queryset.prefetch_related(
            Prefetch(
                'reviews',
                queryset=Review.objects.filter(is_approved=True).select_related('customer__user'),
                to_attr='approved_reviews'
            )
        )
        
        # Annotate with aggregated data (eliminates N+1 for ratings/counts)
        queryset = queryset.annotate(
            annotated_avg_rating=Avg(
                'reviews__rating', 
                filter=Q(reviews__is_approved=True)
            ),
            annotated_review_count=Count(
                'reviews', 
                filter=Q(reviews__is_approved=True),
                distinct=True
            )
        )
        
        return queryset

    def get_serializer_class(self):
        if self.action == 'list':
            return ProductListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ProductCreateUpdateSerializer
        return ProductDetailSerializer

    @method_decorator(cache_page(60 * 5))
    def list(self, request, *args, **kwargs):
        """Cached list view with smart cache key"""
        # Create cache key from query params
        cache_key = f"products_list_{hash(frozenset(request.GET.items()))}"
        
        # Try to get from cache
        cached_response = cache.get(cache_key, version='pagination')
        if cached_response:
            return Response(cached_response)
        
        # Get fresh data
        response = super().list(request, *args, **kwargs)
        
        # Cache the response data
        cache.set(cache_key, response.data, timeout=60 * 5, version='pagination')
        
        return response

    def perform_create(self, serializer):
        """Clear cache when creating products"""
        serializer.save()
        cache.delete_pattern('products_list_*', version='pagination')

    def perform_update(self, serializer):
        """Clear cache when updating products"""
        serializer.save()
        cache.delete_pattern('products_list_*', version='pagination')

    def perform_destroy(self, instance):
        """Soft delete and clear cache"""
        instance.is_active = False
        instance.save()
        cache.delete_pattern('products_list_*', version='pagination')

    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get featured products with small pagination"""
        products = self.get_queryset().filter(is_featured=True)
        
        # Use smaller pagination for featured items
        paginator = SmallResultsSetPagination()
        page = paginator.paginate_queryset(products, request)
        serializer = ProductListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        """Get products with low stock"""
        products = self.get_queryset().filter(
            stock_quantity__lte=F('low_stock_threshold')
        )
        
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(products, request)
        serializer = ProductListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @action(detail=False, methods=['get'])
    def on_sale(self, request):
        """Get products that are on sale"""
        products = self.get_queryset().filter(discount_percentage__gt=0)
        
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(products, request)
        serializer = ProductListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def add_image(self, request, slug=None):
        """Add an image to a product"""
        product = self.get_object()
        serializer = ProductImageSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(product=product)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
            
            # Clear cache
            cache.delete_pattern('products_list_*', version='pagination')
            
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
    """ViewSet for Review CRUD operations with optimized queries."""
    queryset = Review.objects.filter(is_approved=True)
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['product', 'rating']
    ordering_fields = ['created_at', 'rating']
    ordering = ['-created_at']
    
    # Use small pagination for reviews
    pagination_class = SmallResultsSetPagination

    def get_queryset(self):
        """Optimized queryset with prefetching"""
        queryset = super().get_queryset()  # Gets the base queryset
        return queryset.select_related(
            'customer__user',
            'product'
        )

    def perform_create(self, serializer):
        """Create a new review for authenticated user"""
        serializer.save(customer=self.request.user.customer)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_reviews(self, request):
        """Get all reviews by the current user"""
        reviews = Review.objects.filter(
            customer=request.user.customer
        ).select_related('customer__user', 'product')
        
        # Paginate user's reviews
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(reviews, request)
        serializer = self.get_serializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)