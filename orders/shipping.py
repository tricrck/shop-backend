import requests
from django.conf import settings
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class ShippingIntegration:
    """God-Level Shipping Integration System"""
    
    @staticmethod
    def get_shipping_rates(order, destination):
        """Get shipping rates from multiple carriers"""
        rates = []
        
        # DHL Integration
        dhl_rates = ShippingIntegration._get_dhl_rates(order, destination)
        if dhl_rates:
            rates.extend(dhl_rates)
        
        # FedEx Integration
        fedex_rates = ShippingIntegration._get_fedex_rates(order, destination)
        if fedex_rates:
            rates.extend(fedex_rates)
        
        # UPS Integration
        ups_rates = ShippingIntegration._get_ups_rates(order, destination)
        if ups_rates:
            rates.extend(ups_rates)
        
        # Sort by price
        rates.sort(key=lambda x: x['cost'])
        
        return rates
    
    @staticmethod
    def _get_dhl_rates(order, destination):
        """Get rates from DHL API"""
        if not hasattr(settings, 'DHL_API_KEY'):
            return []
        
        try:
            # Calculate package dimensions
            packages = ShippingIntegration._prepare_packages(order)
            
            payload = {
                'rateRequest': {
                    'shipperDetails': {
                        'postalCode': settings.SHIP_FROM_POSTAL_CODE,
                        'countryCode': settings.SHIP_FROM_COUNTRY
                    },
                    'receiverDetails': {
                        'postalCode': destination['postal_code'],
                        'countryCode': destination['country_code']
                    },
                    'packages': packages,
                    'plannedShippingDateAndTime': datetime.now().isoformat(),
                    'isCustomsDeclarable': False,
                    'unitOfMeasurement': 'metric',
                    'returnStandardProductsOnly': True
                }
            }
            
            headers = {
                'Authorization': f'Bearer {settings.DHL_API_KEY}',
                'Content-Type': 'application/json'
            }
            
            response = requests.post(
                'https://api.dhl.com/shipping/v2/rates',
                json=payload,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                rates = []
                
                for product in data.get('products', []):
                    rates.append({
                        'carrier': 'DHL',
                        'service': product['productName'],
                        'cost': float(product['totalPrice'][0]['price']),
                        'currency': product['totalPrice'][0]['currency'],
                        'estimated_days': product.get('deliveryCapabilities', {}).get('estimatedDeliveryDateAndTime', ''),
                        'service_code': product['productCode']
                    })
                
                return rates
            
        except Exception as e:
            logger.error(f"DHL API error: {str(e)}")
        
        return []
    
    @staticmethod
    def _get_fedex_rates(order, destination):
        """Get rates from FedEx API"""
        # Similar implementation for FedEx
        return []
    
    @staticmethod
    def _get_ups_rates(order, destination):
        """Get rates from UPS API"""
        # Similar implementation for UPS
        return []
    
    @staticmethod
    def _prepare_packages(order):
        """Prepare package dimensions for shipping"""
        packages = []
        
        # Group items into packages (simplified)
        total_weight = order.weight_total or 1.0
        
        packages.append({
            'weight': total_weight,
            'dimensions': {
                'length': 20,
                'width': 15,
                'height': 10
            }
        })
        
        return packages
    
    @staticmethod
    def create_shipment(order, shipping_method):
        """Create shipment with carrier"""
        # Implementation for creating shipment label
        pass
    
    @staticmethod
    def track_shipment(tracking_number, carrier):
        """Get tracking information from carrier"""
        if carrier.lower() == 'dhl':
            return ShippingIntegration._track_dhl(tracking_number)
        elif carrier.lower() == 'fedex':
            return ShippingIntegration._track_fedex(tracking_number)
        elif carrier.lower() == 'ups':
            return ShippingIntegration._track_ups(tracking_number)
        
        return None
    
    @staticmethod
    def _track_dhl(tracking_number):
        """Track DHL shipment"""
        if not hasattr(settings, 'DHL_API_KEY'):
            return None
        
        try:
            headers = {
                'Authorization': f'Bearer {settings.DHL_API_KEY}',
                'Accept': 'application/json'
            }
            
            response = requests.get(
                f'https://api.dhl.com/tracking/v2/track/{tracking_number}',
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
        
        except Exception as e:
            logger.error(f"DHL tracking error: {str(e)}")
        
        return None