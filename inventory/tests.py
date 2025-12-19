from django.test import TestCase
from inventory.models import Warehouse, WarehouseStock, StockAlert
from products.models import Product
from django.contrib.auth.models import User

class SignalTests(TestCase):
    def test_low_stock_alert_signal(self):
        # Create test data
        user = User.objects.create_user(username='test', password='test')
        warehouse = Warehouse.objects.create(
            name='Test Warehouse',
            code='TEST',
            manager=user
        )
        product = Product.objects.create(
            name='Test Product',
            sku='TEST-001',
            stock_quantity=10,
            cost_price=10.00,
            selling_price=15.00
        )
        
        # Create warehouse stock below reorder point
        stock = WarehouseStock.objects.create(
            warehouse=warehouse,
            product=product,
            quantity=5,
            reorder_point=10
        )
        
        # Check if alert was created
        alert = StockAlert.objects.filter(
            product=product,
            warehouse=warehouse,
            alert_type='low_stock'
        ).first()
        
        self.assertIsNotNone(alert)
        self.assertEqual(alert.current_quantity, 5)
        self.assertEqual(alert.threshold_quantity, 10)