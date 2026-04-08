from uuid import uuid4

from django.contrib.auth import get_user_model
from django.conf import settings
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from rest_framework import serializers

from jamii_aide.models import EndUserProfile, UserRole

User = get_user_model()


def _build_unique_username(email: str) -> str:
    base_username = email.split('@')[0] or f"user_{uuid4().hex[:8]}"
    username = base_username
    while User.objects.filter(username=username).exists():
        username = f"{base_username}_{uuid4().hex[:6]}"
    return username


class GoogleAuthSerializer(serializers.Serializer):
    """Verify a Google ID token and return a local user."""

    credential = serializers.CharField()

    default_error_messages = {
        'invalid_token': 'Google sign-in failed. Please try again.',
        'missing_email': 'Google account did not provide an email address.',
        'unverified_email': 'Google account email must be verified before sign-in.',
    }

    def validate_credential(self, value):
        client_id = settings.SOCIALACCOUNT_PROVIDERS['google']['APP']['client_id']
        if not client_id:
            raise serializers.ValidationError('Google OAuth is not configured on the server.')

        try:
            token_data = id_token.verify_oauth2_token(value, Request(), client_id)
        except ValueError:
            raise serializers.ValidationError(self.error_messages['invalid_token'])

        if token_data.get('iss') not in {'accounts.google.com', 'https://accounts.google.com'}:
            raise serializers.ValidationError(self.error_messages['invalid_token'])

        email = token_data.get('email')
        if not email:
            raise serializers.ValidationError(self.error_messages['missing_email'])
        if not token_data.get('email_verified', False):
            raise serializers.ValidationError(self.error_messages['unverified_email'])

        self.context['google_token_data'] = token_data
        return value

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
