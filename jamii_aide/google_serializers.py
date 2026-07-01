from uuid import uuid4
import logging

from django.contrib.auth import get_user_model
from django.conf import settings
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from rest_framework import serializers

from jamii_aide.models import EndUserProfile, UserRole

User = get_user_model()
logger = logging.getLogger(__name__)


def _build_unique_username(email: str) -> str:
    base_username = email.split('@')[0] or f"user_{uuid4().hex[:8]}"
    username = base_username
    while User.objects.filter(username=username).exists():
        username = f"{base_username}_{uuid4().hex[:6]}"
    return username


class GoogleAuthSerializer(serializers.Serializer):
    """Verify a Google ID token and return a local user."""

    credential = serializers.CharField(required=False, allow_blank=False)
    id_token = serializers.CharField(required=False, allow_blank=False)
    token = serializers.CharField(required=False, allow_blank=False)

    default_error_messages = {
        'invalid_token': 'Google sign-in failed. Please try again.',
        'missing_email': 'Google account did not provide an email address.',
        'unverified_email': 'Google account email must be verified before sign-in.',
    }

    def validate(self, attrs):
        token_field = next(
            (field for field in ('credential', 'id_token', 'token') if attrs.get(field)),
            None,
        )
        if not token_field:
            raise serializers.ValidationError({
                'credential': 'Provide credential, id_token, or token.',
            })

        token_value = attrs[token_field].strip()
        client_id = settings.SOCIALACCOUNT_PROVIDERS['google']['APP']['client_id']
        if not client_id:
            raise serializers.ValidationError('Google OAuth is not configured on the server.')

        logger.info(
            'Google auth request payload keys=%s selected_field=%s token_length=%s token_prefix=%s token_suffix=%s',
            sorted(self.initial_data.keys()),
            token_field,
            len(token_value),
            token_value[:6],
            token_value[-6:] if len(token_value) >= 6 else token_value,
        )

        try:
            token_data = id_token.verify_oauth2_token(
                token_value,
                Request(),
                client_id,
                clock_skew_in_seconds=getattr(settings, 'GOOGLE_OAUTH_CLOCK_SKEW_SECONDS', 5),
            )
        except Exception as exc:  # pragma: no cover - logged for production debugging
            logger.exception(
                'Google token verification failed for selected_field=%s: %s: %s',
                token_field,
                exc.__class__.__name__,
                exc,
            )
            raise serializers.ValidationError(self.error_messages['invalid_token'])

        if token_data.get('iss') not in {'accounts.google.com', 'https://accounts.google.com'}:
            raise serializers.ValidationError(self.error_messages['invalid_token'])

        email = token_data.get('email')
        if not email:
            raise serializers.ValidationError(self.error_messages['missing_email'])
        if not token_data.get('email_verified', False):
            raise serializers.ValidationError(self.error_messages['unverified_email'])

        self.context['google_token_data'] = token_data
        self.context['google_token_field'] = token_field
        return attrs

    def create(self, validated_data):
        token_data = self.context['google_token_data']
        email = token_data['email'].strip().lower()
        first_name = token_data.get('given_name', '').strip()
        last_name = token_data.get('family_name', '').strip()

        user = User.objects.filter(email__iexact=email).first()
        if user:
            updates = []
            if first_name and user.first_name != first_name:
                user.first_name = first_name
                updates.append('first_name')
            if last_name and user.last_name != last_name:
                user.last_name = last_name
                updates.append('last_name')
            if not user.is_verified:
                user.is_verified = True
                updates.append('is_verified')
            if updates:
                user.save(update_fields=updates)
        else:
            user = User.objects.create(
                email=email,
                username=_build_unique_username(email),
                first_name=first_name,
                last_name=last_name,
                role=UserRole.USER,
                is_verified=True,
            )
            user.set_unusable_password()
            user.save()

        if user.role == UserRole.USER:
            EndUserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'current_country': '',
                    'current_city': '',
                },
            )

        return user


class GoogleLoginResponseSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    refresh_token = serializers.CharField()
    token_type = serializers.CharField()
    user = serializers.DictField()
