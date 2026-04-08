from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from jamii_aide.views import (
    RegisterView, LoginView, CurrentUserView,
    GoogleLoginView,
    EndUserViewSet,
    FamilyMemberViewSet,
    HealthcareNurseViewSet, AvailabilitySlotViewSet,
    AppointmentViewSet,
    HealthRecordViewSet,
    PaymentViewSet,
    ReviewViewSet,
    NotificationViewSet
)

# Create router and register viewsets
router = DefaultRouter()
router.register(r'end-users', EndUserViewSet, basename='end-user')
router.register(r'family-members', FamilyMemberViewSet, basename='family-member')
router.register(r'nurses', HealthcareNurseViewSet, basename='nurse')
router.register(r'availability-slots', AvailabilitySlotViewSet, basename='availability-slot')
router.register(r'appointments', AppointmentViewSet, basename='appointment')
router.register(r'health-records', HealthRecordViewSet, basename='health-record')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'reviews', ReviewViewSet, basename='review')
router.register(r'notifications', NotificationViewSet, basename='notification')

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),
    path('', include('jamii_aide.urls')),
    
    # Auth endpoints
    path('api/auth/register/', RegisterView.as_view(), name='register'),
    path('api/auth/login/', LoginView.as_view(), name='login'),
    path('api/auth/google/', GoogleLoginView.as_view(), name='google-login'),
    path('api/auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/me/', CurrentUserView.as_view(), name='current-user'),
    
    # Allauth URLs (for social auth)
    path('accounts/', include('allauth.urls')),

    # API routes
    path('api/', include(router.urls)),
    
    # Django REST Framework browsable API
    path('api-auth/', include('rest_framework.urls')),
]
