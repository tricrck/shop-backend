from rest_framework import permissions


class IsOrderOwner(permissions.BasePermission):
    """Only allow order owner to access"""
    def has_object_permission(self, request, view, obj):
        return obj.customer.user == request.user


class IsOrderOwnerOrAdmin(permissions.BasePermission):
    """Allow order owner or admin staff"""
    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        return obj.customer.user == request.user


class CanModifyOrder(permissions.BasePermission):
    """Check if order can be modified based on status"""
    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        
        # Customers can only modify pending orders
        if obj.status == 'pending':
            return True
        
        # Customers can cancel orders in certain statuses
        if request.method in ['DELETE', 'PATCH'] and obj.status in ['pending', 'confirmed']:
            return True
        
        return False


class CanCreateReturn(permissions.BasePermission):
    """Check if return can be created for order"""
    def has_object_permission(self, request, view, obj):
        if not obj.status == 'delivered':
            return False
        
        # Check if within return window (e.g., 30 days)
        from django.utils import timezone
        days_since_delivery = (timezone.now() - obj.delivered_date).days
        return days_since_delivery <= 30


class OrderActionPermission(permissions.BasePermission):
    """Permission based on order action"""
    def has_permission(self, request, view):
        if view.action == 'create':
            return True  # Anyone can create order
        
        if request.user.is_authenticated:
            return True
        
        return False
    
    def has_object_permission(self, request, view, obj):
        if view.action in ['retrieve', 'update', 'partial_update', 'destroy']:
            return IsOrderOwnerOrAdmin().has_object_permission(request, view, obj)
        
        if view.action in ['cancel', 'return']:
            return CanModifyOrder().has_object_permission(request, view, obj)
        
        return False