from rest_framework import serializers
from django.contrib.auth import get_user_model
import jwt

User = get_user_model()

class GoogleAuthSerializer(serializers.Serializer):
    """Handle Google OAuth JWT tokens"""
    credential = serializers.CharField()  # ← CHANGE THIS
    
    def validate_credential(self, value):
        try:
            jwt.decode(value, options={"verify_signature": False})
            return value
        except Exception as e:
            raise serializers.ValidationError(f'Invalid token: {str(e)}')
    
    def create(self, validated_data):
        token = validated_data['credential']
        decoded = jwt.decode(token, options={"verify_signature": False})
        
        email = decoded.get('email')
        first_name = decoded.get('given_name', '')
        last_name = decoded.get('family_name', '')
        google_id = decoded.get('sub')
        
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'first_name': first_name,
                'last_name': last_name,
                'username': email.split('@')[0],
                'role': 'END_USER',
                'is_verified': True,
            }
        )
        
        if created:
            from jamii_aide.models import EndUserProfile
            EndUserProfile.objects.get_or_create(user=user)
        
        return user


class GoogleLoginResponseSerializer(serializers.Serializer):
    """Response with JWT tokens"""
    access_token = serializers.CharField()
    refresh_token = serializers.CharField()
    user = serializers.SerializerMethodField()
    
    def get_user(self, obj):
        from jamii_aide.serializers import UserSerializer
        return UserSerializer(obj).data
