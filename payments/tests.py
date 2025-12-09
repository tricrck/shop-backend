# tests/test_mpesa.py
from django.test import TestCase
from payments.services import MpesaAPIClient, MpesaPaymentService
from payments.models import MpesaConfiguration, MpesaTransaction
from orders.models import Order

class MpesaPaymentTest(TestCase):
    def setUp(self):
        # Create test configuration
        self.config = MpesaConfiguration.objects.create(
            name='Test Config',
            environment='sandbox',
            consumer_key='test_key',
            consumer_secret='test_secret',
            business_short_code='174379',
            passkey='test_passkey',
            callback_url='https://test.com/callback/',
            is_default=True
        )
        
        # Create test order
        self.order = Order.objects.create(
            total=100.00,
            # ... other fields
        )
    
    def test_stk_push_initiation(self):
        service = MpesaPaymentService()
        transaction = service.initiate_order_payment(
            order=self.order,
            phone_number='254712345678'
        )
        
        self.assertIsNotNone(transaction)
        self.assertEqual(transaction.amount, self.order.total)
        self.assertEqual(transaction.status, 'processing')
    
    def test_callback_processing(self):
        # Create mock transaction
        transaction = MpesaTransaction.objects.create(
            checkout_request_id='test_checkout_123',
            transaction_type='stk_push',
            phone_number='254712345678',
            amount=100.00,
            status='processing',
            configuration=self.config
        )
        
        # Mock callback data
        callback_data = {
            'Body': {
                'stkCallback': {
                    'MerchantRequestID': 'test_merchant_123',
                    'CheckoutRequestID': 'test_checkout_123',
                    'ResultCode': 0,
                    'ResultDesc': 'Success',
                    'CallbackMetadata': {
                        'Item': [
                            {'Name': 'MpesaReceiptNumber', 'Value': 'TEST123'},
                            {'Name': 'Amount', 'Value': 100},
                            {'Name': 'TransactionDate', 'Value': 20240101120000},
                            {'Name': 'PhoneNumber', 'Value': 254712345678}
                        ]
                    }
                }
            }
        }
        
        from payments.services import MpesaCallbackProcessor
        success = MpesaCallbackProcessor.process_stk_callback(callback_data)
        
        self.assertTrue(success)
        
        # Refresh transaction
        transaction.refresh_from_db()
        self.assertEqual(transaction.status, 'completed')
        self.assertEqual(transaction.mpesa_receipt_number, 'TEST123')