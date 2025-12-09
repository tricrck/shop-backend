from rest_framework import serializers
from django_filters import rest_framework as filters
from .models import (
    MpesaConfiguration, MpesaTransaction, MpesaCallback,
    MpesaRefund, MpesaPaymentMethod
)


# ============ SERIALIZERS ============

class MpesaConfigurationSerializer(serializers.ModelSerializer):
    """Serializer for M-Pesa configuration"""
    
    class Meta:
        model = MpesaConfiguration
        fields = [
            'id', 'name', 'environment', 'business_short_code',
            'callback_url', 'is_active', 'is_default',
            'max_requests_per_minute', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def validate(self, data):
        # Add custom validation
        if data.get('is_active') and not data.get('consumer_key'):
            raise serializers.ValidationError("Consumer key is required for active configuration")
        return data


class MpesaTransactionListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for transaction lists"""
    
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    customer_email = serializers.CharField(source='customer.user.email', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)
    
    class Meta:
        model = MpesaTransaction
        fields = [
            'id', 'transaction_id', 'checkout_request_id',
            'mpesa_receipt_number', 'transaction_type', 'transaction_type_display',
            'status', 'status_display', 'phone_number', 'amount',
            'order_number', 'customer_email', 'initiated_at', 'completed_at'
        ]


class MpesaTransactionSerializer(serializers.ModelSerializer):
    """Detailed serializer for transactions"""
    
    order_details = serializers.SerializerMethodField()
    customer_details = serializers.SerializerMethodField()
    configuration_name = serializers.CharField(source='configuration.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)
    is_successful = serializers.BooleanField(read_only=True)
    can_retry = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = MpesaTransaction
        fields = [
            'id', 'transaction_id', 'merchant_request_id', 'checkout_request_id',
            'mpesa_receipt_number', 'transaction_type', 'transaction_type_display',
            'status', 'status_display', 'phone_number', 'amount',
            'account_reference', 'transaction_desc', 'result_code', 'result_desc',
            'balance', 'transaction_date', 'retry_count', 'max_retries',
            'order_details', 'customer_details', 'configuration_name',
            'is_successful', 'can_retry', 'initiated_at', 'completed_at',
            'failed_at', 'updated_at'
        ]
        read_only_fields = ['transaction_id']
    
    def get_order_details(self, obj):
        if obj.order:
            return {
                'id': obj.order.id,
                'order_number': obj.order.order_number,
                'status': obj.order.status,
                'payment_status': obj.order.payment_status,
                'total': str(obj.order.total)
            }
        return None
    
    def get_customer_details(self, obj):
        if obj.customer:
            return {
                'id': obj.customer.id,
                'email': obj.customer.user.email,
                'name': f"{obj.customer.user.first_name} {obj.customer.user.last_name}".strip()
            }
        return None


class MpesaCallbackSerializer(serializers.ModelSerializer):
    """Serializer for M-Pesa callbacks"""
    
    transaction_details = serializers.SerializerMethodField()
    
    class Meta:
        model = MpesaCallback
        fields = [
            'id', 'callback_id', 'callback_type', 'checkout_request_id',
            'merchant_request_id', 'raw_payload', 'is_processed',
            'processed_at', 'processing_error', 'transaction_details',
            'received_at'
        ]
    
    def get_transaction_details(self, obj):
        if obj.transaction:
            return {
                'id': obj.transaction.id,
                'status': obj.transaction.status,
                'amount': str(obj.transaction.amount)
            }
        return None


class MpesaRefundSerializer(serializers.ModelSerializer):
    """Serializer for M-Pesa refunds"""
    
    original_transaction_details = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = MpesaRefund
        fields = [
            'id', 'refund_id', 'amount', 'reason', 'status', 'status_display',
            'result_code', 'result_desc', 'reversal_id',
            'original_transaction_details', 'initiated_at', 'completed_at'
        ]
        read_only_fields = ['refund_id', 'initiated_at', 'completed_at']
    
    def get_original_transaction_details(self, obj):
        return {
            'mpesa_receipt_number': obj.original_transaction.mpesa_receipt_number,
            'amount': str(obj.original_transaction.amount),
            'phone_number': obj.original_transaction.phone_number
        }


class MpesaPaymentMethodSerializer(serializers.ModelSerializer):
    """Serializer for payment methods"""
    
    class Meta:
        model = MpesaPaymentMethod
        fields = [
            'id', 'phone_number', 'is_default', 'is_verified',
            'successful_transactions', 'failed_transactions',
            'last_used_at', 'created_at'
        ]
        read_only_fields = [
            'is_verified', 'successful_transactions', 'failed_transactions',
            'last_used_at', 'created_at'
        ]
    
    def validate_phone_number(self, value):
        """Validate and format phone number"""
        # Remove spaces and special characters
        phone = ''.join(filter(str.isdigit, value))
        
        # Kenya number validation
        if phone.startswith('0'):
            phone = '254' + phone[1:]
        elif phone.startswith('254'):
            pass
        elif phone.startswith('+254'):
            phone = phone[1:]
        else:
            raise serializers.ValidationError("Invalid phone number format")
        
        if len(phone) != 12:
            raise serializers.ValidationError("Phone number must be 12 digits (254XXXXXXXXX)")
        
        return phone


class InitiatePaymentSerializer(serializers.Serializer):
    """Serializer for initiating payment"""
    
    order_id = serializers.IntegerField(required=True)
    phone_number = serializers.CharField(required=True, max_length=20)
    
    def validate_phone_number(self, value):
        """Validate and format phone number"""
        phone = ''.join(filter(str.isdigit, value))
        
        if phone.startswith('0'):
            phone = '254' + phone[1:]
        elif not phone.startswith('254'):
            phone = '254' + phone
        
        if len(phone) != 12:
            raise serializers.ValidationError(
                "Phone number must be in format: 254XXXXXXXXX or 0XXXXXXXXX"
            )
        
        return phone


class CheckPaymentStatusSerializer(serializers.Serializer):
    """Serializer for checking payment status"""
    
    checkout_request_id = serializers.CharField(required=True)
    order_id = serializers.IntegerField(required=False)