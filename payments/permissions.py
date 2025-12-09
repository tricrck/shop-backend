from rest_framework import permissions

class IsTransactionOwnerOrAdmin(permissions.BasePermission):
    """
    Permission to only allow owners of a transaction or admins to access it
    """
    
    def has_object_permission(self, request, view, obj):
        # Admin users have full access
        if request.user.is_staff:
            return True
        
        # Check if user owns the transaction
        if hasattr(obj, 'customer') and obj.customer:
            return obj.customer.user == request.user
        
        # Check if user owns the order
        if hasattr(obj, 'order') and obj.order:
            return obj.order.customer.user == request.user
        
        return False


class CanInitiatePayment(permissions.BasePermission):
    """
    Permission to initiate payment
    """
    
    def has_permission(self, request, view):
        return request.user.is_authenticated
