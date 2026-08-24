import base64
import re
from datetime import datetime

import requests
from django.conf import settings
from django.core.cache import cache

from .exceptions import PaymentGatewayError

CACHE_KEY = 'mpesa_access_token'


def _base_url():
    return (
        'https://api.safaricom.co.ke'
        if settings.MPESA_ENV == 'production'
        else 'https://sandbox.safaricom.co.ke'
    )


def _require_config():
    missing = [
        name for name in (
            'MPESA_CONSUMER_KEY', 'MPESA_CONSUMER_SECRET',
            'MPESA_SHORTCODE', 'MPESA_PASSKEY', 'MPESA_CALLBACK_URL',
        )
        if not getattr(settings, name, '')
    ]
    if missing:
        raise PaymentGatewayError(
            f"M-Pesa is not configured. Missing settings: {', '.join(missing)}"
        )


def normalize_phone_number(phone_number):
    """Convert a Kenyan phone number to Daraja's required 2547XXXXXXXX format."""
    digits = re.sub(r'\D', '', phone_number or '')
    if digits.startswith('254') and len(digits) == 12:
        return digits
    if digits.startswith('0') and len(digits) == 10:
        return '254' + digits[1:]
    if digits.startswith('7') and len(digits) == 9:
        return '254' + digits
    raise PaymentGatewayError(f"'{phone_number}' is not a valid Kenyan phone number.")


def get_access_token():
    token = cache.get(CACHE_KEY)
    if token:
        return token

    _require_config()
    try:
        response = requests.get(
            f'{_base_url()}/oauth/v1/generate',
            params={'grant_type': 'client_credentials'},
            auth=(settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET),
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise PaymentGatewayError(f'Failed to authenticate with M-Pesa: {exc}') from exc

    data = response.json()
    token = data.get('access_token')
    if not token:
        raise PaymentGatewayError(f'M-Pesa did not return an access token: {data}')

    expires_in = int(data.get('expires_in', 3599))
    cache.set(CACHE_KEY, token, timeout=max(expires_in - 60, 60))
    return token


def _password_and_timestamp():
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    raw = f'{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}'
    password = base64.b64encode(raw.encode()).decode()
    return password, timestamp


def stk_push(payment, phone_number):
    """Initiate an STK push and store the CheckoutRequestID on the payment."""
    _require_config()
    phone = normalize_phone_number(phone_number)
    password, timestamp = _password_and_timestamp()
    token = get_access_token()

    body = {
        'BusinessShortCode': settings.MPESA_SHORTCODE,
        'Password': password,
        'Timestamp': timestamp,
        'TransactionType': 'CustomerPayBillOnline',
        'Amount': int(payment.amount),
        'PartyA': phone,
        'PartyB': settings.MPESA_SHORTCODE,
        'PhoneNumber': phone,
        'CallBackURL': settings.MPESA_CALLBACK_URL,
        'AccountReference': str(payment.id),
        'TransactionDesc': payment.description or 'Jamii Aide payment',
    }

    try:
        response = requests.post(
            f'{_base_url()}/mpesa/stkpush/v1/processrequest',
            json=body,
            headers={'Authorization': f'Bearer {token}'},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise PaymentGatewayError(f'Failed to initiate M-Pesa STK push: {exc}') from exc

    data = response.json()
    checkout_request_id = data.get('CheckoutRequestID')
    if not checkout_request_id:
        raise PaymentGatewayError(f'M-Pesa STK push failed: {data}')

    payment.provider_reference = checkout_request_id
    payment.save(update_fields=['provider_reference'])
    return data


def query_status(checkout_request_id):
    """Query the status of a previously-initiated STK push."""
    _require_config()
    password, timestamp = _password_and_timestamp()
    token = get_access_token()

    body = {
        'BusinessShortCode': settings.MPESA_SHORTCODE,
        'Password': password,
        'Timestamp': timestamp,
        'CheckoutRequestID': checkout_request_id,
    }

    try:
        response = requests.post(
            f'{_base_url()}/mpesa/stkpushquery/v1/query',
            json=body,
            headers={'Authorization': f'Bearer {token}'},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise PaymentGatewayError(f'Failed to query M-Pesa transaction status: {exc}') from exc

    return response.json()
