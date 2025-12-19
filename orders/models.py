from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.core.mail import send_mail
from decimal import Decimal
import uuid
from datetime import timedelta


class Order(models.Model):
    ORDER_STATUS = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('processing', 'Processing'),
        ('ready_to_ship', 'Ready to Ship'),
        ('shipped', 'Shipped'),
        ('out_for_delivery', 'Out for Delivery'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
        ('on_hold', 'On Hold'),
    ]
    
    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('authorized', 'Authorized'),
        ('paid', 'Paid'),
        ('partially_paid', 'Partially Paid'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
        ('cancelled', 'Cancelled'),
    ]
    
    PAYMENT_METHODS = [
        ('MPesa', 'M-Pesa'),
        ('PayPal', 'PayPal'),
        ('OnDelivery', 'Cash on Delivery'),
    ]

    customer = models.ForeignKey('customers.Customer', on_delete=models.PROTECT, related_name='orders')
    order_number = models.CharField(max_length=50, unique=True, editable=False)
    status = models.CharField(max_length=20, choices=ORDER_STATUS, default='pending')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, blank=True)
    payment_id = models.CharField(max_length=255, blank=True)  # Payment gateway reference
    
    # Addresses
    billing_address = models.ForeignKey('customers.Address', on_delete=models.PROTECT, related_name='billing_orders')
    shipping_address = models.ForeignKey('customers.Address', on_delete=models.PROTECT, related_name='shipping_orders')
    
    # Pricing
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # Tax percentage
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_code = models.CharField(max_length=50, blank=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, default='KSH')
    
    # Shipping
    shipping_method = models.CharField(max_length=100, blank=True)
    tracking_number = models.CharField(max_length=100, blank=True)
    tracking_url = models.URLField(blank=True)
    carrier = models.CharField(max_length=100, blank=True)  # DHL, FedEx, UPS, etc.
    estimated_delivery = models.DateTimeField(null=True, blank=True)
    shipped_date = models.DateTimeField(null=True, blank=True)
    delivered_date = models.DateTimeField(null=True, blank=True)

    # M-Pesa integration fields
    mpesa_checkout_request_id = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="M-Pesa STK Push checkout request ID"
    )
    mpesa_transaction_id = models.IntegerField(
        blank=True, 
        null=True,
        help_text="Reference to MpesaTransaction model"
    )
    
    # Customer notes
    customer_notes = models.TextField(blank=True)
    admin_notes = models.TextField(blank=True)
    
    # Flags
    is_gift = models.BooleanField(default=False)
    gift_message = models.TextField(blank=True)
    requires_shipping = models.BooleanField(default=True)
    is_digital = models.BooleanField(default=False)  # For digital products
    is_recurring = models.BooleanField(default=False)  # Subscription orders
    is_guest = models.BooleanField(default=False)  # Guest checkout
    
    # Guest order info
    guest_email = models.EmailField(blank=True)
    guest_phone = models.CharField(max_length=20, blank=True)
    
    # Audit
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order_number']),
            models.Index(fields=['customer', 'created_at']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['payment_status', 'created_at']),
        ]
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = f"ORD-{uuid.uuid4().hex[:10].upper()}"
        
        # Auto-calculate estimated delivery if shipped
        if self.status == 'shipped' and not self.estimated_delivery:
            self.estimated_delivery = timezone.now() + timedelta(days=3)
        
        # Update timestamps based on status
        if self.status == 'paid' and not self.paid_at:
            self.paid_at = timezone.now()
        elif self.status == 'cancelled' and not self.cancelled_at:
            self.cancelled_at = timezone.now()
        elif self.status == 'refunded' and not self.refunded_at:
            self.refunded_at = timezone.now()
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Order {self.order_number} - {self.customer.user.email}"

    @property
    def is_paid(self):
        return self.payment_status in ['paid', 'authorized']

    @property
    def is_completed(self):
        return self.status == 'delivered'

    @property
    def is_cancellable(self):
        return self.status not in ['delivered', 'cancelled', 'refunded', 'shipped']

    @property
    def days_since_ordered(self):
        return (timezone.now() - self.created_at).days

    @property
    def weight_total(self):
        """Calculate total weight of order items"""
        return sum(item.product.weight * item.quantity for item in self.items.all() if item.product.weight)

    def calculate_totals(self):
        """Recalculate order totals from items"""
        subtotal = sum(item.total for item in self.items.all())
        self.subtotal = subtotal
        self.tax_amount = subtotal * (self.tax_rate / 100)
        self.total = subtotal + self.tax_amount + self.shipping_cost - self.discount_amount
        self.save()


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT)
    variant = models.JSONField(default=dict, blank=True)  # For product variants like color, size
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    price = models.DecimalField(max_digits=10, decimal_places=2)  # Price at time of purchase
    original_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)  # Original price for reference
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    
    # Digital product fields
    digital_file = models.FileField(upload_to='digital_products/', blank=True, null=True)
    download_key = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        # unique=True,
        null=True,
        blank=True
    )
    download_limit = models.IntegerField(default=5)
    download_count = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Order Item'
        verbose_name_plural = 'Order Items'

    def save(self, *args, **kwargs):
        # Calculate total for this line item
        self.total = (self.price * self.quantity) - self.discount
        
        # Generate download key for digital products
        try:
            is_digital = getattr(self.product, 'is_digital', False)
            if is_digital and not self.download_key:
                self.download_key = self._generate_download_key()
        except AttributeError:
            # Product doesn't have is_digital attribute
            pass
        
        super().save(*args, **kwargs)
        
        # Update order totals
        if self.order:
            self.order.calculate_totals()

    def __str__(self):
        return f"{self.product.name} x {self.quantity} (Order: {self.order.order_number})"

    @property
    def is_digital(self):
        return bool(self.digital_file)

    @property
    def can_download(self):
        return self.is_digital and self.download_count < self.download_limit

    def increment_download(self):
        if self.can_download:
            self.download_count += 1
            self.save()
            return True
        return False


class OrderStatusHistory(models.Model):
    """Track all status changes for audit trail"""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='status_history')
    old_status = models.CharField(max_length=50)
    new_status = models.CharField(max_length=50)
    changed_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Order Status Histories'

    def __str__(self):
        return f"{self.order.order_number}: {self.old_status} → {self.new_status}"


class ShippingMethod(models.Model):
    """Available shipping methods"""
    name = models.CharField(max_length=100)
    carrier = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    
    # Cost calculation
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    free_shipping_threshold = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    # Delivery time
    estimated_days_min = models.IntegerField(default=3)
    estimated_days_max = models.IntegerField(default=7)
    
    # Constraints
    max_weight = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    allowed_countries = models.JSONField(default=list, blank=True)
    excluded_products = models.ManyToManyField('products.Product', blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['cost', 'estimated_days_min']

    def __str__(self):
        return f"{self.carrier} - {self.name}"


class OrderReturn(models.Model):
    RETURN_STATUS = [
        ('requested', 'Return Requested'),
        ('approved', 'Approved'),
        ('received', 'Received at Warehouse'),
        ('inspected', 'Inspected'),
        ('refunded', 'Refund Issued'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]
    
    RETURN_REASONS = [
        ('defective', 'Product Defective'),
        ('wrong_item', 'Wrong Item Sent'),
        ('not_as_described', 'Not as Described'),
        ('changed_mind', 'Changed Mind'),
        ('too_small', 'Too Small'),
        ('too_large', 'Too Large'),
        ('damaged', 'Damaged in Transit'),
        ('other', 'Other'),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='returns')
    return_number = models.CharField(max_length=50, unique=True, editable=False)
    status = models.CharField(max_length=20, choices=RETURN_STATUS, default='requested')
    reason = models.CharField(max_length=50, choices=RETURN_REASONS)
    reason_details = models.TextField(blank=True)
    
    # Return items
    items = models.ManyToManyField(OrderItem, through='ReturnItem')
    
    # Shipping
    return_shipping_label = models.URLField(blank=True)
    return_tracking = models.CharField(max_length=100, blank=True)
    return_carrier = models.CharField(max_length=100, blank=True)
    
    # Refund
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    refund_method = models.CharField(max_length=50, blank=True)
    refund_id = models.CharField(max_length=255, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    
    # Admin
    notes = models.TextField(blank=True)
    restocking_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Dates
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.return_number:
            self.return_number = f"RET-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Return {self.return_number} for Order {self.order.order_number}"


class ReturnItem(models.Model):
    return_request = models.ForeignKey(OrderReturn, on_delete=models.CASCADE)
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE)
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    condition = models.CharField(max_length=50)  # new, used, damaged, etc.
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ['return_request', 'order_item']


class OrderNote(models.Model):
    """Internal notes for orders"""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='internal_notes')
    user = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    note = models.TextField()
    is_customer_visible = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Note for {self.order.order_number} by {self.user}"