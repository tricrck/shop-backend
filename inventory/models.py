from django.db import models
from products.models import Product
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator

class StockMovement(models.Model):
    MOVEMENT_TYPES = [
        ('purchase', 'Purchase'),
        ('sale', 'Sale'),
        ('return', 'Return'),
        ('adjustment', 'Adjustment'),
        ('damaged', 'Damaged'),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_movements')
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES)
    quantity = models.IntegerField()
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.product.name} - {self.movement_type} ({self.quantity})"


class Warehouse(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    address = models.TextField()
    manager = models.ForeignKey(User, on_delete=models.PROTECT, related_name='managed_warehouses')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class WarehouseStock(models.Model):
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='stock')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    location = models.CharField(max_length=50, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['warehouse', 'product']

    def __str__(self):
        return f"{self.warehouse.name} - {self.product.name}: {self.quantity}"
