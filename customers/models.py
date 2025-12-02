from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Customer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='customer')
    phone = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(blank=True, null=True)
    profile_image = models.ImageField(upload_to='customers/', blank=True, null=True)
    loyalty_points = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.email


class Address(models.Model):
    ADDRESS_TYPES = [
        ('billing', 'Billing'),
        ('shipping', 'Shipping'),
    ]
    
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='addresses')
    address_type = models.CharField(max_length=10, choices=ADDRESS_TYPES)
    street_address = models.CharField(max_length=255)
    apartment = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Addresses'

    def __str__(self):
        return f"{self.customer.user.email} - {self.address_type}"


@receiver(post_save, sender=User)
def create_customer_profile(sender, instance, created, **kwargs):
    if created:
        Customer.objects.create(user=instance)

