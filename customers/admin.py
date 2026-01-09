from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import Customer, Address


class AddressInline(admin.TabularInline):
    model = Address
    extra = 0
    fields = ['address_type', 'street_address', 'city', 'county', 'subcounty', 
              'ward', 'postal_code', 'country', 'is_default']
    readonly_fields = ['created_at']


class CustomerInline(admin.StackedInline):
    model = Customer
    can_delete = False
    verbose_name_plural = 'Customer Profile'
    fields = ['phone', 'date_of_birth', 'profile_image', 'loyalty_points']
    readonly_fields = ['created_at', 'updated_at', 'loyalty_points']


class UserAdmin(BaseUserAdmin):
    inlines = [CustomerInline]
    list_display = ['username', 'email', 'first_name', 'last_name', 'is_staff', 'get_loyalty_points']
    list_filter = ['is_staff', 'is_superuser', 'is_active', 'date_joined']
    search_fields = ['username', 'email', 'first_name', 'last_name', 'customer__phone']
    
    def get_loyalty_points(self, obj):
        if hasattr(obj, 'customer'):
            return obj.customer.loyalty_points
        return 0
    get_loyalty_points.short_description = 'Loyalty Points'
    get_loyalty_points.admin_order_field = 'customer__loyalty_points'


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['get_username', 'get_email', 'phone', 'loyalty_points', 'created_at']
    list_filter = ['created_at', 'updated_at']
    search_fields = ['user__username', 'user__email', 'user__first_name', 'user__last_name', 'phone']
    readonly_fields = ['created_at', 'updated_at', 'loyalty_points']
    inlines = [AddressInline]
    
    fieldsets = (
        ('User Information', {
            'fields': ('user',)
        }),
        ('Customer Details', {
            'fields': ('phone', 'date_of_birth', 'profile_image', 'loyalty_points')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_username(self, obj):
        return obj.user.username
    get_username.short_description = 'Username'
    get_username.admin_order_field = 'user__username'
    
    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'
    get_email.admin_order_field = 'user__email'
    
    actions = ['add_100_points', 'add_500_points', 'reset_points']
    
    def add_100_points(self, request, queryset):
        for customer in queryset:
            customer.loyalty_points += 100
            customer.save()
        self.message_user(request, f"Added 100 points to {queryset.count()} customers")
    add_100_points.short_description = "Add 100 loyalty points"
    
    def add_500_points(self, request, queryset):
        for customer in queryset:
            customer.loyalty_points += 500
            customer.save()
        self.message_user(request, f"Added 500 points to {queryset.count()} customers")
    add_500_points.short_description = "Add 500 loyalty points"
    
    def reset_points(self, request, queryset):
        queryset.update(loyalty_points=0)
        self.message_user(request, f"Reset points for {queryset.count()} customers")
    reset_points.short_description = "Reset loyalty points to 0"


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ['get_customer_name', 'address_type', 'county', 'subcounty', 
                    'ward', 'city', 'is_default', 'created_at']
    list_filter = ['address_type', 'county', 'is_default', 'created_at', 'country']
    search_fields = ['customer__user__username', 'customer__user__email', 
                     'street_address', 'city', 'county', 'subcounty', 'ward', 'postal_code']
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('Customer', {
            'fields': ('customer',)
        }),
        ('Address Type', {
            'fields': ('address_type', 'is_default')
        }),
        ('Location Details', {
            'fields': ('street_address', 'apartment', 'city')
        }),
        ('Kenyan Administrative Divisions', {
            'fields': ('county', 'subcounty', 'ward'),
            'description': 'Administrative divisions specific to Kenya'
        }),
        ('Postal Information', {
            'fields': ('postal_code', 'state', 'country')
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def get_customer_name(self, obj):
        return obj.customer.user.get_full_name() or obj.customer.user.username
    get_customer_name.short_description = 'Customer'
    get_customer_name.admin_order_field = 'customer__user__username'
    
    def save_model(self, request, obj, form, change):
        """
        Handle default address logic when saving through admin.
        If marking as default, unset other defaults of same type.
        """
        if obj.is_default:
            # Unset other default addresses of the same type for this customer
            Address.objects.filter(
                customer=obj.customer,
                address_type=obj.address_type
            ).exclude(pk=obj.pk).update(is_default=False)
        
        super().save_model(request, obj, form, change)


# Unregister the default User admin and register our custom one
admin.site.unregister(User)
admin.site.register(User, UserAdmin)