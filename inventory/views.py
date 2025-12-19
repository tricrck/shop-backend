from rest_framework import viewsets, status, filters, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Sum, F, Q, Count, Avg, Max, Min
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone
from django.http import HttpResponse
from django.core.cache import cache
from datetime import datetime, timedelta
import csv

from .models import (
    Warehouse, WarehouseStock, StockMovement, InventoryTransfer,
    TransferItem, StockAlert, StockCount, StockCountItem
)
from .serializers import (
    WarehouseSerializer, WarehouseStockSerializer, StockMovementSerializer,
    StockMovementCreateSerializer, InventoryTransferSerializer,
    InventoryTransferCreateSerializer, StockAlertSerializer,
    StockCountSerializer, StockCountCreateSerializer, StockCountItemSerializer,
    BulkStockUpdateSerializer
)
from products.models import Product


class WarehouseViewSet(viewsets.ModelViewSet):
    """Complete Warehouse Management"""
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'is_primary', 'town', 'county', 'country']
    search_fields = ['name', 'code', 'street_address', 'town']
    ordering_fields = ['name', 'priority', 'created_at']
    ordering = ['-priority', 'name']
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsAdminUser()]
    
    @action(detail=True, methods=['get'])
    def inventory(self, request, pk=None):
        """Get all inventory for a warehouse"""
        warehouse = self.get_object()
        stock = WarehouseStock.objects.filter(
            warehouse=warehouse
        ).select_related('product', 'product__category', 'product__brand')
        
        # Filters
        low_stock = request.GET.get('low_stock')
        if low_stock == 'true':
            stock = stock.filter(quantity__lte=F('reorder_point'))
        
        out_of_stock = request.GET.get('out_of_stock')
        if out_of_stock == 'true':
            stock = stock.filter(quantity=0)
        
        serializer = WarehouseStockSerializer(stock, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get warehouse statistics"""
        warehouse = self.get_object()
        
        stock_data = WarehouseStock.objects.filter(warehouse=warehouse).aggregate(
            total_items=Count('id'),
            total_quantity=Sum('quantity'),
            total_reserved=Sum('reserved_quantity'),
            total_damaged=Sum('damaged_quantity'),
            low_stock_count=Count('id', filter=Q(quantity__lte=F('reorder_point'))),
            out_of_stock_count=Count('id', filter=Q(quantity=0))
        )
        
        movements_today = StockMovement.objects.filter(
            warehouse=warehouse,
            created_at__date=timezone.now().date()
        ).count()
        
        alerts_unresolved = StockAlert.objects.filter(
            warehouse=warehouse,
            is_resolved=False
        ).count()
        
        return Response({
            'warehouse': WarehouseSerializer(warehouse).data,
            'inventory': stock_data,
            'movements_today': movements_today,
            'alerts_unresolved': alerts_unresolved,
            'capacity_usage': warehouse.capacity_percentage
        })
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def set_primary(self, request, pk=None):
        """Set as primary warehouse"""
        warehouse = self.get_object()
        warehouse.is_primary = True
        warehouse.save()
        return Response({'message': f'{warehouse.name} set as primary warehouse'})


class WarehouseStockViewSet(viewsets.ModelViewSet):
    """Warehouse Stock Management"""
    queryset = WarehouseStock.objects.select_related(
        'warehouse', 'product', 'product__category', 'product__brand'
    ).all()
    serializer_class = WarehouseStockSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['warehouse', 'product']
    search_fields = ['product__name', 'product__sku', 'location', 'zone']
    ordering_fields = ['quantity', 'updated_at']
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsAdminUser()]
    
    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        """Get all low stock items across warehouses"""
        stock = self.get_queryset().annotate(
            available=F('quantity') - F('reserved_quantity') - F('damaged_quantity')
        ).filter(available__lte=F('reorder_point'))
        
        page = self.paginate_queryset(stock)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(stock, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def out_of_stock(self, request):
        """Get all out of stock items"""
        stock = self.get_queryset().filter(quantity=0)
        serializer = self.get_serializer(stock, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def reorder_suggestions(self, request):
        """Get items that need reordering"""
        stock = self.get_queryset().filter(
            Q(quantity__lte=F('reorder_point')) & Q(reorder_quantity__gt=0)
        ).select_related('product')
        
        suggestions = []
        for item in stock:
            suggestions.append({
                'warehouse': item.warehouse.name,
                'product': item.product.name,
                'sku': item.product.sku,
                'current_quantity': item.quantity,
                'reorder_point': item.reorder_point,
                'suggested_order_quantity': item.reorder_quantity,
                'available_quantity': item.available_quantity
            })
        
        return Response(suggestions)
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def adjust_stock(self, request, pk=None):
        """Manually adjust stock level"""
        warehouse_stock = self.get_object()
        adjustment = request.data.get('adjustment')
        reason = request.data.get('reason', 'Manual adjustment')
        
        if adjustment is None:
            return Response(
                {'error': 'adjustment is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            adjustment = int(adjustment)
        except ValueError:
            return Response(
                {'error': 'adjustment must be an integer'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create stock movement
        quantity_before = warehouse_stock.quantity
        warehouse_stock.quantity += adjustment
        warehouse_stock.save()
        
        StockMovement.objects.create(
            warehouse=warehouse_stock.warehouse,
            product=warehouse_stock.product,
            movement_type='adjustment',
            quantity=adjustment,
            quantity_before=quantity_before,
            quantity_after=warehouse_stock.quantity,
            notes=reason,
            created_by=request.user
        )
        
        return Response({
            'message': 'Stock adjusted successfully',
            'new_quantity': warehouse_stock.quantity
        })
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def reserve(self, request, pk=None):
        """Reserve stock for an order"""
        warehouse_stock = self.get_object()
        quantity = request.data.get('quantity')
        
        if not quantity or int(quantity) <= 0:
            return Response(
                {'error': 'Valid quantity is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        quantity = int(quantity)
        
        if warehouse_stock.reserve_stock(quantity):
            return Response({
                'message': f'Reserved {quantity} units',
                'reserved_quantity': warehouse_stock.reserved_quantity,
                'available_quantity': warehouse_stock.available_quantity
            })
        else:
            return Response(
                {'error': 'Insufficient stock to reserve'},
                status=status.HTTP_400_BAD_REQUEST
            )


class StockMovementViewSet(viewsets.ModelViewSet):
    """Stock Movement Tracking"""
    queryset = StockMovement.objects.select_related(
        'warehouse', 'product', 'created_by'
    ).all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['warehouse', 'product', 'movement_type', 'created_by']
    search_fields = ['movement_number', 'product__name', 'product__sku', 'notes']
    ordering_fields = ['created_at', 'movement_date', 'quantity']
    ordering = ['-created_at']
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return StockMovementCreateSerializer
        return StockMovementSerializer
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsAdminUser()]
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get movement summary"""
        # Date range
        days = int(request.GET.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)
        
        movements = self.get_queryset().filter(created_at__gte=start_date)
        
        summary = movements.values('movement_type').annotate(
            count=Count('id'),
            total_quantity=Sum('quantity')
        )
        
        by_date = movements.annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(
            count=Count('id'),
            total_in=Sum('quantity', filter=Q(quantity__gt=0)),
            total_out=Sum('quantity', filter=Q(quantity__lt=0))
        ).order_by('date')
        
        return Response({
            'by_type': list(summary),
            'by_date': list(by_date),
            'period_days': days
        })
    
    @action(detail=False, methods=['get'], permission_classes=[IsAdminUser])
    def export(self, request):
        """Export movements to CSV"""
        movements = self.filter_queryset(self.get_queryset())
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="stock_movements_{timezone.now().date()}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Movement Number', 'Date', 'Warehouse', 'Product SKU', 'Product Name',
            'Type', 'Quantity', 'Before', 'After', 'Unit Cost', 'Total Cost',
            'Reference', 'Notes', 'Created By'
        ])
        
        for movement in movements:
            writer.writerow([
                movement.movement_number,
                movement.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                movement.warehouse.code,
                movement.product.sku,
                movement.product.name,
                movement.get_movement_type_display(),
                movement.quantity,
                movement.quantity_before,
                movement.quantity_after,
                movement.unit_cost or '',
                movement.total_cost or '',
                f"{movement.reference_type}:{movement.reference_id}" if movement.reference_type else '',
                movement.notes,
                movement.created_by.get_full_name()
            ])
        
        return response


class InventoryTransferViewSet(viewsets.ModelViewSet):
    """Warehouse Transfer Management"""
    queryset = InventoryTransfer.objects.select_related(
        'from_warehouse', 'to_warehouse', 'requested_by'
    ).prefetch_related('items', 'items__product').all()
    serializer_class = InventoryTransferSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'from_warehouse', 'to_warehouse']
    search_fields = ['transfer_number', 'tracking_number']
    ordering_fields = ['requested_at', 'status']
    ordering = ['-requested_at']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return InventoryTransferCreateSerializer
        return InventoryTransferSerializer
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsAdminUser()]
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def approve(self, request, pk=None):
        """Approve transfer request"""
        transfer = self.get_object()
        
        if transfer.approve_transfer(request.user):
            return Response({
                'message': 'Transfer approved successfully',
                'transfer': InventoryTransferSerializer(transfer).data
            })
        else:
            return Response(
                {'error': 'Transfer cannot be approved in current status'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def ship(self, request, pk=None):
        """Mark transfer as shipped"""
        transfer = self.get_object()
        tracking_number = request.data.get('tracking_number')
        
        if transfer.ship_transfer(request.user, tracking_number):
            return Response({
                'message': 'Transfer shipped successfully',
                'transfer': InventoryTransferSerializer(transfer).data
            })
        else:
            return Response(
                {'error': 'Transfer cannot be shipped in current status'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def receive(self, request, pk=None):
        """Mark transfer as received"""
        transfer = self.get_object()
        received_items = request.data.get('items', {})
        
        if transfer.receive_transfer(request.user, received_items):
            return Response({
                'message': 'Transfer received successfully',
                'transfer': InventoryTransferSerializer(transfer).data
            })
        else:
            return Response(
                {'error': 'Transfer cannot be received in current status'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def cancel(self, request, pk=None):
        """Cancel transfer"""
        transfer = self.get_object()
        reason = request.data.get('reason', '')
        
        if transfer.status not in ['draft', 'pending']:
            return Response(
                {'error': 'Only draft or pending transfers can be cancelled'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Release reserved stock if it was approved
        if transfer.status == 'pending':
            for item in transfer.items.all():
                warehouse_stock = WarehouseStock.objects.get(
                    warehouse=transfer.from_warehouse,
                    product=item.product
                )
                warehouse_stock.release_reservation(item.quantity)
        
        transfer.status = 'cancelled'
        transfer.rejection_reason = reason
        transfer.save()
        
        return Response({
            'message': 'Transfer cancelled successfully',
            'transfer': InventoryTransferSerializer(transfer).data
        })


class StockAlertViewSet(viewsets.ModelViewSet):
    """Stock Alert Management"""
    queryset = StockAlert.objects.select_related(
        'warehouse', 'product', 'resolved_by'
    ).all()
    serializer_class = StockAlertSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['alert_type', 'priority', 'warehouse', 'is_resolved']
    ordering_fields = ['created_at', 'priority']
    ordering = ['-priority', '-created_at']
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsAdminUser()]
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def resolve(self, request, pk=None):
        """Resolve an alert"""
        alert = self.get_object()
        notes = request.data.get('notes', '')
        
        alert.resolve(request.user, notes)
        
        return Response({
            'message': 'Alert resolved successfully',
            'alert': StockAlertSerializer(alert).data
        })
    
    @action(detail=False, methods=['get'])
    def unresolved(self, request):
        """Get all unresolved alerts"""
        alerts = self.get_queryset().filter(is_resolved=False)
        serializer = self.get_serializer(alerts, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def critical(self, request):
        """Get critical unresolved alerts"""
        alerts = self.get_queryset().filter(
            is_resolved=False,
            priority='critical'
        )
        serializer = self.get_serializer(alerts, many=True)
        return Response(serializer.data)


class StockCountViewSet(viewsets.ModelViewSet):
    """Stock Count Management"""
    queryset = StockCount.objects.select_related(
        'warehouse', 'assigned_to', 'completed_by'
    ).prefetch_related('items', 'items__product').all()
    serializer_class = StockCountSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['warehouse', 'status', 'count_type', 'assigned_to']
    ordering_fields = ['scheduled_date', 'created_at']
    ordering = ['-scheduled_date']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return StockCountCreateSerializer
        return StockCountSerializer
    
    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """Start a stock count"""
        stock_count = self.get_object()
        
        if stock_count.status != 'scheduled':
            return Response(
                {'error': 'Only scheduled counts can be started'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        stock_count.status = 'in_progress'
        stock_count.started_at = timezone.now()
        stock_count.save()
        
        return Response({
            'message': 'Stock count started',
            'count': StockCountSerializer(stock_count).data
        })
    
    @action(detail=True, methods=['post'])
    def record_count(self, request, pk=None):
        """Record counted quantity for an item"""
        stock_count = self.get_object()
        item_id = request.data.get('item_id')
        counted_quantity = request.data.get('counted_quantity')
        notes = request.data.get('notes', '')
        
        if not item_id or counted_quantity is None:
            return Response(
                {'error': 'item_id and counted_quantity are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            item = StockCountItem.objects.get(
                id=item_id,
                stock_count=stock_count
            )
            
            item.counted_quantity = int(counted_quantity)
            item.notes = notes
            item.counted_by = request.user
            item.counted_at = timezone.now()
            item.save()
            
            return Response({
                'message': 'Count recorded successfully',
                'item': StockCountItemSerializer(item).data
            })
        except StockCountItem.DoesNotExist:
            return Response(
                {'error': 'Item not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Complete stock count and apply adjustments"""
        stock_count = self.get_object()
        
        if stock_count.status != 'in_progress':
            return Response(
                {'error': 'Only in-progress counts can be completed'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if all items are counted
        uncounted = stock_count.items.filter(is_counted=False).count()
        if uncounted > 0:
            return Response(
                {'error': f'{uncounted} items still need to be counted'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Apply adjustments for discrepancies
        apply_adjustments = request.data.get('apply_adjustments', True)
        
        if apply_adjustments:
            for item in stock_count.items.filter(has_discrepancy=True):
                warehouse_stock = WarehouseStock.objects.get(
                    warehouse=stock_count.warehouse,
                    product=item.product
                )
                
                quantity_before = warehouse_stock.quantity
                warehouse_stock.quantity = item.counted_quantity
                warehouse_stock.last_counted = timezone.now()
                warehouse_stock.save()
                
                # Create stock movement
                StockMovement.objects.create(
                    warehouse=stock_count.warehouse,
                    product=item.product,
                    movement_type='adjustment',
                    quantity=item.discrepancy,
                    quantity_before=quantity_before,
                    quantity_after=warehouse_stock.quantity,
                    reference_type='stock_count',
                    reference_id=str(stock_count.id),
                    notes=f"Stock count adjustment: {stock_count.count_number}",
                    created_by=request.user
                )
        
        stock_count.status = 'completed'
        stock_count.completed_at = timezone.now()
        stock_count.completed_by = request.user
        stock_count.save()
        
        return Response({
            'message': 'Stock count completed successfully',
            'count': StockCountSerializer(stock_count).data,
            'adjustments_applied': apply_adjustments,
            'discrepancies': stock_count.discrepancy_count
        })


# Analytics and Reporting Views
class InventoryAnalyticsView(APIView):
    """Comprehensive Inventory Analytics"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        period = request.GET.get('period', 'month')  # day, week, month, year
        warehouse_id = request.GET.get('warehouse')
        
        # Base queryset
        stock_qs = WarehouseStock.objects.all()
        if warehouse_id:
            stock_qs = stock_qs.filter(warehouse_id=warehouse_id)
        
        # Current inventory value
        inventory_value = stock_qs.annotate(
            value=F('quantity') * F('product__cost_price')
        ).aggregate(total=Sum('value'))['total'] or 0
        
        # Stock levels
        stock_levels = {
            'total_products': stock_qs.count(),
            'total_quantity': stock_qs.aggregate(Sum('quantity'))['quantity__sum'] or 0,
            'low_stock': stock_qs.filter(quantity__lte=F('reorder_point')).count(),
            'out_of_stock': stock_qs.filter(quantity=0).count(),
            'reserved': stock_qs.aggregate(Sum('reserved_quantity'))['reserved_quantity__sum'] or 0,
            'damaged': stock_qs.aggregate(Sum('damaged_quantity'))['damaged_quantity__sum'] or 0,
        }
        
        # Movement trends
        days_map = {'day': 1, 'week': 7, 'month': 30, 'year': 365}
        days = days_map.get(period, 30)
        start_date = timezone.now() - timedelta(days=days)
        
        movements = StockMovement.objects.filter(created_at__gte=start_date)
        if warehouse_id:
            movements = movements.filter(warehouse_id=warehouse_id)
        
        movement_summary = movements.values('movement_type').annotate(
            count=Count('id'),
            total_quantity=Sum('quantity')
        )
        
        # Top products by movement
        top_products = movements.values(
            'product__name', 'product__sku'
        ).annotate(
            movement_count=Count('id'),
            total_moved=Sum('quantity')
        ).order_by('-movement_count')[:10]
        
        # Turnover rate (simplified)
        sales_movements = movements.filter(movement_type='sale')
        avg_inventory = stock_levels['total_quantity']
        if avg_inventory > 0:
            turnover_rate = abs(sales_movements.aggregate(Sum('quantity'))['quantity__sum'] or 0) / avg_inventory
        else:
            turnover_rate = 0
        
        # Alerts
        alerts_summary = StockAlert.objects.filter(
            is_resolved=False
        ).values('alert_type', 'priority').annotate(count=Count('id'))
        
        return Response({
            'inventory_value': float(inventory_value),
            'stock_levels': stock_levels,
            'movement_summary': list(movement_summary),
            'top_products': list(top_products),
            'turnover_rate': round(turnover_rate, 2),
            'alerts': list(alerts_summary),
            'period': period
        })


class BulkInventoryOperationsView(APIView):
    """Bulk Inventory Operations"""
    permission_classes = [IsAdminUser]
    
    def post(self, request):
        """Bulk update stock levels"""
        serializer = BulkStockUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        updates = serializer.validated_data['updates']
        results = []
        
        for update in updates:
            try:
                warehouse = Warehouse.objects.get(id=update['warehouse_id'])
                product = Product.objects.get(id=update['product_id'])
                
                warehouse_stock, created = WarehouseStock.objects.get_or_create(
                    warehouse=warehouse,
                    product=product,
                    defaults={'quantity': 0}
                )
                
                quantity_before = warehouse_stock.quantity
                new_quantity = update['quantity']
                adjustment = new_quantity - quantity_before
                
                warehouse_stock.quantity = new_quantity
                warehouse_stock.save()
                
                # Create movement record
                StockMovement.objects.create(
                    warehouse=warehouse,
                    product=product,
                    movement_type='adjustment',
                    quantity=adjustment,
                    quantity_before=quantity_before,
                    quantity_after=new_quantity,
                    notes='Bulk update',
                    created_by=request.user
                )
                
                results.append({
                    'product_id': product.id,
                    'warehouse_id': warehouse.id,
                    'status': 'success',
                    'old_quantity': quantity_before,
                    'new_quantity': new_quantity
                })
            except Exception as e:
                results.append({
                    'product_id': update.get('product_id'),
                    'warehouse_id': update.get('warehouse_id'),
                    'status': 'error',
                    'error': str(e)
                })
        
        return Response({
            'message': 'Bulk update completed',
            'results': results,
            'successful': len([r for r in results if r['status'] == 'success']),
            'failed': len([r for r in results if r['status'] == 'error'])
        })