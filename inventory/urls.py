from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    WarehouseViewSet, WarehouseStockViewSet, StockMovementViewSet,
    InventoryTransferViewSet, StockAlertViewSet, StockCountViewSet,
    InventoryAnalyticsView, BulkInventoryOperationsView
)

router = DefaultRouter()
router.register(r'warehouses', WarehouseViewSet, basename='warehouse')
router.register(r'stock', WarehouseStockViewSet, basename='warehouse-stock')
router.register(r'movements', StockMovementViewSet, basename='stock-movement')
router.register(r'transfers', InventoryTransferViewSet, basename='inventory-transfer')
router.register(r'alerts', StockAlertViewSet, basename='stock-alert')
router.register(r'counts', StockCountViewSet, basename='stock-count')

urlpatterns = [
    path('', include(router.urls)),
    path('analytics/', InventoryAnalyticsView.as_view(), name='inventory-analytics'),
    path('bulk-operations/', BulkInventoryOperationsView.as_view(), name='bulk-operations'),
]