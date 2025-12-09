from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'configurations', views.MpesaConfigurationViewSet, basename='mpesa-configuration')
router.register(r'transactions', views.MpesaTransactionViewSet, basename='mpesa-transaction')
router.register(r'refunds', views.MpesaRefundViewSet, basename='mpesa-refund')
router.register(r'payment-methods', views.MpesaPaymentMethodViewSet, basename='mpesa-payment-method')

urlpatterns = [
    # Router URLs
    path('', include(router.urls)),
    
    # Payment initiation and status
    path('initiate/', views.InitiatePaymentView.as_view(), name='mpesa-initiate'),
    path('check-status/', views.CheckPaymentStatusView.as_view(), name='mpesa-check-status'),
    
    # Webhooks (must be publicly accessible)
    path('callback/', views.mpesa_callback, name='mpesa-callback'),
    path('timeout/', views.mpesa_timeout, name='mpesa-timeout'),
    path('validation/', views.mpesa_validation, name='mpesa-validation'),
    path('confirmation/', views.mpesa_confirmation, name='mpesa-confirmation'),
    
    # Admin actions
    path('process-refund/', views.ProcessRefundView.as_view(), name='mpesa-process-refund'),
]
