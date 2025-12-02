from django.db import models
from django.core.validators import MinValueValidator
from customers.models import Customer, Address
from products.models import Product

class Order(models.Model):
    ORDER_STATUS = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]
    
    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='orders')
    order_number = models.CharField(max_length=50, unique=True, editable=False)
    status = models.CharField(max_length=20, choices=ORDER_STATUS, default='pending')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    
    # Addresses
    billing_address = models.ForeignKey(Address, on_delete=models.PROTECT, related_name='billing_orders')
    shipping_address = models.ForeignKey(Address, on_delete=models.PROTECT, related_name='shipping_orders')
    
    # Pricing
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    
    # Shipping
    tracking_number = models.CharField(max_length=100, blank=True)
    shipped_date = models.DateTimeField(blank=True, null=True)
    delivered_date = models.DateTimeField(blank=True, null=True)
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.order_number:
            import uuid
            self.order_number = f"SND-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Order {self.order_number}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)

    def save(self, *args, **kwargs):
        self.total = (self.price * self.quantity) - self.discount
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"