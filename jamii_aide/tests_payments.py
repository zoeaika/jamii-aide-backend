from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from jamii_aide.models import CustomUser, EndUserProfile, Payment, PaymentMethod, PaymentStatus
from jamii_aide.payments import mpesa, pesapal
from jamii_aide.payments.exceptions import PaymentGatewayError


MPESA_SETTINGS = dict(
    MPESA_CONSUMER_KEY='key',
    MPESA_CONSUMER_SECRET='secret',
    MPESA_SHORTCODE='174379',
    MPESA_PASSKEY='passkey',
    MPESA_CALLBACK_URL='https://backend.example.com/api/payments/mpesa_callback/',
)

PESAPAL_SETTINGS = dict(
    PESAPAL_CONSUMER_KEY='key',
    PESAPAL_CONSUMER_SECRET='secret',
)


class MpesaGatewayTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = CustomUser.objects.create_user(
            username='payer1', email='payer1@example.com', password='StrongPass123!', phone='0712345678',
        )
        self.end_user_profile = EndUserProfile.objects.create(
            user=self.user, current_country='Kenya',
        )
        self.payment = Payment.objects.create(
            end_user_profile=self.end_user_profile,
            amount=1000,
            method=PaymentMethod.MPESA,
            description='Test payment',
        )

    def test_stk_push_raises_when_unconfigured(self):
        with self.assertRaises(PaymentGatewayError):
            mpesa.stk_push(self.payment, '0712345678')

    def test_normalize_phone_number_formats(self):
        self.assertEqual(mpesa.normalize_phone_number('0712345678'), '254712345678')
        self.assertEqual(mpesa.normalize_phone_number('712345678'), '254712345678')
        self.assertEqual(mpesa.normalize_phone_number('254712345678'), '254712345678')

    def test_normalize_phone_number_rejects_invalid(self):
        with self.assertRaises(PaymentGatewayError):
            mpesa.normalize_phone_number('12345')

    @override_settings(**MPESA_SETTINGS)
    @patch('jamii_aide.payments.mpesa.requests.post')
    @patch('jamii_aide.payments.mpesa.requests.get')
    def test_stk_push_stores_checkout_request_id(self, mock_get, mock_post):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {'access_token': 'tok123', 'expires_in': '3599'},
        )
        mock_get.return_value.raise_for_status = lambda: None
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {
                'MerchantRequestID': 'merchant-1',
                'CheckoutRequestID': 'ws_CO_123',
                'ResponseCode': '0',
                'ResponseDescription': 'Success',
            },
        )
        mock_post.return_value.raise_for_status = lambda: None

        mpesa.stk_push(self.payment, '0712345678')

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.provider_reference, 'ws_CO_123')


class PesapalGatewayTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = CustomUser.objects.create_user(
            username='payer2', email='payer2@example.com', password='StrongPass123!', phone='0712345678',
        )
        self.end_user_profile = EndUserProfile.objects.create(
            user=self.user, current_country='Kenya',
        )
        self.payment = Payment.objects.create(
            end_user_profile=self.end_user_profile,
            amount=1000,
            method=PaymentMethod.PESAPAL,
            description='Test payment',
        )

    def test_submit_order_raises_when_unconfigured(self):
        with self.assertRaises(PaymentGatewayError):
            pesapal.submit_order(self.payment, self.end_user_profile)

    @override_settings(**PESAPAL_SETTINGS, PESAPAL_IPN_ID='ipn-123', FRONTEND_URL='https://app.example.com')
    @patch('jamii_aide.payments.pesapal.requests.post')
    def test_submit_order_stores_tracking_id_and_redirect_url(self, mock_post):
        def side_effect(url, **kwargs):
            if 'RequestToken' in url:
                response = Mock(status_code=200, json=lambda: {'token': 'tok123'})
            else:
                response = Mock(status_code=200, json=lambda: {
                    'order_tracking_id': 'track-123',
                    'merchant_reference': str(self.payment.id),
                    'redirect_url': 'https://cybqa.pesapal.com/checkout/track-123',
                })
            response.raise_for_status = lambda: None
            return response

        mock_post.side_effect = side_effect

        pesapal.submit_order(self.payment, self.end_user_profile)

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.provider_reference, 'track-123')
        self.assertEqual(self.payment.redirect_url, 'https://cybqa.pesapal.com/checkout/track-123')


class PaymentCallbackViewTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = CustomUser.objects.create_user(
            username='payer3', email='payer3@example.com', password='StrongPass123!', phone='0712345678',
        )
        self.end_user_profile = EndUserProfile.objects.create(
            user=self.user, current_country='Kenya',
        )

    def test_mpesa_callback_marks_payment_completed(self):
        payment = Payment.objects.create(
            end_user_profile=self.end_user_profile,
            amount=1000,
            method=PaymentMethod.MPESA,
            description='Test payment',
            provider_reference='ws_CO_123',
        )
        url = reverse('payment-mpesa-callback')
        body = {
            'Body': {
                'stkCallback': {
                    'CheckoutRequestID': 'ws_CO_123',
                    'ResultCode': 0,
                    'ResultDesc': 'Success',
                    'CallbackMetadata': {
                        'Item': [
                            {'Name': 'Amount', 'Value': 1000},
                            {'Name': 'MpesaReceiptNumber', 'Value': 'NLJ7RT61SV'},
                            {'Name': 'TransactionDate', 'Value': 20240101120000},
                            {'Name': 'PhoneNumber', 'Value': 254712345678},
                        ]
                    },
                }
            }
        }
        response = self.client.post(url, body, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.COMPLETED)
        self.assertEqual(payment.mpesa_receipt_number, 'NLJ7RT61SV')

    def test_mpesa_callback_marks_payment_failed(self):
        payment = Payment.objects.create(
            end_user_profile=self.end_user_profile,
            amount=1000,
            method=PaymentMethod.MPESA,
            description='Test payment',
            provider_reference='ws_CO_456',
        )
        url = reverse('payment-mpesa-callback')
        body = {
            'Body': {
                'stkCallback': {
                    'CheckoutRequestID': 'ws_CO_456',
                    'ResultCode': 1032,
                    'ResultDesc': 'Request cancelled by user',
                }
            }
        }
        response = self.client.post(url, body, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.FAILED)
        self.assertEqual(payment.failure_reason, 'Request cancelled by user')

    def test_mpesa_callback_returns_404_for_unknown_payment(self):
        url = reverse('payment-mpesa-callback')
        body = {'Body': {'stkCallback': {'CheckoutRequestID': 'unknown', 'ResultCode': 0}}}
        response = self.client.post(url, body, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch('jamii_aide.payments.pesapal.get_transaction_status')
    def test_pesapal_ipn_marks_payment_completed(self, mock_status):
        payment = Payment.objects.create(
            end_user_profile=self.end_user_profile,
            amount=1000,
            method=PaymentMethod.PESAPAL,
            description='Test payment',
            provider_reference='track-123',
        )
        mock_status.return_value = {
            'payment_status_description': 'Completed',
            'status_code': pesapal.STATUS_COMPLETED,
        }
        url = reverse('payment-pesapal-ipn')
        response = self.client.get(url, {
            'OrderTrackingId': 'track-123',
            'OrderMerchantReference': str(payment.id),
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.COMPLETED)

    @patch('jamii_aide.payments.pesapal.get_transaction_status')
    def test_pesapal_ipn_marks_payment_failed(self, mock_status):
        payment = Payment.objects.create(
            end_user_profile=self.end_user_profile,
            amount=1000,
            method=PaymentMethod.PESAPAL,
            description='Test payment',
            provider_reference='track-456',
        )
        mock_status.return_value = {
            'payment_status_description': 'Failed',
            'status_code': pesapal.STATUS_FAILED,
        }
        url = reverse('payment-pesapal-ipn')
        response = self.client.get(url, {
            'OrderTrackingId': 'track-456',
            'OrderMerchantReference': str(payment.id),
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.FAILED)
