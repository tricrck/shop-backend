from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
from .models import Order
import requests


@shared_task
def send_order_confirmation_email(order_id):
    """Send order confirmation email"""
    try:
        order = Order.objects.get(id=order_id)
        
        subject = f"Order Confirmation - {order.order_number}"
        
        context = {
            'order': order,
            'items': order.items.all(),
            'site_name': 'SoundWaveAudio'
        }
        
        html_message = render_to_string('emails/order_confirmation.html', context)
        text_message = render_to_string('emails/order_confirmation.txt', context)
        
        recipient = order.customer.user.email if order.customer else order.guest_email
        
        send_mail(
            subject=subject,
            message=text_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            html_message=html_message,
            fail_silently=False,
        )
        
        return f"Confirmation email sent for order {order.order_number}"
    except Exception as e:
        return f"Error sending confirmation email: {str(e)}"


@shared_task
def send_shipping_notification_email(order_id):
    """Send shipping notification email"""
    try:
        order = Order.objects.get(id=order_id)
        
        if not order.tracking_number:
            return "No tracking number available"
        
        subject = f"Your Order Has Shipped! - {order.order_number}"
        
        context = {
            'order': order,
            'tracking_url': order.tracking_url or f"https://tracking.com/{order.tracking_number}",
            'site_name': 'SoundWaveAudio'
        }
        
        html_message = render_to_string('emails/order_shipped.html', context)
        text_message = render_to_string('emails/order_shipped.txt', context)
        
        recipient = order.customer.user.email if order.customer else order.guest_email
        
        send_mail(
            subject=subject,
            message=text_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            html_message=html_message,
            fail_silently=False,
        )
        
        return f"Shipping notification sent for order {order.order_number}"
    except Exception as e:
        return f"Error sending shipping notification: {str(e)}"


@shared_task
def update_order_status_task(order_id, old_status, new_status):
    """Handle order status updates"""
    order = Order.objects.get(id=order_id)
    
    # Send emails based on status change
    if new_status == 'shipped' and old_status != 'shipped':
        send_shipping_notification_email.delay(order_id)
    
    elif new_status == 'delivered' and old_status != 'delivered':
        # Send delivery confirmation
        pass
    
    elif new_status == 'cancelled' and old_status != 'cancelled':
        # Send cancellation email
        pass
    
    return f"Status updated from {old_status} to {new_status} for order {order.order_number}"


@shared_task
def check_delayed_orders():
    """Check for orders that are delayed in shipping"""
    threshold_date = timezone.now() - timezone.timedelta(days=7)
    
    delayed_orders = Order.objects.filter(
        status='shipped',
        shipped_date__lt=threshold_date,
        delivered_date__isnull=True
    )
    
    for order in delayed_orders:
        # Send delayed order notification to admin
        send_mail(
            subject=f"Delayed Order Alert - {order.order_number}",
            message=f"Order {order.order_number} shipped on {order.shipped_date} is still not delivered.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.ADMIN_EMAIL],
            fail_silently=True,
        )
    
    return f"Checked {delayed_orders.count()} delayed orders"


@shared_task
def sync_tracking_updates():
    """Sync tracking updates from carriers"""
    # This would integrate with carrier APIs
    orders_with_tracking = Order.objects.exclude(
        tracking_number=''
    ).filter(
        status__in=['shipped', 'out_for_delivery']
    )
    
    for order in orders_with_tracking:
        # Call carrier API to get latest status
        # Update order status based on carrier response
        pass
    
    return "Tracking updates synced"