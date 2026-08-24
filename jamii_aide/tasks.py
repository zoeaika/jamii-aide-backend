import logging
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)

@shared_task
def send_email_task(subject, message, recipient_list):
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@jamiiaide.com'),
            recipient_list=recipient_list,
            fail_silently=True,
        )
    except Exception as e:
        logger.error('Failed to send email to %s: %s', recipient_list, str(e))

@shared_task
def send_payment_receipt_task(payment_id):
    from jamii_aide.models import Payment
    try:
        payment = Payment.objects.select_related('end_user_profile__user').get(id=payment_id)
        user = payment.end_user_profile.user
        if user.email:
            receipt_number = payment.mpesa_receipt_number or payment.provider_reference or payment.id
            send_mail(
                subject=f"Payment Receipt: {receipt_number}",
                message=f"Dear {user.first_name or 'User'},\n\nYour payment of {payment.currency} {payment.amount} was successful.\nReceipt: {receipt_number}\n\nThank you for using Jamii Aide.",
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@jamiiaide.com'),
                recipient_list=[user.email],
                fail_silently=True,
            )
    except Exception as e:
        logger.error('Failed to send payment receipt for payment %s: %s', payment_id, str(e))