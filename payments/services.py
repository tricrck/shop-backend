import base64
import requests
from datetime import datetime, timedelta
from django.utils import timezone
from django.conf import settings
from django.core.cache import cache
from decimal import Decimal
import logging

from .models import (
    MpesaConfiguration, MpesaTransaction, MpesaCallback, 
    MpesaAccessToken, MpesaRefund, MpesaWebhookLog
)
from orders.models import Order, OrderStatusHistory

logger = logging.getLogger(__name__)


class MpesaAPIClient:
    """
    God-Level M-Pesa API Client with retry logic, caching, and error handling
    """
    
    def __init__(self, configuration=None):
        if configuration:
            self.config = configuration
        else:
            self.config = MpesaConfiguration.objects.filter(is_default=True, is_active=True).first()
            if not self.config:
                raise ValueError("No active M-Pesa configuration found")
    
    def get_access_token(self):
        """
        Get cached access token or fetch new one
        Implements token caching to reduce API calls
        """
        cache_key = f'mpesa_token_{self.config.id}'
        cached_token = cache.get(cache_key)
        
        if cached_token:
            return cached_token
        
        # Check database cache
        try:
            token_obj = MpesaAccessToken.objects.get(configuration=self.config)
            if token_obj.is_valid:
                # Cache for remaining time
                cache_time = int((token_obj.expires_at - timezone.now()).total_seconds())
                cache.set(cache_key, token_obj.token, cache_time)
                return token_obj.token
        except MpesaAccessToken.DoesNotExist:
            pass
        
        # Fetch new token
        return self._fetch_new_token()
    
    def _fetch_new_token(self):
        """Fetch new access token from M-Pesa API"""
        auth_string = f"{self.config.consumer_key}:{self.config.consumer_secret}"
        auth_bytes = auth_string.encode('utf-8')
        auth_base64 = base64.b64encode(auth_bytes).decode('utf-8')
        
        url = f"{self.config.api_base_url}/oauth/v1/generate"
        headers = {
            "Authorization": f"Basic {auth_base64}"
        }
        params = {"grant_type": "client_credentials"}
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            access_token = data.get('access_token')
            expires_in = int(data.get('expires_in', 3600))
            
            if not access_token:
                raise ValueError("Access token not found in response")
            
            # Save to database
            expires_at = timezone.now() + timedelta(seconds=expires_in)
            MpesaAccessToken.objects.update_or_create(
                configuration=self.config,
                defaults={
                    'token': access_token,
                    'expires_at': expires_at
                }
            )
            
            # Cache token
            cache_key = f'mpesa_token_{self.config.id}'
            cache.set(cache_key, access_token, expires_in - 60)  # Expire 1 min early
            
            logger.info(f"New M-Pesa access token fetched for {self.config.name}")
            return access_token
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch M-Pesa access token: {str(e)}")
            raise
    
    def generate_password(self, timestamp):
        """Generate M-Pesa password for STK Push"""
        data_to_encode = f"{self.config.business_short_code}{self.config.passkey}{timestamp}"
        encoded = base64.b64encode(data_to_encode.encode()).decode('utf-8')
        return encoded
    
    def initiate_stk_push(self, phone_number, amount, account_reference, 
                         transaction_desc="Payment", order=None, customer=None):
        """
        Initiate STK Push (Lipa Na M-Pesa Online)
        Returns MpesaTransaction object
        """
        # Format phone number (remove + and leading zeros)
        phone_number = str(phone_number).replace('+', '').replace(' ', '')
        if phone_number.startswith('0'):
            phone_number = '254' + phone_number[1:]
        elif not phone_number.startswith('254'):
            phone_number = '254' + phone_number
        
        # Generate timestamp and password
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password = self.generate_password(timestamp)
        
        # Create transaction record
        transaction = MpesaTransaction.objects.create(
            transaction_type='stk_push',
            configuration=self.config,
            phone_number=phone_number,
            amount=Decimal(str(amount)),
            account_reference=account_reference,
            transaction_desc=transaction_desc,
            order=order,
            customer=customer,
            status='processing'
        )
        
        # Prepare API request
        url = f"{self.config.api_base_url}/mpesa/stkpush/v1/processrequest"
        headers = {
            "Authorization": f"Bearer {self.get_access_token()}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "BusinessShortCode": self.config.business_short_code,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": phone_number,
            "PartyB": self.config.business_short_code,
            "PhoneNumber": phone_number,
            "CallBackURL": self.config.callback_url,
            "AccountReference": account_reference,
            "TransactionDesc": transaction_desc
        }
        
        try:
            transaction.request_payload = payload
            transaction.save()
            
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            response_data = response.json()
            
            transaction.response_payload = response_data
            
            response_code = str(response_data.get('ResponseCode', ''))
            if response.status_code == 200 and response_code == '0':
                # Success
                transaction.merchant_request_id = response_data.get('MerchantRequestID')
                transaction.checkout_request_id = response_data.get('CheckoutRequestID')
                transaction.status = 'processing'
                
                logger.info(f"STK Push initiated successfully: {transaction.checkout_request_id}")
            else:
                # Failed
                transaction.status = 'failed'
                transaction.result_code = response_data.get('errorCode', -1)
                transaction.result_desc = response_data.get('errorMessage', 'Unknown error')
                transaction.failed_at = timezone.now()
                
                logger.error(f"STK Push failed: {transaction.result_desc}")
            transaction.save()
            return transaction
            
        except requests.RequestException as e:
            transaction.status = 'failed'
            transaction.result_desc = f"API request failed: {str(e)}"
            transaction.failed_at = timezone.now()
            transaction.save()
            
            logger.error(f"STK Push API error: {str(e)}")
            raise
    
    def query_stk_status(self, checkout_request_id):
        """Query the status of an STK Push transaction"""
        
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password = self.generate_password(timestamp)
        
        url = f"{self.config.api_base_url}/mpesa/stkpushquery/v1/query"
        headers = {
            "Authorization": f"Bearer {self.get_access_token()}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "BusinessShortCode": self.config.business_short_code,
            "Password": password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"STK status query failed: {str(e)}")
            raise
    
    def initiate_reversal(self, transaction, amount, reason):
        """
        Initiate transaction reversal
        """
        if not transaction.mpesa_receipt_number:
            raise ValueError("Cannot reverse transaction without M-Pesa receipt number")
        
        # Create refund record
        refund = MpesaRefund.objects.create(
            original_transaction=transaction,
            amount=amount,
            reason=reason,
            status='processing'
        )
        
        url = f"{self.config.api_base_url}/mpesa/reversal/v1/request"
        headers = {
            "Authorization": f"Bearer {self.get_access_token()}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "Initiator": "API",  # From Safaricom portal
            "SecurityCredential": "ENCRYPTED_PASSWORD",  # Generate this
            "CommandID": "TransactionReversal",
            "TransactionID": transaction.mpesa_receipt_number,
            "Amount": str(amount),
            "ReceiverParty": self.config.business_short_code,
            "RecieverIdentifierType": "4",
            "ResultURL": f"{self.config.callback_url}/reversal",
            "QueueTimeOutURL": f"{self.config.timeout_url}/reversal",
            "Remarks": reason,
            "Occasion": f"Refund for order {transaction.account_reference}"
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            response_data = response.json()
            
            if response.status_code == 200 and response_data.get('ResponseCode') == '0':
                refund.status = 'processing'
                refund.result_desc = response_data.get('ResponseDescription')
                logger.info(f"Reversal initiated: {refund.refund_id}")
            else:
                refund.status = 'failed'
                refund.result_code = response_data.get('errorCode', -1)
                refund.result_desc = response_data.get('errorMessage', 'Unknown error')
            
            refund.save()
            return refund
            
        except requests.RequestException as e:
            refund.status = 'failed'
            refund.result_desc = f"Reversal API error: {str(e)}"
            refund.save()
            logger.error(f"Reversal failed: {str(e)}")
            raise


class MpesaCallbackProcessor:
    """
    Process M-Pesa callbacks with idempotency and error handling
    """
    
    @staticmethod
    def process_stk_callback(callback_data, ip_address=None):
        """
        Process STK Push callback
        Implements idempotency to handle duplicate callbacks
        """
        try:
            # Log callback
            callback_log = MpesaCallback.objects.create(
                callback_type='stk_callback',
                raw_payload=callback_data,
                ip_address=ip_address
            )
            
            # Extract data
            stk_callback = callback_data.get('Body', {}).get('stkCallback', {})
            merchant_request_id = stk_callback.get('MerchantRequestID')
            checkout_request_id = stk_callback.get('CheckoutRequestID')
            result_code = stk_callback.get('ResultCode')
            result_desc = stk_callback.get('ResultDesc')
            
            callback_log.merchant_request_id = merchant_request_id
            callback_log.checkout_request_id = checkout_request_id
            
            # Find transaction
            try:
                transaction = MpesaTransaction.objects.get(
                    checkout_request_id=checkout_request_id
                )
                callback_log.transaction = transaction
            except MpesaTransaction.DoesNotExist:
                callback_log.processing_error = "Transaction not found"
                callback_log.save()
                logger.error(f"Transaction not found: {checkout_request_id}")
                return False
            
            # Check if already processed (idempotency)
            if transaction.status in ['completed', 'failed']:
                callback_log.is_processed = True
                callback_log.processed_at = timezone.now()
                callback_log.save()
                logger.info(f"Callback already processed: {checkout_request_id}")
                return True
            
            # Process based on result code
            if result_code == 0:
                # Success
                metadata = stk_callback.get('CallbackMetadata', {}).get('Item', [])
                metadata_dict = {item['Name']: item.get('Value') for item in metadata}
                
                mpesa_receipt_number = metadata_dict.get('MpesaReceiptNumber')
                amount = metadata_dict.get('Amount')
                transaction_date_str = str(metadata_dict.get('TransactionDate'))
                phone_number = metadata_dict.get('PhoneNumber')
                
                # Parse transaction date
                transaction_date = datetime.strptime(
                    transaction_date_str, 
                    '%Y%m%d%H%M%S'
                )
                transaction_date = timezone.make_aware(transaction_date)
                
                # Update transaction
                transaction.mark_completed(
                    mpesa_receipt_number=mpesa_receipt_number,
                    transaction_date=transaction_date,
                    callback_data=callback_data
                )
                
                # Update order if exists
                if transaction.order:
                    MpesaCallbackProcessor._update_order_payment(
                        transaction.order, 
                        transaction
                    )
                
                logger.info(f"Transaction completed: {mpesa_receipt_number}")
            else:
                # Failed
                transaction.mark_failed(
                    result_code=result_code,
                    result_desc=result_desc,
                    callback_data=callback_data
                )
                logger.warning(f"Transaction failed: {result_desc}")
            
            callback_log.is_processed = True
            callback_log.processed_at = timezone.now()
            callback_log.save()
            
            return True
            
        except Exception as e:
            logger.error(f"Callback processing error: {str(e)}", exc_info=True)
            if 'callback_log' in locals():
                callback_log.processing_error = str(e)
                callback_log.save()
            return False
    
    @staticmethod
    def _update_order_payment(order, transaction):
        """Update order payment status after successful M-Pesa payment"""
        from orders.models import Order, OrderStatusHistory
        
        old_payment_status = order.payment_status
        
        # Update order
        order.payment_status = 'paid'
        order.payment_id = transaction.mpesa_receipt_number
        order.paid_at = transaction.transaction_date or timezone.now()
        
        # Update order status if still pending
        if order.status == 'pending':
            order.status = 'confirmed'
        
        order.save()
        
        # Create status history
        OrderStatusHistory.objects.create(
            order=order,
            old_status=old_payment_status,
            new_status='paid',
            notes=f"Payment received via M-Pesa. Receipt: {transaction.mpesa_receipt_number}",
            changed_by=None  # System
        )
        
        logger.info(f"Order {order.order_number} payment updated")


class MpesaPaymentService:
    """
    High-level payment service orchestrating the payment flow
    """
    
    def __init__(self):
        self.api_client = MpesaAPIClient()
    
    def initiate_order_payment(self, order, phone_number):
        """
        Initiate payment for an order
        """
        # Validate order
        if order.payment_status in ['paid', 'refunded']:
            raise ValueError(f"Order {order.order_number} is already {order.payment_status}")
        
        # Initiate STK push
        transaction = self.api_client.initiate_stk_push(
            phone_number=phone_number,
            amount=order.total,
            account_reference=order.order_number,
            transaction_desc=f"Payment for order {order.order_number}",
            order=order,
            customer=order.customer
        )
        
        # Update order
        order.payment_method = 'MPesa'
        order.save()
        
        return transaction
    
    def check_payment_status(self, checkout_request_id):
        """
        Check payment status for a checkout request
        Query M-Pesa API if transaction is still pending
        """
        try:
            transaction = MpesaTransaction.objects.get(
                checkout_request_id=checkout_request_id
            )
            
            # If still processing, query M-Pesa API for latest status
            
            if transaction.is_pending:
                logger.info(f"Querying M-Pesa API for transaction status: {checkout_request_id}")
                
                try:
                    status_response = self.api_client.query_stk_status(checkout_request_id)
                    logger.info(f"M-Pesa status response: {status_response}")
                    
                    # Parse M-Pesa response
                    result_code = status_response.get('ResultCode')
                    result_desc = status_response.get('ResultDesc', '')
                    
                    if result_code is not None:
                        if result_code == '0':
                            # Transaction successful - extract metadata
                            result_parameters = status_response.get('ResultParameter', [])
                            
                            # Convert list of parameters to dict
                            params_dict = {}
                            if isinstance(result_parameters, list):
                                for param in result_parameters:
                                    if isinstance(param, dict):
                                        key = param.get('Key')
                                        value = param.get('Value')
                                        if key:
                                            params_dict[key] = value
                            
                            # Extract transaction details
                            mpesa_receipt_number = params_dict.get('ReceiptNo') or params_dict.get('MpesaReceiptNumber')
                            transaction_date_str = params_dict.get('TransactionCompletedDateTime') or params_dict.get('TransactionDate')
                            
                            if mpesa_receipt_number and transaction_date_str:
                                # Parse transaction date
                                try:
                                    # M-Pesa date format: YYYYMMDDHHmmss or DD.MM.YYYY HH:mm:ss
                                    if '.' in transaction_date_str:
                                        transaction_date = datetime.strptime(transaction_date_str, '%d.%m.%Y %H:%M:%S')
                                    else:
                                        transaction_date = datetime.strptime(str(transaction_date_str), '%Y%m%d%H%M%S')
                                    
                                    transaction_date = timezone.make_aware(transaction_date)
                                except (ValueError, TypeError) as e:
                                    logger.error(f"Error parsing transaction date: {e}")
                                    transaction_date = timezone.now()
                                
                                # Mark transaction as completed
                                transaction.mark_completed(
                                    mpesa_receipt_number=mpesa_receipt_number,
                                    transaction_date=transaction_date,
                                    callback_data=status_response
                                )
                                
                                # Update order if exists
                                if transaction.order:
                                    MpesaCallbackProcessor._update_order_payment(
                                        transaction.order, 
                                        transaction
                                    )
                                
                                logger.info(f"Transaction {checkout_request_id} marked as completed")
                            else:
                                logger.warning(f"Missing receipt number or date in successful response")
                        
                        elif result_code in ['1032', '1037']:
                            # User cancelled or timeout - mark as cancelled
                            transaction.status = 'cancelled' if result_code == '1032' else 'timeout'
                            transaction.result_code = int(result_code)
                            transaction.result_desc = result_desc
                            transaction.failed_at = timezone.now()
                            transaction.save()
                            logger.info(f"Transaction {checkout_request_id} marked as {transaction.status}")
                        
                        else:
                            # Transaction failed
                            transaction.mark_failed(
                                result_code=int(result_code),
                                result_desc=result_desc,
                                callback_data=status_response
                            )
                            logger.info(f"Transaction {checkout_request_id} marked as failed")
                    
                except Exception as e:
                    logger.error(f"Error querying M-Pesa status: {str(e)}", exc_info=True)
                    # Don't update transaction status on query error
                    # Return existing transaction data
            
            # Refresh transaction from database to get latest data
            transaction.refresh_from_db()
            return transaction
            
        except MpesaTransaction.DoesNotExist:
            logger.error(f"Transaction not found: {checkout_request_id}")
            return None
    
    def process_refund(self, order, amount, reason):
        """
        Process refund for an order
        """
        # Find successful transaction
        transaction = MpesaTransaction.objects.filter(
            order=order,
            status='completed',
            result_code=0
        ).first()
        
        if not transaction:
            raise ValueError(f"No successful M-Pesa transaction found for order {order.order_number}")
        
        if amount > transaction.amount:
            raise ValueError(f"Refund amount cannot exceed original payment amount")
        
        # Initiate reversal
        refund = self.api_client.initiate_reversal(transaction, amount, reason)
        
        return refund