from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.db.models import Sum, F, Q
from products.models import Product
from decimal import Decimal
import uuid


class Warehouse(models.Model):
    """Physical or virtual warehouse locations"""
    name = models.CharField(max_length=100, unique=True) # e.g. "Home", "Office", "Warehouse"
    code = models.CharField(max_length=20, unique=True)  # Internal code / short-id
    street_address = models.CharField(max_length=200, default="Moi Avenue, 1st Floor")  # e.g. “Moi Avenue, 1st Floor”
    additional_details = models.TextField(null=True, blank=True)  # landmarks, etc.

    town = models.CharField(max_length=100, default="Nairobi")  # e.g. “Nairobi”, “Thika”, “Eldoret”
    county = models.CharField(max_length=100, default="Nairobi")  # e.g. “Nairobi County”, “Kiambu County”

    postal_code = models.CharField(max_length=20, null=True, blank=True)  
    # Kenya postal codes are usually like "00100" or "20100"

    country = models.CharField(max_length=100, default='Kenya')
    
    # Contact
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    manager = models.ForeignKey(User, on_delete=models.PROTECT, related_name='managed_warehouses')
    
    # Settings
    is_active = models.BooleanField(default=True)
    is_primary = models.BooleanField(default=False)
    priority = models.IntegerField(default=0, help_text='Higher priority warehouses are checked first for stock')
    
    # Capacity
    max_capacity = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, 
                                      help_text='Maximum capacity in cubic meters')
    current_capacity = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-priority', 'name']
        verbose_name_plural = 'Warehouses'

    def __str__(self):
        return f"{self.name} ({self.code})"

    @property
    def capacity_percentage(self):
        if self.max_capacity and self.max_capacity > 0:
            return (self.current_capacity / self.max_capacity) * 100
        return 0

    @property
    def total_products(self):
        return self.stock.aggregate(total=Sum('quantity'))['total'] or 0

    def save(self, *args, **kwargs):
        # Ensure only one primary warehouse
        if self.is_primary:
            Warehouse.objects.filter(is_primary=True).exclude(id=self.id).update(is_primary=False)
        super().save(*args, **kwargs)


class WarehouseStock(models.Model):
    """Stock levels per warehouse per product"""
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='stock')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='warehouse_stock')
    
    # Quantities
    quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    reserved_quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)], 
                                           help_text='Quantity reserved for pending orders')
    damaged_quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    
    # Location within warehouse
    location = models.CharField(max_length=50, blank=True, help_text='Aisle-Shelf-Bin (e.g., A-12-5)')
    zone = models.CharField(max_length=50, blank=True, help_text='Storage zone (e.g., Cold, Dry, Hazmat)')
    
    # Reorder settings per warehouse
    reorder_point = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    reorder_quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    
    # Timestamps
    last_counted = models.DateTimeField(null=True, blank=True, help_text='Last physical count date')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['warehouse', 'product']
        ordering = ['warehouse', 'product']
        verbose_name_plural = 'Warehouse Stock'
        indexes = [
            models.Index(fields=['warehouse', 'product']),
            models.Index(fields=['quantity']),
        ]

    def __str__(self):
        return f"{self.warehouse.code} - {self.product.sku}: {self.quantity}"

    @property
    def available_quantity(self):
        """Quantity available for sale (total - reserved - damaged)"""
        return max(0, self.quantity - self.reserved_quantity - self.damaged_quantity)

    @property
    def needs_reorder(self):
        return self.available_quantity <= self.reorder_point

    def reserve_stock(self, quantity):
        """Reserve stock for an order"""
        if self.available_quantity >= quantity:
            self.reserved_quantity += quantity
            self.save()
            return True
        return False

    def release_reservation(self, quantity):
        """Release reserved stock (e.g., order cancelled)"""
        self.reserved_quantity = max(0, self.reserved_quantity - quantity)
        self.save()

    def fulfill_reservation(self, quantity):
        """Fulfill reserved stock (remove from inventory)"""
        self.reserved_quantity = max(0, self.reserved_quantity - quantity)
        self.quantity = max(0, self.quantity - quantity)
        self.save()


class StockMovement(models.Model):
    """Track all inventory movements"""
    MOVEMENT_TYPES = [
        ('purchase', 'Purchase/Receiving'),
        ('sale', 'Sale'),
        ('return', 'Customer Return'),
        ('adjustment', 'Adjustment'),
        ('transfer', 'Warehouse Transfer'),
        ('damaged', 'Damaged'),
        ('lost', 'Lost'),
        ('found', 'Found'),
        ('production', 'Production'),
        ('sample', 'Sample'),
        ('promotion', 'Promotional'),
        ('writeoff', 'Write-off'),
    ]

    movement_number = models.CharField(max_length=50, unique=True, editable=False, null=True, blank=True)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='movements', null=True)
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='stock_movements')
    
    # Movement details
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES)
    quantity = models.IntegerField(help_text='Positive for increases, negative for decreases')
    quantity_before = models.IntegerField(default=0, help_text='Quantity before movement')
    quantity_after = models.IntegerField(default=0, help_text='Quantity after movement')
    
    # Cost tracking
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, default=0)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    
    # References
    reference_type = models.CharField(max_length=50, blank=True, 
                                     help_text='Type of reference (order, transfer, adjustment)')
    reference_id = models.CharField(max_length=100, blank=True, 
                                   help_text='ID of the referenced entity')
    order = models.ForeignKey('orders.Order', on_delete=models.SET_NULL, null=True, blank=True, 
                             related_name='inventory_movements')
    transfer = models.ForeignKey('InventoryTransfer', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='movements')
    
    # Notes and audit
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, 
                                   related_name='approved_movements')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    movement_date = models.DateTimeField(default=timezone.now, 
                                        help_text='Actual date of movement (can be backdated)')

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['warehouse', 'product', '-created_at']),
            models.Index(fields=['movement_type', '-created_at']),
            models.Index(fields=['reference_type', 'reference_id']),
        ]

    def save(self, *args, **kwargs):
        if not self.movement_number:
            self.movement_number = f"MV-{uuid.uuid4().hex[:10].upper()}"
        
        # Calculate total cost
        if self.unit_cost and self.quantity:
            self.total_cost = abs(self.quantity) * self.unit_cost
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.movement_number} - {self.movement_type} ({self.quantity})"


class InventoryTransfer(models.Model):
    """Transfer stock between warehouses"""
    TRANSFER_STATUS = [
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('in_transit', 'In Transit'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    ]

    transfer_number = models.CharField(max_length=50, unique=True, editable=False)
    
    # Warehouses
    from_warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, 
                                      related_name='transfers_out')
    to_warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, 
                                    related_name='transfers_in')
    
    # Status and tracking
    status = models.CharField(max_length=20, choices=TRANSFER_STATUS, default='draft')
    tracking_number = models.CharField(max_length=100, blank=True)
    
    # Timestamps
    requested_at = models.DateTimeField(auto_now_add=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    expected_arrival = models.DateTimeField(null=True, blank=True)
    
    # Users
    requested_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='requested_transfers')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='approved_transfers')
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='received_transfers')
    
    # Notes
    notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-requested_at']

    def save(self, *args, **kwargs):
        if not self.transfer_number:
            self.transfer_number = f"TRF-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.transfer_number}: {self.from_warehouse.code} → {self.to_warehouse.code}"

    @property
    def total_items(self):
        return self.items.aggregate(total=Sum('quantity'))['total'] or 0

    def approve_transfer(self, user):
        """Approve and initiate transfer"""
        if self.status != 'draft':
            return False
        
        self.status = 'pending'
        self.approved_by = user
        self.save()
        
        # Reserve stock in source warehouse
        for item in self.items.all():
            warehouse_stock = WarehouseStock.objects.get(
                warehouse=self.from_warehouse,
                product=item.product
            )
            warehouse_stock.reserve_stock(item.quantity)
        
        return True

    def ship_transfer(self, user, tracking_number=None):
        """Mark transfer as shipped"""
        if self.status != 'pending':
            return False
        
        self.status = 'in_transit'
        self.shipped_at = timezone.now()
        if tracking_number:
            self.tracking_number = tracking_number
        self.save()
        
        # Remove stock from source warehouse
        for item in self.items.all():
            from_stock = WarehouseStock.objects.get(
                warehouse=self.from_warehouse,
                product=item.product
            )
            from_stock.fulfill_reservation(item.quantity)
            
            # Create stock movement
            StockMovement.objects.create(
                warehouse=self.from_warehouse,
                product=item.product,
                movement_type='transfer',
                quantity=-item.quantity,
                quantity_before=from_stock.quantity + item.quantity,
                quantity_after=from_stock.quantity,
                reference_type='transfer',
                reference_id=str(self.id),
                transfer=self,
                notes=f"Transfer to {self.to_warehouse.code}",
                created_by=user
            )
        
        return True

    def receive_transfer(self, user, received_items=None):
        """Mark transfer as received"""
        if self.status != 'in_transit':
            return False
        
        self.status = 'received'
        self.received_at = timezone.now()
        self.received_by = user
        self.save()
        
        # Add stock to destination warehouse
        for item in self.items.all():
            quantity = item.quantity
            if received_items and item.id in received_items:
                quantity = received_items[item.id].get('quantity', item.quantity)
            
            to_stock, created = WarehouseStock.objects.get_or_create(
                warehouse=self.to_warehouse,
                product=item.product,
                defaults={'quantity': 0}
            )
            
            quantity_before = to_stock.quantity
            to_stock.quantity += quantity
            to_stock.save()
            
            # Create stock movement
            StockMovement.objects.create(
                warehouse=self.to_warehouse,
                product=item.product,
                movement_type='transfer',
                quantity=quantity,
                quantity_before=quantity_before,
                quantity_after=to_stock.quantity,
                reference_type='transfer',
                reference_id=str(self.id),
                transfer=self,
                notes=f"Transfer from {self.from_warehouse.code}",
                created_by=user
            )
            
            # Update received quantity
            item.received_quantity = quantity
            item.save()
        
        return True


class TransferItem(models.Model):
    """Items in an inventory transfer"""
    transfer = models.ForeignKey(InventoryTransfer, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    received_quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ['transfer', 'product']

    def __str__(self):
        return f"{self.product.sku} x {self.quantity}"


class StockAlert(models.Model):
    """Automated alerts for inventory issues"""
    ALERT_TYPES = [
        ('low_stock', 'Low Stock'),
        ('out_of_stock', 'Out of Stock'),
        ('overstock', 'Overstock'),
        ('reorder_point', 'Reorder Point Reached'),
        ('damaged', 'Damaged Stock'),
        ('expiring', 'Expiring Soon'),
        ('discrepancy', 'Stock Discrepancy'),
    ]

    ALERT_PRIORITY = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    priority = models.CharField(max_length=10, choices=ALERT_PRIORITY, default='medium')
    
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='alerts')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_alerts')
    
    # Alert details
    message = models.TextField()
    current_quantity = models.IntegerField()
    threshold_quantity = models.IntegerField(null=True, blank=True)
    
    # Status
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='resolved_alerts')
    resolution_notes = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-priority', '-created_at']
        indexes = [
            models.Index(fields=['alert_type', 'is_resolved']),
            models.Index(fields=['warehouse', 'is_resolved']),
        ]

    def __str__(self):
        return f"{self.get_alert_type_display()} - {self.product.sku} @ {self.warehouse.code}"

    def resolve(self, user, notes=''):
        """Mark alert as resolved"""
        self.is_resolved = True
        self.resolved_at = timezone.now()
        self.resolved_by = user
        self.resolution_notes = notes
        self.save()


class StockCount(models.Model):
    """Physical inventory counts"""
    COUNT_STATUS = [
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    COUNT_TYPES = [
        ('full', 'Full Count'),
        ('cycle', 'Cycle Count'),
        ('spot', 'Spot Check'),
    ]

    count_number = models.CharField(max_length=50, unique=True, editable=False)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='stock_counts')
    
    count_type = models.CharField(max_length=20, choices=COUNT_TYPES, default='cycle')
    status = models.CharField(max_length=20, choices=COUNT_STATUS, default='scheduled')
    
    # Schedule
    scheduled_date = models.DateField()
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Users
    assigned_to = models.ForeignKey(User, on_delete=models.PROTECT, related_name='assigned_counts')
    completed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='completed_counts')
    
    # Notes
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-scheduled_date']

    def save(self, *args, **kwargs):
        if not self.count_number:
            self.count_number = f"CNT-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.count_number} - {self.warehouse.code} ({self.scheduled_date})"

    @property
    def total_items(self):
        return self.items.count()

    @property
    def discrepancy_count(self):
        return self.items.filter(has_discrepancy=True).count()


class StockCountItem(models.Model):
    """Individual items in a stock count"""
    stock_count = models.ForeignKey(StockCount, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    
    # Quantities
    expected_quantity = models.IntegerField(help_text='Quantity from system')
    counted_quantity = models.IntegerField(null=True, blank=True, help_text='Actual counted quantity')
    discrepancy = models.IntegerField(default=0, help_text='Difference between expected and counted')
    
    # Status
    is_counted = models.BooleanField(default=False)
    has_discrepancy = models.BooleanField(default=False)
    
    # Notes
    notes = models.TextField(blank=True)
    counted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    counted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['stock_count', 'product']
        ordering = ['product__sku']

    def __str__(self):
        return f"{self.product.sku} - Expected: {self.expected_quantity}, Counted: {self.counted_quantity}"

    def save(self, *args, **kwargs):
        if self.counted_quantity is not None:
            self.discrepancy = self.counted_quantity - self.expected_quantity
            self.has_discrepancy = self.discrepancy != 0
            self.is_counted = True
        super().save(*args, **kwargs)