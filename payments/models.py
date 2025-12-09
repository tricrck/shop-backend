from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal
import uuid


class MpesaConfiguration(models.Model):
    """
    Store M-Pesa API configurations
    Supports multiple environments (sandbox/production)
    """
    ENVIRONMENT_CHOICES = [
        ('sandbox', 'Sandbox'),
        ('production', 'Production'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    environment = models.CharField(max_length=20, choices=ENVIRONMENT_CHOICES, default='sandbox')
    consumer_key = models.CharField(max_length=255)
    consumer_secret = models.CharField(max_length=255)
    business_short_code = models.CharField(max_length=20)
    passkey = models.CharField(max_length=255)
    
    # API Endpoints
    api_base_url = models.URLField(default='https://sandbox.safaricom.co.ke')
    callback_url = models.URLField()
    timeout_url = models.URLField(blank=True)
    
    # Settings
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    
    # Rate limiting
    max_requests_per_minute = models.IntegerField(default=60)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'M-Pesa Configuration'
        verbose_name_plural = 'M-Pesa Configurations'

    def save(self, *args, **kwargs):
        # Ensure only one default configuration
        if self.is_default:
            MpesaConfiguration.objects.filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.environment})"


class MpesaTransaction(models.Model):
    """
    Core transaction model - tracks all M-Pesa transactions
    """
    TRANSACTION_TYPE_CHOICES = [
        ('stk_push', 'STK Push'),
        ('b2c', 'Business to Customer'),
        ('b2b', 'Business to Business'),
        ('c2b', 'Customer to Business'),
        ('account_balance', 'Account Balance'),
        ('reversal', 'Reversal'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('timeout', 'Timeout'),
        ('reversed', 'Reversed'),
    ]

    # Transaction identifiers
    transaction_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    merchant_request_id = models.CharField(max_length=255, db_index=True, blank=True)
    checkout_request_id = models.CharField(max_length=255, db_index=True, blank=True)
    mpesa_receipt_number = models.CharField(max_length=255, unique=True, null=True, blank=True)
    
    # Transaction details
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Related entities
    order = models.ForeignKey('orders.Order', on_delete=models.SET_NULL, null=True, blank=True, related_name='mpesa_transactions')
    customer = models.ForeignKey('customers.Customer', on_delete=models.SET_NULL, null=True, blank=True, related_name='mpesa_transactions')
    configuration = models.ForeignKey(MpesaConfiguration, on_delete=models.PROTECT, related_name='transactions')
    
    # Payment details
    phone_number = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(1)])
    account_reference = models.CharField(max_length=100)  # Order number or reference
    transaction_desc = models.CharField(max_length=255, blank=True)
    
    # Response data
    result_code = models.IntegerField(null=True, blank=True)
    result_desc = models.TextField(blank=True)
    
    # Additional metadata
    balance = models.CharField(max_length=100, blank=True)
    transaction_date = models.DateTimeField(null=True, blank=True)
    
    # Request/Response logs
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    callback_payload = models.JSONField(default=dict, blank=True)
    
    # Retry mechanism
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=3)
    last_retry_at = models.DateTimeField(null=True, blank=True)
    
    # Audit
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    # Timestamps
    initiated_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-initiated_at']
        indexes = [
            models.Index(fields=['checkout_request_id']),
            models.Index(fields=['merchant_request_id']),
            models.Index(fields=['mpesa_receipt_number']),
            models.Index(fields=['phone_number', 'initiated_at']),
            models.Index(fields=['status', 'initiated_at']),
            models.Index(fields=['order', 'status']),
        ]
        verbose_name = 'M-Pesa Transaction'
        verbose_name_plural = 'M-Pesa Transactions'

    def __str__(self):
        return f"{self.transaction_type} - {self.phone_number} - KES {self.amount}"

    @property
    def is_successful(self):
        return self.status == 'completed' and self.result_code == 0

    @property
    def is_pending(self):
        return self.status in ['pending', 'processing']

    @property
    def can_retry(self):
        return self.status == 'failed' and self.retry_count < self.max_retries

    def mark_completed(self, mpesa_receipt_number, transaction_date, callback_data=None):
        """Mark transaction as completed"""
        self.status = 'completed'
        self.mpesa_receipt_number = mpesa_receipt_number
        self.transaction_date = transaction_date
        self.completed_at = timezone.now()
        self.result_code = 0
        self.result_desc = 'Transaction completed successfully'
        
        if callback_data:
            self.callback_payload = callback_data
        
        self.save()

    def mark_failed(self, result_code, result_desc, callback_data=None):
        """Mark transaction as failed"""
        self.status = 'failed'
        self.result_code = result_code
        self.result_desc = result_desc
        self.failed_at = timezone.now()
        
        if callback_data:
            self.callback_payload = callback_data
        
        self.save()

    def increment_retry(self):
        """Increment retry count"""
        self.retry_count += 1
        self.last_retry_at = timezone.now()
        self.save()


class MpesaCallback(models.Model):
    """
    Store all M-Pesa callbacks for audit trail
    """
    CALLBACK_TYPE_CHOICES = [
        ('stk_callback', 'STK Callback'),
        ('validation', 'Validation'),
        ('confirmation', 'Confirmation'),
        ('timeout', 'Timeout'),
    ]

    callback_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    callback_type = models.CharField(max_length=20, choices=CALLBACK_TYPE_CHOICES)
    transaction = models.ForeignKey(MpesaTransaction, on_delete=models.SET_NULL, null=True, blank=True, related_name='callbacks')
    
    # Callback data
    checkout_request_id = models.CharField(max_length=255, db_index=True, blank=True)
    merchant_request_id = models.CharField(max_length=255, blank=True)
    raw_payload = models.JSONField()
    
    # Processing
    is_processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    processing_error = models.TextField(blank=True)
    
    # Audit
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['checkout_request_id']),
            models.Index(fields=['is_processed', 'received_at']),
        ]
        verbose_name = 'M-Pesa Callback'
        verbose_name_plural = 'M-Pesa Callbacks'

    def __str__(self):
        return f"{self.callback_type} - {self.checkout_request_id}"


class MpesaAccessToken(models.Model):
    """
    Cache M-Pesa access tokens
    """
    configuration = models.OneToOneField(MpesaConfiguration, on_delete=models.CASCADE, related_name='access_token')
    token = models.TextField()
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'M-Pesa Access Token'
        verbose_name_plural = 'M-Pesa Access Tokens'

    def __str__(self):
        return f"Token for {self.configuration.name}"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_valid(self):
        return not self.is_expired


class MpesaRefund(models.Model):
    """
    Track M-Pesa refunds/reversals
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    refund_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    original_transaction = models.ForeignKey(MpesaTransaction, on_delete=models.PROTECT, related_name='refunds')
    reversal_transaction = models.ForeignKey(MpesaTransaction, on_delete=models.SET_NULL, null=True, blank=True, related_name='original_refunds')
    
    order_return = models.ForeignKey('orders.OrderReturn', on_delete=models.SET_NULL, null=True, blank=True, related_name='mpesa_refunds')
    
    # Refund details
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Response
    result_code = models.IntegerField(null=True, blank=True)
    result_desc = models.TextField(blank=True)
    reversal_id = models.CharField(max_length=255, blank=True)
    
    # Audit
    initiated_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    initiated_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-initiated_at']
        verbose_name = 'M-Pesa Refund'
        verbose_name_plural = 'M-Pesa Refunds'

    def __str__(self):
        return f"Refund {self.refund_id} - KES {self.amount}"


class MpesaWebhookLog(models.Model):
    """
    Log all webhook attempts for debugging
    """
    webhook_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    endpoint = models.CharField(max_length=255)
    method = models.CharField(max_length=10)
    headers = models.JSONField(default=dict)
    body = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    # Response
    status_code = models.IntegerField(null=True, blank=True)
    response_body = models.JSONField(default=dict, blank=True)
    
    # Processing
    is_valid = models.BooleanField(default=False)
    validation_error = models.TextField(blank=True)
    
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-received_at']
        verbose_name = 'M-Pesa Webhook Log'
        verbose_name_plural = 'M-Pesa Webhook Logs'

    def __str__(self):
        return f"{self.method} {self.endpoint} - {self.received_at}"


class MpesaPaymentMethod(models.Model):
    """
    Store customer M-Pesa payment preferences
    """
    customer = models.ForeignKey('customers.Customer', on_delete=models.CASCADE, related_name='mpesa_payment_methods')
    phone_number = models.CharField(max_length=20)
    is_default = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    
    # Usage stats
    successful_transactions = models.IntegerField(default=0)
    failed_transactions = models.IntegerField(default=0)
    last_used_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['customer', 'phone_number']
        verbose_name = 'M-Pesa Payment Method'
        verbose_name_plural = 'M-Pesa Payment Methods'

    def __str__(self):
        return f"{self.customer.user.email} - {self.phone_number}"

    def save(self, *args, **kwargs):
        # Ensure only one default per customer
        if self.is_default:
            MpesaPaymentMethod.objects.filter(
                customer=self.customer, 
                is_default=True
            ).update(is_default=False)
        super().save(*args, **kwargs)