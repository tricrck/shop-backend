from rest_framework import viewsets, status, generics, filters, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Sum, Count, Avg, F, Value
from django.db.models.functions import TruncDate, TruncMonth, TruncYear
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.core.cache import cache
from datetime import datetime, timedelta
import csv
import json
from products.models import Product
from .models import (
    Order, OrderItem, OrderStatusHistory, ShippingMethod, 
    OrderReturn, ReturnItem, OrderNote
)
from .serializers import (
    OrderListSerializer, OrderDetailSerializer, OrderCreateSerializer,
    OrderUpdateSerializer, OrderCancelSerializer, OrderItemSerializer,
    OrderStatusHistorySerializer, ShippingMethodSerializer,
    OrderReturnSerializer, ReturnCreateSerializer, ReturnItemSerializer,
    OrderNoteSerializer, ShippingQuoteSerializer
)
from .filters import OrderFilter, OrderReturnFilter
from .permissions import IsOrderOwnerOrAdmin, CanModifyOrder, CanCreateReturn
from .tasks import send_order_confirmation_email, update_order_status_task
from .notifications import send_order_confirmation
from payments.services import MpesaPaymentService


class OrderViewSet(viewsets.ModelViewSet):
    """
    Order Management ViewSet
    """
    queryset = Order.objects.select_related(
        'customer', 'customer__user', 
        'billing_address', 'shipping_address'
    ).prefetch_related(
        'items', 'items__product', 'status_history'
    ).all()

    lookup_field = 'order_number'
    lookup_value_regex = '[^/]+'
    
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = OrderFilter
    search_fields = ['order_number', 'customer__user__email', 
                    'customer__user__first_name', 'customer__user__last_name',
                    'tracking_number']
    ordering_fields = ['created_at', 'updated_at', 'total', 'status']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return OrderCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return OrderUpdateSerializer
        elif self.action == 'list':
            return OrderListSerializer
        return OrderDetailSerializer
    
    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()]  # Allow guest checkout
        elif self.action in ['list', 'retrieve']:
            return [IsOrderOwnerOrAdmin()]
        elif self.action in ['update', 'partial_update', 'destroy']:
            return [IsAdminUser()]  # Only admins can modify orders
        elif self.action in ['cancel', 'return']:
            return [IsOrderOwnerOrAdmin()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Non-staff users can only see their own orders
        if not self.request.user.is_staff:
            if self.request.user.is_authenticated:
                queryset = queryset.filter(customer__user=self.request.user)
            else:
                # For guest orders, check session or token
                guest_email = self.request.GET.get('guest_email')
                guest_token = self.request.GET.get('guest_token')
                if guest_email:
                    queryset = queryset.filter(guest_email=guest_email, is_guest=True)
                else:
                    queryset = queryset.none()
        
        return queryset
    
    def create(self, request, *args, **kwargs):
        """Create a new order (supports guest checkout)"""
        serializer = self.get_serializer(data=request.data)
        
        # Check if serializer is valid
        if not serializer.is_valid():
            print("Validation errors:", serializer.errors)
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            order = serializer.save()

            # Check if M-Pesa payment should be initiated
            payment_method = request.data.get('payment_method')
            payment_number = request.data.get('payment_number')
            
            if payment_method == 'MPesa' and payment_number:
                try:
                    # Initiate M-Pesa payment
                    service = MpesaPaymentService()
                    transaction = service.initiate_order_payment(order, payment_number)
                    
                    # Store transaction reference in order if needed
                    order.mpesa_transaction_id = transaction.id
                    order.mpesa_checkout_request_id = transaction.checkout_request_id
                    order.save()
                    
                except Exception as mpesa_error:
                    print(f"M-Pesa initiation error: {str(mpesa_error)}")
                    # You might want to handle this differently - maybe mark order as pending payment
                    # For now, we'll just log the error and continue
                    import traceback
                    traceback.print_exc()
            
            # Send confirmation email (async)
            try:
                send_order_confirmation(order)
            except:
                print("Warning: Could not send confirmation email")
            
            return Response(
                OrderDetailSerializer(order, context=self.get_serializer_context()).data,
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            print("Error creating order:", str(e))
            import traceback
            traceback.print_exc()
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel an order"""
        order = self.get_object()
        serializer = OrderCancelSerializer(data=request.data, context={'order': order})
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        
        try:
            # Update order status
            old_status = order.status
            order.status = 'cancelled'
            order.cancelled_at = timezone.now()
            
            # Process refund if specified
            if data.get('refund_amount'):
                order.payment_status = 'refunded'
                order.refunded_at = timezone.now()
                # Here you would integrate with payment gateway
            
            order.save()
            
            # Restock items if requested
            if data.get('restock_items', True):
                for item in order.items.all():
                    item.product.stock_quantity += item.quantity
                    item.product.save()
            
            # Create status history
            OrderStatusHistory.objects.create(
                order=order,
                old_status=old_status,
                new_status='cancelled',
                changed_by=request.user,
                notes=data.get('reason', 'Order cancelled by customer'),
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            return Response({
                'message': 'Order cancelled successfully',
                'order': OrderDetailSerializer(order).data
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update order status (admin only)"""
        if not request.user.is_staff:
            return Response(
                {'error': 'Only admins can update order status'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        order = self.get_object()
        new_status = request.data.get('status')
        notes = request.data.get('notes', '')
        
        if not new_status:
            return Response(
                {'error': 'Status is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if new_status not in dict(Order.ORDER_STATUS):
            return Response(
                {'error': 'Invalid status'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        old_status = order.status
        order.status = new_status
        
        # Update timestamps based on status
        if new_status == 'shipped' and not order.shipped_date:
            order.shipped_date = timezone.now()
        elif new_status == 'delivered' and not order.delivered_date:
            order.delivered_date = timezone.now()
        
        order.save()
        
        # Create status history
        OrderStatusHistory.objects.create(
            order=order,
            old_status=old_status,
            new_status=new_status,
            changed_by=request.user,
            notes=notes,
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        # Trigger async tasks based on status
        update_order_status_task.delay(order.id, old_status, new_status)
        
        return Response({
            'message': f'Order status updated from {old_status} to {new_status}',
            'order': OrderDetailSerializer(order).data
        })
    
    @action(detail=True, methods=['post'])
    def add_tracking(self, request, pk=None):
        """Add tracking information to order"""
        if not request.user.is_staff:
            return Response(
                {'error': 'Only admins can add tracking'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        order = self.get_object()
        tracking_number = request.data.get('tracking_number')
        carrier = request.data.get('carrier')
        tracking_url = request.data.get('tracking_url')
        
        if not tracking_number or not carrier:
            return Response(
                {'error': 'Tracking number and carrier are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        order.tracking_number = tracking_number
        order.carrier = carrier
        order.tracking_url = tracking_url
        order.status = 'shipped'
        order.shipped_date = timezone.now()
        order.save()
        
        # Create status history
        OrderStatusHistory.objects.create(
            order=order,
            old_status='processing',
            new_status='shipped',
            changed_by=request.user,
            notes=f'Tracking added: {carrier} - {tracking_number}',
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return Response({
            'message': 'Tracking information added successfully',
            'order': OrderDetailSerializer(order).data
        })
    
    @action(detail=True, methods=['get'])
    def tracking_info(self, request, pk=None):
        """Get tracking information for an order"""
        order = self.get_object()
        
        if not order.tracking_number:
            return Response(
                {'error': 'No tracking information available'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # In a real app, you would integrate with carrier API
        tracking_info = {
            'tracking_number': order.tracking_number,
            'carrier': order.carrier,
            'tracking_url': order.tracking_url,
            'status': order.status,
            'shipped_date': order.shipped_date,
            'estimated_delivery': order.estimated_delivery,
            'last_update': order.updated_at
        }
        
        # Simulate carrier API response
        if order.status == 'shipped':
            tracking_info['events'] = [
                {
                    'date': order.shipped_date,
                    'location': 'Warehouse',
                    'description': 'Package picked up by carrier'
                },
                {
                    'date': order.shipped_date + timedelta(hours=2),
                    'location': 'Sorting Facility',
                    'description': 'Package in transit'
                }
            ]
        elif order.status == 'delivered':
            tracking_info['events'] = [
                {
                    'date': order.delivered_date,
                    'location': order.shipping_address.city if order.shipping_address else '',
                    'description': 'Package delivered'
                }
            ]
        
        return Response(tracking_info)
    
    @action(detail=False, methods=['get'])
    def my_orders(self, request):
        """Get current user's orders"""
        try:
            if not request.user.is_authenticated:
                return Response(
                    {'error': 'Authentication required'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # Check if user has a customer profile
            try:
                customer = request.user.customer
            except Exception as e:
                print(f"ERROR: User has no customer profile: {e}")
                return Response(
                    {'error': 'User does not have a customer profile', 'detail': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get orders
            try:
                orders = self.get_queryset().filter(customer__user=request.user)
            except Exception as e:
                print(f"ERROR querying orders: {e}")
                import traceback
                traceback.print_exc()
                return Response(
                    {'error': 'Error querying orders', 'detail': str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # Paginate
            try:
                page = self.paginate_queryset(orders)
                
                if page is not None:
                    serializer = OrderListSerializer(page, many=True)
                    return self.get_paginated_response(serializer.data)
                
                serializer = OrderListSerializer(orders, many=True)
                return Response(serializer.data)
            except Exception as e:
                print(f"ERROR during serialization/pagination: {e}")
                import traceback
                traceback.print_exc()
                return Response(
                    {'error': 'Error serializing orders', 'detail': str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
                
        except Exception as e:
            print(f"UNEXPECTED ERROR in my_orders: {e}")
            import traceback
            traceback.print_exc()
            return Response(
                {'error': 'Unexpected error', 'detail': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def recent(self, request):
        """Get recent orders (last 30 days)"""
        cutoff_date = timezone.now() - timedelta(days=30)
        orders = self.get_queryset().filter(created_at__gte=cutoff_date)
        
        serializer = OrderListSerializer(orders, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], permission_classes=[IsAdminUser])
    def stats(self, request):
        """Get order statistics (admin only)"""
        # Try cache first
        cache_key = f'order_stats_{timezone.now().date()}'
        cached_stats = cache.get(cache_key)
        
        if cached_stats:
            return Response(cached_stats)
        
        # Calculate stats
        today = timezone.now().date()
        thirty_days_ago = today - timedelta(days=30)
        
        stats = {
            'total_orders': Order.objects.count(),
            'total_revenue': Order.objects.aggregate(total=Sum('total'))['total'] or 0,
            'today': {
                'orders': Order.objects.filter(created_at__date=today).count(),
                'revenue': Order.objects.filter(created_at__date=today).aggregate(
                    total=Sum('total')
                )['total'] or 0
            },
            'last_30_days': {
                'orders': Order.objects.filter(created_at__date__gte=thirty_days_ago).count(),
                'revenue': Order.objects.filter(created_at__date__gte=thirty_days_ago).aggregate(
                    total=Sum('total')
                )['total'] or 0
            },
            'by_status': dict(Order.objects.values_list('status').annotate(
                count=Count('id')
            )),
            'by_payment_method': dict(Order.objects.exclude(payment_method='').values_list(
                'payment_method'
            ).annotate(count=Count('id'))),
            'average_order_value': Order.objects.aggregate(
                avg=Avg('total')
            )['avg'] or 0,
            'conversion_rate': 0,  # You would calculate this from sessions
        }
        
        # Cache for 1 hour
        cache.set(cache_key, stats, 60 * 60)
        
        return Response(stats)
    
    @action(detail=False, methods=['get'], permission_classes=[IsAdminUser])
    def export(self, request):
        """Export orders to CSV (admin only)"""
        orders = self.filter_queryset(self.get_queryset())
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="orders_{timezone.now().date()}.csv"'
        
        writer = csv.writer(response)
        
        # Write header
        writer.writerow([
            'Order Number', 'Customer Email', 'Status', 'Payment Status',
            'Subtotal', 'Tax', 'Shipping', 'Discount', 'Total',
            'Created Date', 'Updated Date', 'Tracking Number', 'Carrier'
        ])
        
        # Write data
        for order in orders:
            writer.writerow([
                order.order_number,
                order.customer.user.email if order.customer else order.guest_email,
                order.get_status_display(),
                order.get_payment_status_display(),
                order.subtotal,
                order.tax_amount,
                order.shipping_cost,
                order.discount_amount,
                order.total,
                order.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                order.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
                order.tracking_number,
                order.carrier
            ])
        
        return response


class OrderItemViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for Order Items (read-only)"""
    serializer_class = OrderItemSerializer
    permission_classes = [IsOrderOwnerOrAdmin]
    
    def get_queryset(self):
        return OrderItem.objects.select_related('order', 'product').all()
    
    @action(detail=True, methods=['post'])
    def download(self, request, pk=None):
        """Download digital product"""
        order_item = self.get_object()
        
        if not order_item.is_digital:
            return Response(
                {'error': 'This is not a digital product'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not order_item.can_download:
            return Response(
                {'error': 'Download limit reached'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Increment download count
        order_item.increment_download()
        
        # Return download URL
        download_url = request.build_absolute_uri(order_item.digital_file.url)
        
        return Response({
            'download_url': download_url,
            'download_key': order_item.download_key,
            'remaining_downloads': order_item.download_limit - order_item.download_count
        })


class ShippingMethodViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for Shipping Methods"""
    queryset = ShippingMethod.objects.filter(is_active=True)
    serializer_class = ShippingMethodSerializer
    permission_classes = [AllowAny]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'carrier', 'code']
    ordering_fields = ['cost', 'estimated_days_min']
    
    @action(detail=False, methods=['post'])
    def calculate(self, request):
        """Calculate shipping cost"""
        serializer = ShippingQuoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        shipping_method = data['shipping_method_id']
        items = data['items']
        country = data['country']
        postal_code = data['postal_code']
        
        # Calculate weight and dimensions
        total_weight = 0
        total_value = 0
        
        for item_data in items:
            try:
                product = Product.objects.get(id=item_data['product_id'])
            except Product.DoesNotExist:
                return Response(
                    print(f"Product with id {item_data['product_id']} not found"),
                    {'error': f'Product with id {item_data["product_id"]} not found'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            quantity = item_data['quantity']
            
            if product.weight:
                total_weight += product.weight * quantity
            total_value += product.final_price * quantity
        
        # Check if free shipping applies
        shipping_cost = shipping_method.cost
        if (shipping_method.free_shipping_threshold and 
            total_value >= shipping_method.free_shipping_threshold):
            shipping_cost = 0
        
        # Check weight limit
        if shipping_method.max_weight and total_weight > shipping_method.max_weight:
            return Response(
                # print(f"Total weight {total_weight} exceeds max {shipping_method.max_weight}"),
                {'error': f'Total weight ({total_weight}kg) exceeds maximum ({shipping_method.max_weight}kg) for this shipping method'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check country restrictions
        # if (shipping_method.allowed_countries and 
        #     country not in shipping_method.allowed_countries):
        #     return Response(
        #         {'error': f'Shipping method not available for {country}'},
        #         status=status.HTTP_400_BAD_REQUEST
        #     )
        
        return Response({
            'shipping_method': ShippingMethodSerializer(shipping_method).data,
            'cost': shipping_cost,
            'estimated_delivery_days': {
                'min': shipping_method.estimated_days_min,
                'max': shipping_method.estimated_days_max
            },
            'free_shipping_eligible': shipping_cost == 0,
            'total_weight': total_weight,
            'total_value': total_value
        })


class OrderReturnViewSet(viewsets.ModelViewSet):
    """ViewSet for Order Returns"""
    queryset = OrderReturn.objects.select_related('order', 'order__customer__user').all()
    serializer_class = OrderReturnSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = OrderReturnFilter
    ordering_fields = ['requested_at', 'status']
    ordering = ['-requested_at']
    
    def get_permissions(self):
        if self.action == 'create':
            return [IsAuthenticated()]
        elif self.action in ['list', 'retrieve']:
            return [IsOrderOwnerOrAdmin()]
        elif self.action in ['update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Non-staff users can only see their own returns
        if not self.request.user.is_staff:
            queryset = queryset.filter(order__customer__user=self.request.user)
        
        return queryset
    
    def create(self, request, *args, **kwargs):
        """Create a return request"""
        serializer = ReturnCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        order = data['order_id']
        
        # Create return
        return_request = OrderReturn.objects.create(
            order=order,
            reason=data['reason'],
            reason_details=data.get('reason_details', '')
        )
        
        # Create return items
        for item_data in data['items']:
            order_item = OrderItem.objects.get(
                id=item_data['order_item_id'],
                order=order
            )
            
            ReturnItem.objects.create(
                return_request=return_request,
                order_item=order_item,
                quantity=item_data['quantity'],
                condition=item_data['condition'],
                refund_amount=order_item.price * item_data['quantity']
            )
        
        # Update total refund amount
        total_refund = sum(item.refund_amount for item in return_request.items.all())
        return_request.refund_amount = total_refund
        return_request.save()
        
        return Response(
            OrderReturnSerializer(return_request).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def approve(self, request, pk=None):
        """Approve a return request (admin only)"""
        return_request = self.get_object()
        
        if return_request.status != 'requested':
            return Response(
                {'error': 'Return request is not in requested status'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return_request.status = 'approved'
        return_request.approved_at = timezone.now()
        return_request.save()
        
        # Generate return shipping label (integration with carrier API)
        # return_request.return_shipping_label = generate_shipping_label(return_request)
        # return_request.save()
        
        return Response({
            'message': 'Return request approved',
            'return': OrderReturnSerializer(return_request).data
        })
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def process_refund(self, request, pk=None):
        """Process refund for return (admin only)"""
        return_request = self.get_object()
        
        if return_request.status != 'received':
            return Response(
                {'error': 'Return must be received before processing refund'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Here you would integrate with payment gateway
        # refund_id = process_payment_refund(return_request)
        
        return_request.status = 'refunded'
        return_request.refunded_at = timezone.now()
        # return_request.refund_id = refund_id
        return_request.save()
        
        # Restock items
        for return_item in return_request.items.all():
            if return_item.condition in ['new', 'like_new']:
                return_item.order_item.product.stock_quantity += return_item.quantity
                return_item.order_item.product.save()
        
        return Response({
            'message': 'Refund processed successfully',
            'return': OrderReturnSerializer(return_request).data
        })


class OrderNoteViewSet(viewsets.ModelViewSet):
    """ViewSet for Order Notes"""
    serializer_class = OrderNoteSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        order_number = self.kwargs.get('order_number')  # Changed from 'order_pk'
        
        try:
            order = Order.objects.get(order_number=order_number)
            queryset = OrderNote.objects.filter(order=order)
            
            if not self.request.user.is_staff:
                queryset = queryset.filter(is_customer_visible=True)
            
            return queryset
        except Order.DoesNotExist:
            return OrderNote.objects.none()
    
    def perform_create(self, serializer):
        order = Order.objects.get(pk=self.kwargs['order_number'])
        serializer.save(order=order)


# Analytics Views
class OrderAnalyticsView(APIView):
    """God-Level Order Analytics"""
    permission_classes = [IsAdminUser]
    
    def get(self, request):
        # Sales by day/week/month/year
        period = request.GET.get('period', 'month')  # day, week, month, year
        
        if period == 'day':
            trunc_func = TruncDate
        elif period == 'month':
            trunc_func = TruncMonth
        elif period == 'year':
            trunc_func = TruncYear
        else:
            trunc_func = TruncDate
        
        # Sales data
        sales_data = Order.objects.annotate(
            period=trunc_func('created_at')
        ).values('period').annotate(
            total_sales=Sum('total'),
            order_count=Count('id'),
            avg_order_value=Avg('total')
        ).order_by('period')
        
        # Top products
        top_products = OrderItem.objects.values(
            'product__name', 'product__sku'
        ).annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum(F('price') * F('quantity')),
            order_count=Count('order', distinct=True)
        ).order_by('-total_quantity')[:10]
        
        # Customer metrics
        customer_metrics = {
            'repeat_customers': Order.objects.values('customer').annotate(
                order_count=Count('id')
            ).filter(order_count__gt=1).count(),
            'new_customers': Order.objects.values('customer').annotate(
                first_order=Min('created_at')
            ).filter(first_order__date=timezone.now().date()).count(),
            'avg_customer_value': Order.objects.values('customer').annotate(
                total_spent=Sum('total')
            ).aggregate(avg=Avg('total_spent'))['avg'] or 0,
        }
        
        # Geographical data
        geography_data = Order.objects.exclude(
            shipping_address__isnull=True
        ).values(
            'shipping_address__country', 'shipping_address__state'
        ).annotate(
            order_count=Count('id'),
            total_revenue=Sum('total')
        ).order_by('-total_revenue')
        
        return Response({
            'sales_data': list(sales_data),
            'top_products': list(top_products),
            'customer_metrics': customer_metrics,
            'geography_data': list(geography_data),
            'period': period
        })


# Public API Views
class PublicOrderStatusView(APIView):
    """Public API to check order status without authentication"""
    permission_classes = [AllowAny]
    
    def get(self, request):
        order_number = request.GET.get('order_number')
        email = request.GET.get('email')
        
        if not order_number or not email:
            return Response(
                {'error': 'Order number and email are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            order = Order.objects.get(
                Q(order_number=order_number) &
                (Q(customer__user__email=email) | Q(guest_email=email))
            )
            
            return Response({
                'order_number': order.order_number,
                'status': order.status,
                'status_display': order.get_status_display(),
                'payment_status': order.payment_status,
                'payment_status_display': order.get_payment_status_display(),
                'tracking_number': order.tracking_number,
                'carrier': order.carrier,
                'estimated_delivery': order.estimated_delivery,
                'created_at': order.created_at,
                'items': [
                    {
                        'product_name': item.product.name,
                        'quantity': item.quantity,
                        'price': item.price
                    }
                    for item in order.items.all()
                ]
            })
        except Order.DoesNotExist:
            return Response(
                {'error': 'Order not found'},
                status=status.HTTP_404_NOT_FOUND
            )


# Webhook Views
@api_view(['POST'])
@permission_classes([AllowAny])
def shipping_webhook(request, carrier):
    """
    Webhook endpoint for shipping carriers to update tracking
    """
    # Verify webhook signature (implementation depends on carrier)
    # carrier can be 'dhl', 'fedex', 'ups', etc.
    
    data = request.data
    
    # Extract tracking info from webhook data
    tracking_number = data.get('tracking_number')
    status = data.get('status')
    events = data.get('events', [])
    
    try:
        order = Order.objects.get(tracking_number=tracking_number)
        
        # Update order status based on carrier status
        status_mapping = {
            'delivered': 'delivered',
            'out_for_delivery': 'out_for_delivery',
            'exception': 'on_hold',
            # Add more mappings as needed
        }
        
        if status in status_mapping:
            old_status = order.status
            order.status = status_mapping[status]
            
            if status == 'delivered':
                order.delivered_date = timezone.now()
            
            order.save()
            
            # Create status history
            OrderStatusHistory.objects.create(
                order=order,
                old_status=old_status,
                new_status=order.status,
                changed_by=None,  # System
                notes=f'Status updated via {carrier} webhook',
                ip_address=request.META.get('REMOTE_ADDR')
            )
        
        return Response({'success': True})
    
    except Order.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )