from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from twilio.rest import Client
import logging

logger = logging.getLogger(__name__)


class OrderNotifications:
    """God-Level Notification System for Orders"""
    
    @staticmethod
    def send_email_notification(order, notification_type, context=None):
        """Send email notification"""
        templates = {
            'order_confirmation': {
                'subject': 'Order Confirmation - {order_number}',
                'template_html': 'emails/order_confirmation.html',
                'template_txt': 'emails/order_confirmation.txt'
            },
            'order_shipped': {
                'subject': 'Your Order Has Shipped! - {order_number}',
                'template_html': 'emails/order_shipped.html',
                'template_txt': 'emails/order_shipped.txt'
            },
            'order_delivered': {
                'subject': 'Order Delivered - {order_number}',
                'template_html': 'emails/order_delivered.html',
                'template_txt': 'emails/order_delivered.txt'
            },
            'order_cancelled': {
                'subject': 'Order Cancelled - {order_number}',
                'template_html': 'emails/order_cancelled.html',
                'template_txt': 'emails/order_cancelled.txt'
            },
            'payment_failed': {
                'subject': 'Payment Failed - {order_number}',
                'template_html': 'emails/payment_failed.html',
                'template_txt': 'emails/payment_failed.txt'
            },
        }
        
        if notification_type not in templates:
            logger.error(f"Unknown notification type: {notification_type}")
            return
        
        template = templates[notification_type]
        
        # Prepare context
        if context is None:
            context = {}
        
        context.update({
            'order': order,
            'site_name': 'SoundWaveAudio',
            'support_email': settings.SUPPORT_EMAIL
        })
        
        # Render templates
        subject = template['subject'].format(order_number=order.order_number)
        html_content = render_to_string(template['template_html'], context)
        text_content = render_to_string(template['template_txt'], context)
        
        # Determine recipient
        if order.is_guest:
            recipient = order.guest_email
        else:
            recipient = order.customer.user.email
        
        # Send email
        try:
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[recipient],
                reply_to=[settings.SUPPORT_EMAIL]
            )
            email.attach_alternative(html_content, "text/html")
            email.send()
            
            logger.info(f"Email notification sent: {notification_type} for order {order.order_number}")
            
        except Exception as e:
            logger.error(f"Failed to send email notification: {str(e)}")
    
    @staticmethod
    def send_sms_notification(order, message):
        """Send SMS notification"""
        if not hasattr(settings, 'TWILIO_ACCOUNT_SID'):
            logger.warning("Twilio not configured")
            return
        
        try:
            # Determine phone number
            if order.is_guest and order.guest_phone:
                phone_number = order.guest_phone
            elif order.customer and order.customer.phone:
                phone_number = order.customer.phone
            else:
                return
            
            client = Client(
                settings.TWILIO_ACCOUNT_SID,
                settings.TWILIO_AUTH_TOKEN
            )
            
            message = client.messages.create(
                body=message,
                from_=settings.TWILIO_PHONE_NUMBER,
                to=phone_number
            )
            
            logger.info(f"SMS sent to {phone_number}: {message.sid}")
            
        except Exception as e:
            logger.error(f"Failed to send SMS: {str(e)}")
    
    @staticmethod
    def send_admin_alert(order, alert_type, message):
        """Send alert to admin"""
        if not hasattr(settings, 'ADMIN_EMAILS'):
            return
        
        try:
            subject = f"Admin Alert: {alert_type} - Order {order.order_number}"
            
            context = {
                'order': order,
                'alert_type': alert_type,
                'message': message,
                'timestamp': timezone.now()
            }
            
            html_content = render_to_string('emails/admin_alert.html', context)
            text_content = render_to_string('emails/admin_alert.txt', context)
            
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=settings.ADMIN_EMAILS
            )
            email.attach_alternative(html_content, "text/html")
            email.send()
            
            logger.info(f"Admin alert sent: {alert_type} for order {order.order_number}")
            
        except Exception as e:
            logger.error(f"Failed to send admin alert: {str(e)}")