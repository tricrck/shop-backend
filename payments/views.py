from rest_framework import viewsets, status, generics
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Sum, Count, Avg
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from datetime import timedelta
import logging

from .models import (
    MpesaConfiguration, MpesaTransaction, MpesaCallback,
    MpesaRefund, MpesaWebhookLog, MpesaPaymentMethod
)
from .serializers import (
    MpesaConfigurationSerializer, MpesaTransactionSerializer,
    MpesaCallbackSerializer, MpesaRefundSerializer,
    InitiatePaymentSerializer, CheckPaymentStatusSerializer,
    MpesaPaymentMethodSerializer, MpesaTransactionListSerializer
)
from .services import MpesaPaymentService, MpesaCallbackProcessor
from .filters import MpesaTransactionFilter
from .permissions import IsTransactionOwnerOrAdmin
from orders.models import Order

logger = logging.getLogger(__name__)


class MpesaConfigurationViewSet(viewsets.ModelViewSet):
    """
    Admin-only viewset for M-Pesa configurations
    """
    queryset = MpesaConfiguration.objects.all()
    serializer_class = MpesaConfigurationSerializer
    permission_classes = [IsAdminUser]
    
    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        """Set a configuration as default"""
        config = self.get_object()
        MpesaConfiguration.objects.filter(is_default=True).update(is_default=False)
        config.is_default = True
        config.save()
        
        return Response({
            'message': f'{config.name} set as default configuration',
            'configuration': MpesaConfigurationSerializer(config).data
        })
    
    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """Test M-Pesa API connection"""
        from .services import MpesaAPIClient
        
        config = self.get_object()
        
        try:
            client = MpesaAPIClient(configuration=config)
            token = client.get_access_token()
            
            return Response({
                'status': 'success',
                'message': 'Connection successful',
                'token_preview': token[:20] + '...' if token else None
            })
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


class MpesaTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing M-Pesa transactions
    """
    queryset = MpesaTransaction.objects.select_related(
        'order', 'customer', 'configuration'
    ).all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = MpesaTransactionFilter
    
    def get_serializer_class(self):
        if self.action == 'list':
            return MpesaTransactionListSerializer
        return MpesaTransactionSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Non-staff users can only see their own transactions
        if not self.request.user.is_staff:
            queryset = queryset.filter(
                Q(customer__user=self.request.user) |
                Q(order__customer__user=self.request.user)
            )
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def my_transactions(self, request):
        """Get current user's transactions"""
        transactions = self.get_queryset().filter(
            Q(customer__user=request.user) |
            Q(order__customer__user=request.user)
        ).order_by('-initiated_at')
        
        page = self.paginate_queryset(transactions)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(transactions, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        """Retry a failed transaction"""
        transaction = self.get_object()
        
        if not transaction.can_retry:
            return Response({
                'error': 'Transaction cannot be retried'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Initiate new payment with same details
        service = MpesaPaymentService()
        
        try:
            new_transaction = service.api_client.initiate_stk_push(
                phone_number=transaction.phone_number,
                amount=transaction.amount,
                account_reference=transaction.account_reference,
                transaction_desc=transaction.transaction_desc,
                order=transaction.order,
                customer=transaction.customer
            )
            
            # Update original transaction
            transaction.increment_retry()
            
            return Response({
                'message': 'Payment retry initiated',
                'transaction': MpesaTransactionSerializer(new_transaction).data
            })
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'], permission_classes=[IsAdminUser])
    def stats(self, request):
        """Get transaction statistics (admin only)"""
        today = timezone.now().date()
        thirty_days_ago = today - timedelta(days=30)
        
        stats = {
            'total_transactions': MpesaTransaction.objects.count(),
            'successful_transactions': MpesaTransaction.objects.filter(
                status='completed', result_code=0
            ).count(),
            'failed_transactions': MpesaTransaction.objects.filter(
                status='failed'
            ).count(),
            'pending_transactions': MpesaTransaction.objects.filter(
                status__in=['pending', 'processing']
            ).count(),
            'total_amount': MpesaTransaction.objects.filter(
                status='completed', result_code=0
            ).aggregate(total=Sum('amount'))['total'] or 0,
            'today': {
                'transactions': MpesaTransaction.objects.filter(
                    initiated_at__date=today
                ).count(),
                'successful': MpesaTransaction.objects.filter(
                    initiated_at__date=today,
                    status='completed',
                    result_code=0
                ).count(),
                'amount': MpesaTransaction.objects.filter(
                    initiated_at__date=today,
                    status='completed',
                    result_code=0
                ).aggregate(total=Sum('amount'))['total'] or 0,
            },
            'last_30_days': {
                'transactions': MpesaTransaction.objects.filter(
                    initiated_at__date__gte=thirty_days_ago
                ).count(),
                'successful': MpesaTransaction.objects.filter(
                    initiated_at__date__gte=thirty_days_ago,
                    status='completed',
                    result_code=0
                ).count(),
                'amount': MpesaTransaction.objects.filter(
                    initiated_at__date__gte=thirty_days_ago,
                    status='completed',
                    result_code=0
                ).aggregate(total=Sum('amount'))['total'] or 0,
            },
            'average_transaction_amount': MpesaTransaction.objects.filter(
                status='completed', result_code=0
            ).aggregate(avg=Avg('amount'))['avg'] or 0,
            'success_rate': 0,
        }
        
        # Calculate success rate
        total = stats['total_transactions']
        if total > 0:
            stats['success_rate'] = (stats['successful_transactions'] / total) * 100
        
        return Response(stats)


class InitiatePaymentView(APIView):
    """
    Initiate M-Pesa STK Push payment
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = InitiatePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        order_id = data['order_id']
        phone_number = data['phone_number']
        
        try:
            # Get order
            order = Order.objects.get(id=order_id)
            
            # Verify order ownership
            if order.customer.user != request.user and not request.user.is_staff:
                return Response({
                    'error': 'You do not have permission to pay for this order'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Check if order is already paid
            if order.payment_status in ['paid', 'refunded']:
                return Response({
                    'error': f'Order is already {order.payment_status}'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Initiate payment
            service = MpesaPaymentService()
            transaction = service.initiate_order_payment(order, phone_number)
            
            return Response({
                'message': 'Payment initiated successfully. Please check your phone.',
                'transaction': MpesaTransactionSerializer(transaction).data,
                'checkout_request_id': transaction.checkout_request_id
            }, status=status.HTTP_201_CREATED)
            
        except Order.DoesNotExist:
            return Response({
                'error': 'Order not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Payment initiation error: {str(e)}", exc_info=True)
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


class CheckPaymentStatusView(APIView):
    """
    Check payment status by checkout request ID
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        logger.info("=== Check Payment Status Request ===")
        logger.info(f"Request Data: {request.data}")
        logger.info(f"User: {request.user}")
        
        serializer = CheckPaymentStatusSerializer(data=request.data)
        
        if not serializer.is_valid():
            logger.error(f"Validation Errors: {serializer.errors}")
            return Response({
                'error': 'Invalid request data',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        checkout_request_id = serializer.validated_data['checkout_request_id']
        logger.info(f"Looking for transaction with checkout_request_id: {checkout_request_id}")
        
        try:
            transaction = MpesaTransaction.objects.select_related(
                'order', 'customer', 'order__customer', 'order__customer__user', 'customer__user'
            ).get(checkout_request_id=checkout_request_id)
            
            logger.info(f"Found transaction: {transaction.id}")
            logger.info(f"Transaction status: {transaction.status}")
            
            # Verify ownership first
            has_permission = False
            
            if request.user.is_staff:
                has_permission = True
            elif transaction.customer and hasattr(transaction.customer, 'user'):
                if transaction.customer.user == request.user:
                    has_permission = True
            elif transaction.order and hasattr(transaction.order, 'customer'):
                if hasattr(transaction.order.customer, 'user'):
                    if transaction.order.customer.user == request.user:
                        has_permission = True
            
            if not has_permission:
                logger.warning(f"Permission denied for user {request.user.id} on transaction {transaction.id}")
                return Response({
                    'error': 'Permission denied'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # If transaction is still processing, query M-Pesa API for latest status
            if transaction.status == 'processing':
                logger.info(f"Transaction {transaction.id} is still processing, querying M-Pesa API")
                try:
                    service = MpesaPaymentService()
                    updated_transaction = service.check_payment_status(checkout_request_id)
                    if updated_transaction:
                        transaction = updated_transaction
                        logger.info(f"Transaction status updated to: {transaction.status}")
                except Exception as e:
                    logger.error(f"Error querying M-Pesa API: {str(e)}")
                    # Continue with existing transaction data even if API query fails
            
            # Prepare response
            response_data = {
                'transaction': MpesaTransactionSerializer(transaction).data,
                'statusInfo': {
                    'transaction': {
                        'status': transaction.status,
                        'result_code': transaction.result_code,
                        'result_desc': transaction.result_desc,
                        'mpesa_receipt_number': transaction.mpesa_receipt_number,
                        'is_successful': transaction.is_successful,
                        'is_pending': transaction.is_pending,
                    }
                }
            }
            
            if transaction.order:
                response_data['order'] = {
                    'id': transaction.order.id,
                    'order_number': transaction.order.order_number,
                    'payment_status': transaction.order.payment_status,
                    'status': transaction.order.status
                }
            
            logger.info(f"Successfully returning transaction data for {checkout_request_id}")
            return Response(response_data)
            
        except MpesaTransaction.DoesNotExist:
            logger.error(f"Transaction not found for checkout_request_id: {checkout_request_id}")
            return Response({
                'error': 'Transaction not found',
                'checkout_request_id': checkout_request_id
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error checking payment status: {str(e)}", exc_info=True)
            return Response({
                'error': 'Internal server error',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MpesaRefundViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for M-Pesa refunds
    """
    queryset = MpesaRefund.objects.select_related(
        'original_transaction', 'order_return'
    ).all()
    serializer_class = MpesaRefundSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Non-staff users can only see their own refunds
        if not self.request.user.is_staff:
            queryset = queryset.filter(
                original_transaction__customer__user=self.request.user
            )
        
        return queryset


class MpesaPaymentMethodViewSet(viewsets.ModelViewSet):
    """
    Manage customer's M-Pesa payment methods
    """
    serializer_class = MpesaPaymentMethodSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return MpesaPaymentMethod.objects.filter(
            customer=self.request.user.customer
        )
    
    def perform_create(self, serializer):
        serializer.save(customer=self.request.user.customer)
    
    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        """Set a payment method as default"""
        payment_method = self.get_object()
        
        # Unset other defaults
        MpesaPaymentMethod.objects.filter(
            customer=request.user.customer,
            is_default=True
        ).update(is_default=False)
        
        payment_method.is_default = True
        payment_method.save()
        
        return Response({
            'message': 'Default payment method updated',
            'payment_method': self.get_serializer(payment_method).data
        })


# Webhook Endpoints
@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def mpesa_callback(request):
    """
    M-Pesa STK Push callback endpoint
    This is called by Safaricom servers
    """
    try:
        # Log webhook
        webhook_log = MpesaWebhookLog.objects.create(
            endpoint='/mpesa/callback',
            method='POST',
            headers=dict(request.headers),
            body=request.data,
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        # Process callback asynchronously (recommended)
        # from .tasks import process_mpesa_callback_task
        # process_mpesa_callback_task.delay(request.data, request.META.get('REMOTE_ADDR'))
        
        # Or process synchronously
        success = MpesaCallbackProcessor.process_stk_callback(
            request.data,
            request.META.get('REMOTE_ADDR')
        )
        
        webhook_log.is_valid = success
        webhook_log.status_code = 200 if success else 400
        webhook_log.save()
        
        # M-Pesa expects this exact response
        return JsonResponse({
            'ResultCode': 0,
            'ResultDesc': 'Accepted'
        })
        
    except Exception as e:
        logger.error(f"Callback processing error: {str(e)}", exc_info=True)
        return JsonResponse({
            'ResultCode': 1,
            'ResultDesc': 'Failed'
        }, status=500)


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def mpesa_timeout(request):
    """
    M-Pesa timeout callback endpoint
    """
    try:
        # Log timeout
        MpesaWebhookLog.objects.create(
            endpoint='/mpesa/timeout',
            method='POST',
            headers=dict(request.headers),
            body=request.data,
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        checkout_request_id = request.data.get('CheckoutRequestID')
        
        if checkout_request_id:
            try:
                transaction = MpesaTransaction.objects.get(
                    checkout_request_id=checkout_request_id
                )
                transaction.status = 'timeout'
                transaction.result_desc = 'Transaction timed out'
                transaction.failed_at = timezone.now()
                transaction.save()
            except MpesaTransaction.DoesNotExist:
                pass
        
        return JsonResponse({
            'ResultCode': 0,
            'ResultDesc': 'Accepted'
        })
        
    except Exception as e:
        logger.error(f"Timeout processing error: {str(e)}", exc_info=True)
        return JsonResponse({
            'ResultCode': 1,
            'ResultDesc': 'Failed'
        }, status=500)


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def mpesa_validation(request):
    """
    C2B Validation endpoint (optional)
    Validate transactions before they are processed
    """
    try:
        # Log validation request
        MpesaWebhookLog.objects.create(
            endpoint='/mpesa/validation',
            method='POST',
            headers=dict(request.headers),
            body=request.data,
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        # Perform validation logic
        # For now, accept all transactions
        return JsonResponse({
            'ResultCode': 0,
            'ResultDesc': 'Accepted'
        })
        
    except Exception as e:
        logger.error(f"Validation error: {str(e)}", exc_info=True)
        return JsonResponse({
            'ResultCode': 1,
            'ResultDesc': 'Failed'
        }, status=500)


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def mpesa_confirmation(request):
    """
    C2B Confirmation endpoint (optional)
    Confirm successful C2B transactions
    """
    try:
        # Log confirmation
        MpesaWebhookLog.objects.create(
            endpoint='/mpesa/confirmation',
            method='POST',
            headers=dict(request.headers),
            body=request.data,
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        # Process C2B transaction
        # This would be similar to STK callback processing
        
        return JsonResponse({
            'ResultCode': 0,
            'ResultDesc': 'Accepted'
        })
        
    except Exception as e:
        logger.error(f"Confirmation error: {str(e)}", exc_info=True)
        return JsonResponse({
            'ResultCode': 1,
            'ResultDesc': 'Failed'
        }, status=500)


# Admin Actions
class ProcessRefundView(APIView):
    """
    Admin endpoint to process refunds
    """
    permission_classes = [IsAdminUser]
    
    def post(self, request):
        order_id = request.data.get('order_id')
        amount = request.data.get('amount')
        reason = request.data.get('reason', 'Customer refund request')
        
        if not order_id or not amount:
            return Response({
                'error': 'order_id and amount are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            order = Order.objects.get(id=order_id)
            service = MpesaPaymentService()
            
            refund = service.process_refund(order, amount, reason)
            
            return Response({
                'message': 'Refund initiated successfully',
                'refund': MpesaRefundSerializer(refund).data
            })
            
        except Order.DoesNotExist:
            return Response({
                'error': 'Order not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)