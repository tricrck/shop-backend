from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from .models import Customer, Address
from django.urls import reverse
import json
from datetime import date

class KenyanAddressModelTests(TestCase):
    """Comprehensive model tests for Kenyan address system"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            first_name='John',
            last_name='Doe'
        )
        self.customer = self.user.customer
        self.customer.phone = '+254712345678'
        self.customer.date_of_birth = date(1990, 1, 1)
        self.customer.save()
    
    def test_create_address_with_kenyan_fields(self):
        """Test creating address with Kenyan-specific fields"""
        address = Address.objects.create(
            customer=self.customer,
            address_type='shipping',
            street_address='123 Main Street',
            county='Nairobi',
            subcounty='Westlands',
            ward='Parklands',
            city='Nairobi',
            state='Nairobi County',
            postal_code='00100',
            country='Kenya',
            is_default=True
        )
        
        self.assertEqual(address.county, 'Nairobi')
        self.assertEqual(address.subcounty, 'Westlands')
        self.assertEqual(address.ward, 'Parklands')
        self.assertEqual(address.country, 'Kenya')
        self.assertTrue(address.is_default)
    
    def test_address_str_representation(self):
        """Test string representation includes Kenyan county"""
        address = Address.objects.create(
            customer=self.customer,
            address_type='billing',
            street_address='456 Moi Avenue',
            county='Mombasa',
            city='Mombasa',
            state='Mombasa County',
            postal_code='80100',
            country='Kenya'
        )
        
        self.assertIn('Mombasa', str(address))
        self.assertIn('billing', str(address))
    
    def test_country_default_kenya(self):
        """Test that country defaults to Kenya"""
        address = Address.objects.create(
            customer=self.customer,
            address_type='shipping',
            street_address='789 Thika Road',
            county='Kiambu',
            city='Thika',
            postal_code='01000'
            # country not specified
        )
        
        self.assertEqual(address.country, 'Kenya')
    
    def test_multiple_addresses_per_customer(self):
        """Test customer can have multiple addresses with different types"""
        # Create shipping address
        shipping = Address.objects.create(
            customer=self.customer,
            address_type='shipping',
            street_address='111 Kasarani',
            county='Nairobi',
            subcounty='Kasarani',
            ward='Mwiki',
            city='Nairobi',
            postal_code='00600',
            country='Kenya'
        )
        
        # Create billing address
        billing = Address.objects.create(
            customer=self.customer,
            address_type='billing',
            street_address='222 Karen',
            county='Nairobi',
            subcounty='Langata',
            ward='Karen',
            city='Nairobi',
            postal_code='00502',
            country='Kenya',
            is_default=True
        )
        
        self.assertEqual(self.customer.addresses.count(), 2)
        self.assertEqual(self.customer.addresses.filter(address_type='shipping').count(), 1)
        self.assertEqual(self.customer.addresses.filter(address_type='billing').count(), 1)
        self.assertTrue(billing.is_default)
        self.assertFalse(shipping.is_default)
    
    def test_unique_default_per_address_type(self):
        """Test only one default address per address type"""
        # Create first default billing address
        addr1 = Address.objects.create(
            customer=self.customer,
            address_type='billing',
            street_address='Address 1',
            county='Nairobi',
            city='Nairobi',
            postal_code='00100',
            country='Kenya',
            is_default=True
        )
        
        # Create second default billing address - should auto-update
        addr2 = Address.objects.create(
            customer=self.customer,
            address_type='billing',
            street_address='Address 2',
            county='Nairobi',
            city='Nairobi',
            postal_code='00200',
            country='Kenya',
            is_default=True
        )
        
        addr1.refresh_from_db()
        addr2.refresh_from_db()
        
        self.assertFalse(addr1.is_default)
        self.assertTrue(addr2.is_default)
    
    def test_kenyan_counties_validation(self):
        """Test validation of Kenyan counties"""
        # Valid counties
        valid_counties = ['Nairobi', 'Mombasa', 'Kisumu', 'Nakuru', 'Eldoret']
        
        for county in valid_counties:
            address = Address(
                customer=self.customer,
                address_type='shipping',
                street_address='Test Street',
                county=county,
                city=county,
                postal_code='00100',
                country='Kenya'
            )
            address.full_clean()  # Should not raise validation error
    
    def test_address_with_minimal_kenyan_fields(self):
        """Test address creation with minimal required fields for Kenya"""
        address = Address.objects.create(
            customer=self.customer,
            address_type='shipping',
            street_address='Minimal Address',
            county='Kajiado',  # Required
            city='Kajiado',  # Required
            postal_code='01100',  # Required
            # subcounty, ward, apartment optional
        )
        
        self.assertEqual(address.county, 'Kajiado')
        self.assertEqual(address.city, 'Kajiado')
        self.assertEqual(address.country, 'Kenya')  # Default
        self.assertEqual(address.subcounty, '')  # Empty string default
        self.assertEqual(address.ward, '')  # Empty string default


class KenyanAddressAPITests(APITestCase):
    """API tests for Kenyan address system"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='apitestuser',
            email='api@example.com',
            password='testpass123'
        )
        self.customer = self.user.customer
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        
        self.address_data = {
            'address_type': 'shipping',
            'street_address': '123 Kimathi Street',
            'apartment': 'Suite 4B',
            'county': 'Nairobi',
            'subcounty': 'Central',
            'ward': 'Central',
            'city': 'Nairobi',
            'state': 'Nairobi County',
            'postal_code': '00100',
            'country': 'Kenya',
            'is_default': True
        }
    
    def test_create_address_with_kenyan_fields_api(self):
        """Test API address creation with Kenyan fields"""
        url = reverse('address-list')
        response = self.client.post(url, self.address_data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['county'], 'Nairobi')
        self.assertEqual(response.data['subcounty'], 'Central')
        self.assertEqual(response.data['ward'], 'Central')
        self.assertEqual(response.data['country'], 'Kenya')
    
    def test_create_address_without_county_fails(self):
        """Test API validation requires county field"""
        data = self.address_data.copy()
        data.pop('county')  # Remove required county field
        
        url = reverse('address-list')
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('county', response.data)
    
    def test_create_address_with_non_kenyan_country_fails(self):
        """Test API rejects non-Kenyan addresses"""
        data = self.address_data.copy()
        data['country'] = 'Uganda'  # Non-Kenyan country
        
        url = reverse('address-list')
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('country', response.data)
    
    def test_update_address_kenyan_fields_api(self):
        """Test API address update with Kenyan fields"""
        # Create address first
        address = Address.objects.create(
            customer=self.customer,
            **{k: v for k, v in self.address_data.items() if k != 'is_default'}
        )
        
        # Update with new Kenyan data
        update_data = {
            'county': 'Mombasa',
            'subcounty': 'Island',
            'ward': 'Old Town',
            'city': 'Mombasa',
            'postal_code': '80100'
        }
        
        url = reverse('address-detail', args=[address.id])
        response = self.client.patch(url, update_data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['county'], 'Mombasa')
        self.assertEqual(response.data['subcounty'], 'Island')
        self.assertEqual(response.data['ward'], 'Old Town')
        self.assertEqual(response.data['city'], 'Mombasa')
    
    def test_list_addresses_includes_kenyan_fields(self):
        """Test API address list includes Kenyan fields"""
        # Create multiple addresses
        Address.objects.create(
            customer=self.customer,
            address_type='shipping',
            street_address='Address 1',
            county='Nairobi',
            city='Nairobi',
            postal_code='00100',
            country='Kenya'
        )
        
        Address.objects.create(
            customer=self.customer,
            address_type='billing',
            street_address='Address 2',
            county='Kisumu',
            city='Kisumu',
            postal_code='40100',
            country='Kenya'
        )
        
        url = reverse('address-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        
        # Verify Kenyan fields are present in response
        for address in response.data:
            self.assertIn('county', address)
            self.assertIn('subcounty', address)
            self.assertIn('ward', address)
            self.assertIn('country', address)
            self.assertEqual(address['country'], 'Kenya')
    
    def test_set_default_address_with_kenyan_fields(self):
        """Test setting default address via API"""
        # Create two addresses
        addr1 = Address.objects.create(
            customer=self.customer,
            address_type='shipping',
            street_address='Address 1',
            county='Nakuru',
            city='Nakuru',
            postal_code='20100',
            country='Kenya',
            is_default=True
        )
        
        addr2 = Address.objects.create(
            customer=self.customer,
            address_type='shipping',
            street_address='Address 2',
            county='Eldoret',
            city='Eldoret',
            postal_code='30100',
            country='Kenya',
            is_default=False
        )
        
        # Set addr2 as default via API
        url = reverse('address-set-default', args=[addr2.id])
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Refresh from database
        addr1.refresh_from_db()
        addr2.refresh_from_db()
        
        self.assertFalse(addr1.is_default)
        self.assertTrue(addr2.is_default)
    
    def test_customer_profile_includes_kenyan_addresses(self):
        """Test customer profile includes addresses with Kenyan fields"""
        # Create address with Kenyan fields
        Address.objects.create(
            customer=self.customer,
            address_type='shipping',
            street_address='Kenyatta Avenue',
            county='Nairobi',
            subcounty='CBD',
            ward='Harambee',
            city='Nairobi',
            postal_code='00100',
            country='Kenya',
            is_default=True
        )
        
        url = reverse('customer-profile')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('addresses', response.data)
        self.assertEqual(len(response.data['addresses']), 1)
        
        address = response.data['addresses'][0]
        self.assertEqual(address['county'], 'Nairobi')
        self.assertEqual(address['subcounty'], 'CBD')
        self.assertEqual(address['ward'], 'Harambee')
        self.assertEqual(address['country'], 'Kenya')


class KenyanAddressEdgeCaseTests(TestCase):
    """Edge case tests for Kenyan address system"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='edgeuser',
            email='edge@example.com',
            password='testpass123'
        )
        self.customer = self.user.customer
    
    def test_address_with_special_characters_in_kenyan_fields(self):
        """Test address with special characters in Kenyan fields"""
        address = Address.objects.create(
            customer=self.customer,
            address_type='billing',
            street_address='Moi\'s Lane',
            county='Nairobi (CBD)',
            subcounty='Westlands/ABC',
            ward='Kileleshwa-Section',
            city='Nairobi-City',
            postal_code='00100-100',
            country='Kenya'
        )
        
        self.assertEqual(address.county, 'Nairobi (CBD)')
        self.assertEqual(address.subcounty, 'Westlands/ABC')
        self.assertEqual(address.ward, 'Kileleshwa-Section')
        self.assertEqual(address.postal_code, '00100-100')
    
    def test_long_kenyan_field_values(self):
        """Test address with maximum length Kenyan field values"""
        long_county = 'A' * 100  # Max length for county field
        long_subcounty = 'B' * 100  # Max length for subcounty field
        long_ward = 'C' * 100  # Max length for ward field
        
        address = Address.objects.create(
            customer=self.customer,
            address_type='shipping',
            street_address='Test Street',
            county=long_county,
            subcounty=long_subcounty,
            ward=long_ward,
            city='Test City',
            postal_code='00100',
            country='Kenya'
        )
        
        self.assertEqual(address.county, long_county)
        self.assertEqual(address.subcounty, long_subcounty)
        self.assertEqual(address.ward, long_ward)
    
    def test_empty_optional_kenyan_fields(self):
        """Test address with empty optional Kenyan fields"""
        address = Address.objects.create(
            customer=self.customer,
            address_type='shipping',
            street_address='Simple Address',
            county='Nairobi',
            subcounty='',  # Empty string
            ward='',  # Empty string
            apartment='',  # Empty string
            city='Nairobi',
            postal_code='00100',
            country='Kenya'
        )
        
        self.assertEqual(address.subcounty, '')
        self.assertEqual(address.ward, '')
        self.assertEqual(address.apartment, '')
    
    def test_address_with_nairobi_county_variations(self):
        """Test different variations of Nairobi county naming"""
        variations = [
            'Nairobi',
            'nairobi',  # lowercase
            'NAIROBI',  # uppercase
            ' Nairobi ',  # with spaces
            'Nairobi County',
        ]
        
        for county_name in variations:
            address = Address(
                customer=self.customer,
                address_type='shipping',
                street_address='Test',
                county=county_name.strip(),
                city='Nairobi',
                postal_code='00100',
                country='Kenya'
            )
            address.save()
            
            self.assertEqual(address.county, county_name.strip())
            Address.objects.filter(county=county_name.strip()).delete()
    
    def test_multiple_customers_same_kenyan_address(self):
        """Test multiple customers can have addresses in same Kenyan location"""
        # Create second customer
        user2 = User.objects.create_user(
            username='customer2',
            email='customer2@example.com',
            password='testpass123'
        )
        customer2 = user2.customer
        
        # Same address details, different customers
        address1 = Address.objects.create(
            customer=self.customer,
            address_type='shipping',
            street_address='Same Building',
            county='Nairobi',
            subcounty='Westlands',
            ward='Parklands',
            city='Nairobi',
            postal_code='00100',
            country='Kenya'
        )
        
        address2 = Address.objects.create(
            customer=customer2,
            address_type='shipping',
            street_address='Same Building',
            county='Nairobi',
            subcounty='Westlands',
            ward='Parklands',
            city='Nairobi',
            postal_code='00100',
            country='Kenya'
        )
        
        self.assertEqual(address1.county, address2.county)
        self.assertEqual(address1.subcounty, address2.subcounty)
        self.assertEqual(address1.ward, address2.ward)
        self.assertNotEqual(address1.customer, address2.customer)


class KenyanAddressPerformanceTests(TestCase):
    """Performance tests for Kenyan address system"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='perfuser',
            email='perf@example.com',
            password='testpass123'
        )
        self.customer = self.user.customer
    
    def test_bulk_create_kenyan_addresses(self):
        """Test bulk creation of addresses with Kenyan fields"""
        addresses = []
        
        for i in range(100):
            addresses.append(Address(
                customer=self.customer,
                address_type='shipping',
                street_address=f'Street {i}',
                county=f'County {i % 10}',
                subcounty=f'Subcounty {i % 20}',
                ward=f'Ward {i % 30}',
                city=f'City {i % 5}',
                postal_code=f'00{i:03d}',
                country='Kenya'
            ))
        
        Address.objects.bulk_create(addresses)
        
        self.assertEqual(Address.objects.filter(customer=self.customer).count(), 100)
        self.assertEqual(Address.objects.filter(country='Kenya').count(), 100)
    
    def test_query_filter_by_kenyan_fields_performance(self):
        """Test query performance when filtering by Kenyan fields"""
        # Create test data
        for i in range(50):
            Address.objects.create(
                customer=self.customer,
                address_type='shipping' if i % 2 == 0 else 'billing',
                street_address=f'Address {i}',
                county='Nairobi' if i % 3 == 0 else 'Mombasa',
                subcounty=f'Subcounty {i % 5}',
                ward=f'Ward {i % 7}',
                city='Nairobi' if i % 3 == 0 else 'Mombasa',
                postal_code=f'00{i:03d}',
                country='Kenya'
            )
        
        # Test various filter combinations
        with self.assertNumQueries(1):
            # Filter by county
            nairobi_addresses = Address.objects.filter(county='Nairobi')
            self.assertGreater(nairobi_addresses.count(), 0)
        
        with self.assertNumQueries(1):
            # Filter by county and subcounty
            filtered = Address.objects.filter(
                county='Nairobi',
                subcounty__startswith='Subcounty'
            )
            self.assertGreater(filtered.count(), 0)
        
        with self.assertNumQueries(1):
            # Filter by county, subcounty, and ward
            filtered = Address.objects.filter(
                county='Nairobi',
                subcounty='Subcounty 1',
                ward='Ward 1'
            )
    
    def test_address_related_queries_performance(self):
        """Test performance of related queries with Kenyan addresses"""
        # Create addresses
        for i in range(20):
            Address.objects.create(
                customer=self.customer,
                address_type='shipping',
                street_address=f'Street {i}',
                county='Nairobi',
                subcounty=f'Sub {i}',
                ward=f'Ward {i}',
                city='Nairobi',
                postal_code='00100',
                country='Kenya'
            )
        
        # Test prefetch_related performance
        with self.assertNumQueries(2):  # One for customer, one for addresses
            customer = Customer.objects.select_related('user')\
                .prefetch_related('addresses')\
                .get(id=self.customer.id)
            
            # Access addresses (should not trigger additional queries)
            addresses = list(customer.addresses.all())
            self.assertEqual(len(addresses), 20)
            
            # Access Kenyan fields (should not trigger additional queries)
            for addr in addresses:
                _ = addr.county
                _ = addr.subcounty
                _ = addr.ward