from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from .models import Order, OrderStatusHistory
from .notifications import OrderNotifications
import logging

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Order)
def order_pre_save(sender, instance, **kwargs):
    """Handle order pre-save operations"""
    if instance.pk:
        old_instance = Order.objects.get(pk=instance.pk)
        
        # Check if status changed
        if old_instance.status != instance.status:
            # This will be handled in post_save to ensure instance is saved
            pass


@receiver(post_save, sender=Order)
def order_post_save(sender, instance, created, **kwargs):
    """Handle order post-save operations"""
    if created:
        # Send confirmation email for new orders
        OrderNotifications.send_email_notification(
            instance, 
            'order_confirmation'
        )
        
        # Create initial status history
        OrderStatusHistory.objects.create(
            order=instance,
            old_status='',
            new_status='pending',
            changed_by=None,  # System
            notes='Order created'
        )
        
        logger.info(f"New order created: {instance.order_number}")
    
    else:
        # Check for status changes
        try:
            old_instance = Order.objects.get(pk=instance.pk)
            
            if old_instance.status != instance.status:
                # Create status history
                OrderStatusHistory.objects.create(
                    order=instance,
                    old_status=old_instance.status,
                    new_status=instance.status,
                    changed_by=None,  # System (will be overridden if changed by user)
                    notes='Status updated'
                )
                
                # Send notifications based on status change
                if instance.status == 'shipped':
                    OrderNotifications.send_email_notification(
                        instance, 
                        'order_shipped'
                    )
                    
                    # Send SMS if configured
                    message = f"Your order {instance.order_number} has shipped! Tracking: {instance.tracking_number}"
                    OrderNotifications.send_sms_notification(instance, message)
                
                elif instance.status == 'delivered':
                    OrderNotifications.send_email_notification(
                        instance, 
                        'order_delivered'
                    )
                
                elif instance.status == 'cancelled':
                    OrderNotifications.send_email_notification(
                        instance, 
                        'order_cancelled'
                    )
                
                logger.info(f"Order {instance.order_number} status changed from {old_instance.status} to {instance.status}")
        
        except Order.DoesNotExist:
            pass


@receiver(post_save, sender=OrderStatusHistory)
def status_history_post_save(sender, instance, created, **kwargs):
    """Handle status history post-save"""
    if created and instance.changed_by:
        # Log user-initiated status changes
        logger.info(
            f"User {instance.changed_by} changed order {instance.order.order_number} "
            f"from {instance.old_status} to {instance.new_status}"
        )