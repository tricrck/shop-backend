from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from .models import Customer, Address


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ['id', 'address_type', 'street_address', 'apartment', 
                  'county', 'subcounty', 'ward', 'city', 'state', 
                  'postal_code', 'country', 'is_default', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def validate(self, attrs):
        # Ensure country is Kenya for this system
        if attrs.get('country', '').lower() != 'kenya':
            raise serializers.ValidationError({
                'country': 'This system only supports Kenyan addresses'
            })
        return attrs


class CustomerSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    addresses = AddressSerializer(many=True, read_only=True)
    
    class Meta:
        model = Customer
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 
                  'phone', 'date_of_birth', 'profile_image', 'loyalty_points', 
                  'addresses', 'created_at', 'updated_at']
        read_only_fields = ['id', 'loyalty_points', 'created_at', 'updated_at']


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    
    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password2', 
                  'first_name', 'last_name', 'phone', 'date_of_birth']
        extra_kwargs = {
            'first_name': {'required': True},
            'last_name': {'required': True},
            'email': {'required': True}
        }

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        
        if User.objects.filter(email=attrs['email']).exists():
            raise serializers.ValidationError({"email": "Email already exists."})
        
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        phone = validated_data.pop('phone', '')
        date_of_birth = validated_data.pop('date_of_birth', None)
        
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            password=validated_data['password']
        )
        
        # Update customer profile created by signal
        customer = user.customer
        customer.phone = phone
        customer.date_of_birth = date_of_birth
        customer.save()
        
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    phone = serializers.CharField(source='customer.phone', required=False)
    date_of_birth = serializers.DateField(source='customer.date_of_birth', required=False, allow_null=True)
    profile_image = serializers.ImageField(source='customer.profile_image', required=False, allow_null=True)
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'date_of_birth', 'profile_image']

    def update(self, instance, validated_data):
        customer_data = validated_data.pop('customer', {})
        
        # Update User fields
        instance.first_name = validated_data.get('first_name', instance.first_name)
        instance.last_name = validated_data.get('last_name', instance.last_name)
        instance.email = validated_data.get('email', instance.email)
        instance.save()
        
        # Update Customer fields
        customer = instance.customer
        customer.phone = customer_data.get('phone', customer.phone)
        customer.date_of_birth = customer_data.get('date_of_birth', customer.date_of_birth)
        
        if 'profile_image' in customer_data:
            customer.profile_image = customer_data['profile_image']
        
        customer.save()
        
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True, validators=[validate_password])
    new_password2 = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({"new_password": "Password fields didn't match."})
        return attrs

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value

    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user