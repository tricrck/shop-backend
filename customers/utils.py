import secrets
import string
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.tokens import PasswordResetTokenGenerator
import six

class AccountActivationTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        return (
            six.text_type(user.pk) + six.text_type(timestamp) + 
            six.text_type(user.is_active)
        )

account_activation_token = AccountActivationTokenGenerator()

def generate_reset_code(length=6):
    """Generate a random alphanumeric reset code."""
    characters = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(characters) for _ in range(length))

def send_password_reset_email(user, reset_code):
    """Send password reset email with code."""
    # Generate token for URL
    token = account_activation_token.make_token(user)
    uid = six.text_type(user.pk)
    
    # Build reset URL
    reset_url = f"{settings.CORS_ALLOWED_ORIGINS[0]}?uid={uid}&token={token}&code={reset_code}"
    
    # Render email template
    context = {
        'user': user,
        'reset_code': reset_code,
        'reset_url': reset_url,
    }
    
    html_message = render_to_string('reset_email.html', context)
    plain_message = f"""
Hello {user.first_name},

We received a request to reset your password for your SoundWaveAudio account.

Your password reset code is: {reset_code}

This code will expire in 24 hours.

If you didn't request a password reset, you can safely ignore this email.

Best regards,
The SoundWaveAudio Team
"""
    
    send_mail(
        subject='Password Reset Request - SoundWaveAudio',
        message=plain_message,
        html_message=html_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )