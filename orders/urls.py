from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    OrderViewSet, OrderItemViewSet, ShippingMethodViewSet,
    OrderReturnViewSet, OrderNoteViewSet, OrderAnalyticsView,
    PublicOrderStatusView, shipping_webhook
)

router = DefaultRouter()
router.register(r'orders', OrderViewSet, basename='order')
router.register(r'order-items', OrderItemViewSet, basename='orderitem')
router.register(r'shipping-methods', ShippingMethodViewSet, basename='shippingmethod')
router.register(r'returns', OrderReturnViewSet, basename='orderreturn')

# Nested routes for order notes
order_notes_router = DefaultRouter()
order_notes_router.register(r'notes', OrderNoteViewSet, basename='ordernote')

urlpatterns = [
    path('', include(router.urls)),
    path('orders/<int:order_pk>/', include(order_notes_router.urls)),
    path('analytics/', OrderAnalyticsView.as_view(), name='order-analytics'),
    path('public/status/', PublicOrderStatusView.as_view(), name='public-order-status'),
    path('webhook/shipping/<str:carrier>/', shipping_webhook, name='shipping-webhook'),
]