from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Avg, Count
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from .models import Category, Brand, Product, ProductImage, Review
from .serializers import (CategorySerializer, BrandSerializer, ProductListSerializer, 
                          ProductDetailSerializer, ProductImageSerializer, ReviewSerializer)
from .filters import ProductFilter
from .permissions import IsAdminOrReadOnly

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'description']

    @method_decorator(cache_page(60 * 15))
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @action(detail=True, methods=['get'])
    def products(self, request, slug=None):
        category = self.get_object()
        products = Product.objects.filter(category=category, is_active=True)
        serializer = ProductListSerializer(products, many=True)
        return Response(serializer.data)


class BrandViewSet(viewsets.ModelViewSet):
    queryset = Brand.objects.filter(is_active=True)
    serializer_class = BrandSerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']

    @method_decorator(cache_page(60 * 15))
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.filter(is_active=True).prefetch_related('images', 'reviews')
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ['name', 'description', 'sku', 'brand__name']
    ordering_fields = ['price', 'created_at', 'name', 'stock_quantity']

    def get_serializer_class(self):
        if self.action == 'list':
            return ProductListSerializer
        return ProductDetailSerializer

    @method_decorator(cache_page(60 * 5))
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def featured(self, request):
        products = self.queryset.filter(is_featured=True)[:10]
        serializer = ProductListSerializer(products, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        products = Product.objects.filter(
            stock_quantity__lte=models.F('low_stock_threshold'),
            is_active=True
        )
        serializer = ProductListSerializer(products, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def add_image(self, request, slug=None):
        product = self.get_object()
        serializer = ProductImageSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(product=product)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ReviewViewSet(viewsets.ModelViewSet):
    queryset = Review.objects.filter(is_approved=True)
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at', 'rating']
    ordering = ['-created_at']

    def perform_create(self, serializer):
        serializer.save(customer=self.request.user.customer)