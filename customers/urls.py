from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RegisterView,
    LogoutView,
    CustomerProfileView,
    UpdateProfileView,
    ChangePasswordView,
    AddressViewSet,
    CustomerViewSet,
    PasswordResetRequestView,
    PasswordResetCodeVerifyView,
    PasswordResetConfirmView
)

router = DefaultRouter()
router.register(r'addresses', AddressViewSet, basename='address')
router.register(r'all', CustomerViewSet, basename='customer')

urlpatterns = [
    # Authentication endpoints
    path('register/', RegisterView.as_view(), name='customer-register'),
    path('logout/', LogoutView.as_view(), name='customer-logout'),
    
    # Profile management
    path('profile/', CustomerProfileView.as_view(), name='customer-profile'),
    path('profile/update/', UpdateProfileView.as_view(), name='customer-update'),
    path('password/change/', ChangePasswordView.as_view(), name='customer-change-password'),

    # Password reset endpoints
    path('password/reset/', PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('password/reset/verify/', PasswordResetCodeVerifyView.as_view(), name='password-reset-verify'),
    path('password/reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    
    # Router URLs (addresses and customer list)
    path('', include(router.urls)),
]