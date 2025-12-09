from rest_framework import permissions


class IsWarehouseManager(permissions.BasePermission):
    """Allow warehouse managers to manage their warehouse"""
    
    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        
        # Check if user is manager of the warehouse
        if hasattr(obj, 'warehouse'):
            return obj.warehouse.manager == request.user
        elif hasattr(obj, 'managed_warehouses'):
            return obj.manager == request.user
        
        return False


class CanApproveTransfer(permissions.BasePermission):
    """Only staff or destination warehouse manager can approve"""
    
    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        
        # Destination warehouse manager can approve
        return obj.to_warehouse.manager == request.user


class CanShipTransfer(permissions.BasePermission):
    """Only staff or source warehouse manager can ship"""
    
    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        
        # Source warehouse manager can ship
        return obj.from_warehouse.manager == request.user