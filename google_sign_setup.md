# Google Sign-In Authentication for Jamii Aide

## 📋 Setup Overview

This guide adds Google Sign-In as the primary authentication method instead of email/password.

---

## Step 1: Install Required Packages

```bash
pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client django-allauth
pip install djangorestframework-google-oauth2
```

Update `requirements_django.txt`:

```
django==4.2.10
djangorestframework==3.14.0
django-filter==24.1
django-cors-headers==4.3.1
djangorestframework-simplejwt>=5.4.0
psycopg2-binary==2.9.10
python-decouple==3.8
pillow==10.1.0
celery==5.3.4
redis==5.0.1
gunicorn==21.2.0
whitenoise==6.6.0
pytest==7.4.4
pytest-django==4.7.0
pytest-cov==4.1.0
factory-boy==3.3.0
faker==22.2.0
black==24.1.1
flake8==7.0.0
isort==5.13.2
google-auth-oauthlib==1.2.0
google-auth-httplib2==0.2.0
google-api-python-client==2.104.0
django-allauth==0.57.0
```

Install:
```bash
pip install -r requirements_django.txt
```

---

## Step 2: Setup Google Cloud Console

### 1. Create Google OAuth Credentials

1. Go to: https://console.cloud.google.com/
2. Create a new project: "Jamii Aide"
3. Go to **APIs & Services** → **Credentials**
4. Click **Create Credentials** → **OAuth 2.0 Client ID**
5. Choose **Web Application**
6. Add **Authorized redirect URIs**:
   ```
   http://localhost:8000/api/auth/google/callback/
   http://localhost:3000/auth/google/callback
   https://yourdomain.com/api/auth/google/callback/
   ```
7. Download the credentials as JSON

### 2. Copy Client ID & Secret

Save these (you'll need them in .env):
- **Client ID**
- **Client Secret**

---

## Step 3: Update Django Settings

**Open `config/settings.py` and add:**

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',  # ← ADD THIS
    
    'rest_framework',
    'django_filters',
    'corsheaders',
    'rest_framework_simplejwt',
    'allauth',  # ← ADD THIS
    'allauth.account',  # ← ADD THIS
    'allauth.socialaccount',  # ← ADD THIS
    'allauth.socialaccount.providers.google',  # ← ADD THIS
    
    'jamii_aide',
]

SITE_ID = 1

# Google OAuth Settings
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',
        },
        'FIELDS': [
            'email',
            'first_name',
            'last_name',
            'picture',
        ]
    }
}

# Rest Framework Settings
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

# JWT Settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
}
```

---

## Step 4: Update .env File

```env
SECRET_KEY=your-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DB_ENGINE=django.db.backends.postgresql
DB_NAME=jamii_aide_db
DB_USER=jamii_user
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

# Google OAuth
GOOGLE_OAUTH_CLIENT_ID=YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=YOUR_GOOGLE_CLIENT_SECRET

# JWT
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:3001
```

---

## Step 5: Create Google Auth Serializer

**Create `jamii_aide/google_serializers.py`:**

```python
from rest_framework import serializers
from django.contrib.auth import get_user_model
from allauth.socialaccount.models import SocialAccount
from rest_framework_simplejwt.tokens import RefreshToken
import requests

User = get_user_model()

class GoogleAuthSerializer(serializers.Serializer):
    """Handle Google OAuth tokens"""
    access_token = serializers.CharField()
    id_token = serializers.CharField(required=False)
    
    def validate_access_token(self, value):
        """Verify Google token and get user info"""
        try:
            # Verify token with Google
            response = requests.get(
                'https://www.googleapis.com/oauth2/v1/userinfo',
                headers={'Authorization': f'Bearer {value}'}
            )
            
            if response.status_code != 200:
                raise serializers.ValidationError('Invalid Google token')
            
            return value
        except Exception as e:
            raise serializers.ValidationError(f'Token verification failed: {str(e)}')
    
    def create(self, validated_data):
        """Get or create user from Google token"""
        access_token = validated_data['access_token']
        
        # Get user info from Google
        response = requests.get(
            'https://www.googleapis.com/oauth2/v1/userinfo',
            headers={'Authorization': f'Bearer {access_token}'}
        )
        
        if response.status_code != 200:
            raise serializers.ValidationError('Failed to get user info from Google')
        
        user_info = response.json()
        email = user_info.get('email')
        first_name = user_info.get('given_name', '')
        last_name = user_info.get('family_name', '')
        picture = user_info.get('picture', '')
        google_id = user_info.get('id')
        
        # Get or create user
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'first_name': first_name,
                'last_name': last_name,
                'username': email.split('@')[0],
                'role': 'DIASPORA_USER',  # Default role
                'is_verified': True,  # Google verified
            }
        )
        
        # Create social account link if new user
        if created:
            SocialAccount.objects.get_or_create(
                user=user,
                provider='google',
                defaults={
                    'uid': google_id,
                    'extra_data': {
                        'picture': picture,
                        'email': email,
                    }
                }
            )
            
            # Create diaspora user profile
            from jamii_aide.models import DasporaUser
            DasporaUser.objects.get_or_create(user=user)
        
        return user


class GoogleLoginResponseSerializer(serializers.Serializer):
    """Response with JWT tokens"""
    access_token = serializers.CharField()
    refresh_token = serializers.CharField()
    user = serializers.SerializerMethodField()
    
    def get_user(self, obj):
        from jamii_aide.serializers import UserSerializer
        return UserSerializer(obj).data
```

---

## Step 6: Create Google Auth View

**Add to `jamii_aide/views.py`:**

```python
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from jamii_aide.google_serializers import GoogleAuthSerializer, GoogleLoginResponseSerializer

class GoogleLoginView(APIView):
    """Login with Google"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        """
        Authenticate with Google token
        
        Expected payload:
        {
            "access_token": "google_access_token"
        }
        """
        serializer = GoogleAuthSerializer(data=request.data)
        
        if serializer.is_valid():
            user = serializer.save()
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            
            response_data = {
                'access_token': str(refresh.access_token),
                'refresh_token': str(refresh),
                'user': {
                    'id': str(user.id),
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'role': user.role,
                }
            }
            
            return Response(response_data, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
```

---

## Step 7: Update URLs

**Update `config/urls.py`:**

```python
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from jamii_aide.views import (
    RegisterView, LoginView, CurrentUserView,
    GoogleLoginView,  # ← ADD THIS
    DasporaUserViewSet,
    FamilyMemberViewSet,
    HealthcareNurseViewSet, AvailabilitySlotViewSet,
    AppointmentViewSet,
    HealthRecordViewSet,
    PrescriptionViewSet,
    PaymentViewSet,
    ReviewViewSet
)

# Router setup...
router = DefaultRouter()
router.register(r'diaspora-users', DasporaUserViewSet, basename='diaspora-user')
router.register(r'family-members', FamilyMemberViewSet, basename='family-member')
router.register(r'nurses', HealthcareNurseViewSet, basename='nurse')
router.register(r'availability-slots', AvailabilitySlotViewSet, basename='availability-slot')
router.register(r'appointments', AppointmentViewSet, basename='appointment')
router.register(r'health-records', HealthRecordViewSet, basename='health-record')
router.register(r'prescriptions', PrescriptionViewSet, basename='prescription')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'reviews', ReviewViewSet, basename='review')

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Auth endpoints
    path('api/auth/register/', RegisterView.as_view(), name='register'),
    path('api/auth/login/', LoginView.as_view(), name='login'),
    path('api/auth/google/', GoogleLoginView.as_view(), name='google-login'),  # ← ADD THIS
    path('api/auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/me/', CurrentUserView.as_view(), name='current-user'),
    
    # Allauth URLs (for social auth)
    path('accounts/', include('allauth.urls')),  # ← ADD THIS
    
    # API routes
    path('api/', include(router.urls)),
    
    # Django REST Framework auth
    path('api-auth/', include('rest_framework.urls')),
]
```

---

## Step 8: Run Migrations

```bash
python manage.py migrate
python manage.py runserver
```

---

## 🧪 Test Google Login

### With cURL:

```powershell
# Get Google token first (from frontend)
$googleToken = "YOUR_GOOGLE_ACCESS_TOKEN"

curl -X POST http://localhost:8000/api/auth/google/ `
  -H "Content-Type: application/json" `
  -d '{
    "access_token": "'$googleToken'"
  }' | ConvertFrom-Json | ConvertTo-Json -Depth 3
```

---

## 💻 React Frontend Integration

**Install Google OAuth package:**

```bash
npm install @react-oauth/google
```

**Google Login Component:**

```jsx
import { GoogleOAuthProvider, GoogleLogin } from '@react-oauth/google';
import axios from 'axios';

function LoginPage() {
  const handleGoogleLogin = async (credentialResponse) => {
    try {
      // Send token to backend
      const response = await axios.post(
        'http://localhost:8000/api/auth/google/',
        {
          access_token: credentialResponse.credential
        }
      );
      
      // Save tokens
      localStorage.setItem('access_token', response.data.access_token);
      localStorage.setItem('refresh_token', response.data.refresh_token);
      
      // Redirect to dashboard
      window.location.href = '/dashboard';
    } catch (error) {
      console.error('Login failed:', error);
    }
  };

  return (
    <GoogleOAuthProvider clientId="YOUR_CLIENT_ID.apps.googleusercontent.com">
      <GoogleLogin onSuccess={handleGoogleLogin} />
    </GoogleOAuthProvider>
  );
}

export default LoginPage;
```

---

## 🔑 Complete Flow

```
1. User clicks "Sign in with Google"
2. Google OAuth popup appears
3. User logs in with Google account
4. Frontend receives Google access token
5. Frontend sends token to: POST /api/auth/google/
6. Backend verifies token with Google
7. Backend creates/gets user
8. Backend returns JWT tokens
9. Frontend stores JWT tokens
10. Frontend uses JWT for API requests
```

---

## ✅ Advantages of Google Sign-In

✅ No password management  
✅ Faster registration  
✅ Higher security (Google handles 2FA)  
✅ Better user experience  
✅ Access to Google user profile  
✅ One-click authentication  

---

## 📝 Optional: Add Other Providers

Want to add Facebook, GitHub, etc.? Same process:

```python
# settings.py
INSTALLED_APPS = [
    ...
    'allauth.socialaccount.providers.facebook',
    'allauth.socialaccount.providers.github',
    'allauth.socialaccount.providers.apple',
]
```

Then create similar views for each provider.

---

## 🚀 Deploy to Production

Remember to:
1. Update Google Cloud Console with production URLs
2. Update CORS_ORIGINS in .env
3. Set DEBUG=False
4. Use HTTPS
5. Update ALLOWED_HOSTS

---

**Your Jamii Aide now has Google Sign-In!** 