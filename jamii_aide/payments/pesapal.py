import requests
from django.conf import settings
from django.core.cache import cache

from .exceptions import PaymentGatewayError

TOKEN_CACHE_KEY = 'pesapal_access_token'
IPN_CACHE_KEY = 'pesapal_ipn_id'

# PesaPal's numeric transaction status codes (GetTransactionStatus.status_code).
STATUS_INVALID = 0
STATUS_COMPLETED = 1
STATUS_FAILED = 2
STATUS_REVERSED = 3


def _base_url():
    return (
        'https://pay.pesapal.com/v3'
        if settings.PESAPAL_ENV == 'live'
        else 'https://cybqa.pesapal.com/pesapalv3'
    )


def _require_config():
    missing = [
        name for name in ('PESAPAL_CONSUMER_KEY', 'PESAPAL_CONSUMER_SECRET')
        if not getattr(settings, name, '')
    ]
    if missing:
        raise PaymentGatewayError(
            f"PesaPal is not configured. Missing settings: {', '.join(missing)}"
        )


def get_access_token():
    token = cache.get(TOKEN_CACHE_KEY)
    if token:
        return token

    _require_config()
    try:
        response = requests.post(
            f'{_base_url()}/api/Auth/RequestToken',
            json={
                'consumer_key': settings.PESAPAL_CONSUMER_KEY,
                'consumer_secret': settings.PESAPAL_CONSUMER_SECRET,
            },
            headers={'Accept': 'application/json', 'Content-Type': 'application/json'},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise PaymentGatewayError(f'Failed to authenticate with PesaPal: {exc}') from exc

    data = response.json()
    token = data.get('token')
    if not token:
        raise PaymentGatewayError(f'PesaPal did not return an access token: {data}')

    # Tokens are valid for 5 minutes; refresh a little early.
    cache.set(TOKEN_CACHE_KEY, token, timeout=240)
    return token


def ensure_ipn_registered():
    """Register our IPN endpoint with PesaPal once, caching the returned ipn_id."""
    if settings.PESAPAL_IPN_ID:
        return settings.PESAPAL_IPN_ID

    cached = cache.get(IPN_CACHE_KEY)
    if cached:
        return cached

    token = get_access_token()
    ipn_url = f'{settings.BACKEND_URL.rstrip("/")}/api/payments/pesapal_ipn/'

    try:
        response = requests.post(
            f'{_base_url()}/api/URLSetup/RegisterIPN',
            json={'url': ipn_url, 'ipn_notification_type': 'GET'},
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {token}',
            },
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise PaymentGatewayError(f'Failed to register PesaPal IPN: {exc}') from exc

    data = response.json()
    ipn_id = data.get('ipn_id')
    if not ipn_id:
        raise PaymentGatewayError(f'PesaPal did not return an ipn_id: {data}')

    # No expiry from PesaPal's side; cache for a day and re-register if it falls out.
    cache.set(IPN_CACHE_KEY, ipn_id, timeout=60 * 60 * 24)
    return ipn_id


def submit_order(payment, end_user_profile):
    """Submit a hosted checkout order and store the tracking id + redirect link."""
    _require_config()
    token = get_access_token()
    ipn_id = ensure_ipn_registered()
    user = end_user_profile.user

    body = {
        'id': str(payment.id),
        'currency': payment.currency,
        'amount': float(payment.amount),
        'description': (payment.description or 'Jamii Aide payment')[:100],
        'callback_url': f'{settings.FRONTEND_URL.rstrip("/")}/payments/pesapal/return',
        'notification_id': ipn_id,
        'billing_address': {
            'email_address': user.email or '',
            'phone_number': user.phone or '',
            'country_code': 'KE',
            'first_name': user.first_name or '',
            'last_name': user.last_name or '',
        },
    }

    try:
        response = requests.post(
            f'{_base_url()}/api/Transactions/SubmitOrderRequest',
            json=body,
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {token}',
            },
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise PaymentGatewayError(f'Failed to submit PesaPal order: {exc}') from exc

    data = response.json()
    order_tracking_id = data.get('order_tracking_id')
    redirect_url = data.get('redirect_url')
    if not order_tracking_id or not redirect_url:
        raise PaymentGatewayError(f'PesaPal order submission failed: {data}')

    payment.provider_reference = order_tracking_id
    payment.redirect_url = redirect_url
    payment.save(update_fields=['provider_reference', 'redirect_url'])
    return data


def get_transaction_status(order_tracking_id):
    _require_config()
    token = get_access_token()

    try:
        response = requests.get(
            f'{_base_url()}/api/Transactions/GetTransactionStatus',
            params={'orderTrackingId': order_tracking_id},
            headers={'Accept': 'application/json', 'Authorization': f'Bearer {token}'},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise PaymentGatewayError(f'Failed to query PesaPal transaction status: {exc}') from exc

    return response.json()
