from celery import shared_task
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def process_mpesa_callback_task(self, callback_data, ip_address):
    '''Process M-Pesa callback asynchronously'''
    from .services import MpesaCallbackProcessor
    
    try:
        success = MpesaCallbackProcessor.process_stk_callback(
            callback_data,
            ip_address
        )
        
        if not success:
            logger.error(f"Callback processing failed: {callback_data}")
            # Retry after 30 seconds
            raise self.retry(countdown=30)
        
        return {'status': 'success'}
    
    except Exception as e:
        logger.error(f"Callback task error: {str(e)}", exc_info=True)
        raise self.retry(countdown=60, exc=e)


@shared_task
def check_pending_transactions():
    '''
    Periodic task to check status of pending transactions
    Run every 5 minutes
    '''
    from django.utils import timezone
    from datetime import timedelta
    from .models import MpesaTransaction
    from .services import MpesaAPIClient
    
    # Get transactions pending for more than 5 minutes
    cutoff_time = timezone.now() - timedelta(minutes=5)
    pending_transactions = MpesaTransaction.objects.filter(
        status='processing',
        initiated_at__lte=cutoff_time
    )
    
    client = MpesaAPIClient()
    
    for transaction in pending_transactions:
        try:
            status_response = client.query_stk_status(
                transaction.checkout_request_id
            )
            
            # Update transaction based on response
            result_code = status_response.get('ResultCode')
            
            if result_code == '0':
                # Success - but callback might have been missed
                logger.warning(
                    f"Transaction {transaction.checkout_request_id} "
                    f"completed but callback was not received"
                )
            elif result_code:
                # Failed
                transaction.mark_failed(
                    result_code=int(result_code),
                    result_desc=status_response.get('ResultDesc', 'Unknown error')
                )
        
        except Exception as e:
            logger.error(
                f"Error checking transaction {transaction.id}: {str(e)}"
            )


@shared_task
def send_payment_confirmation_email(transaction_id):
    '''Send payment confirmation email to customer'''
    from django.core.mail import send_mail
    from .models import MpesaTransaction
    
    try:
        transaction = MpesaTransaction.objects.get(id=transaction_id)
        
        if transaction.order and transaction.order.customer:
            customer_email = transaction.order.customer.user.email
            
            send_mail(
                subject=f'Payment Confirmation - Order {transaction.order.order_number}',
                message=f'''
                Dear {transaction.order.customer.user.first_name},
                
                Your payment of KES {transaction.amount} has been received successfully.
                
                Transaction Details:
                - M-Pesa Receipt: {transaction.mpesa_receipt_number}
                - Order Number: {transaction.order.order_number}
                - Amount: KES {transaction.amount}
                - Date: {transaction.transaction_date}
                
                Thank you for your purchase!
                ''',
                from_email='noreply@yourshop.com',
                recipient_list=[customer_email],
                fail_silently=False,
            )
            
            logger.info(f"Payment confirmation email sent to {customer_email}")
    
    except Exception as e:
        logger.error(f"Failed to send confirmation email: {str(e)}")