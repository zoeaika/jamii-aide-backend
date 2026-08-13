from django.contrib import messages
from django.conf import settings
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from rest_framework import viewsets, status, permissions, filters
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.db.models import Q, Avg
from decimal import Decimal
from datetime import time
import uuid
import logging

from jamii_aide.models import (
    CustomUser, EndUserProfile, Organization, OrganizationAdministrator,
    HealthcareNurse, FamilyMember,
    AvailabilitySlot, Appointment, HealthRecord,
    Payment, Review, AppointmentStatus, PaymentStatus, UserRole,
    NurseStatus, ServiceType, ProfessionalType,
    Notification, NotificationEventType, NurseEarning
)
from jamii_aide.serializers import (
    UserSerializer, RegisterSerializer, LoginSerializer,
    EndUserProfileSerializer, EndUserProfileUpdateSerializer,
    EndUserSerializer, EndUserUpdateSerializer,
    OrganizationSerializer, OrganizationAdministratorSerializer,
    FamilyMemberSerializer, FamilyMemberDetailSerializer,
    HealthcareNurseSerializer, HealthcareNurseDetailSerializer,
    HealthcareNurseUpdateSerializer, HealthcareNurseCreateSerializer,
    AvailabilitySlotSerializer,
    AppointmentSerializer, AppointmentDetailSerializer,
    AppointmentCreateSerializer, AppointmentUpdateSerializer,
    AppointmentSuggestNurseSerializer, AppointmentDecisionSerializer,
    HealthRecordSerializer, HealthRecordCreateSerializer,
    HealthRecordUpdateSerializer,
    PaymentSerializer, PaymentInitiateSerializer,
    ReviewSerializer, ReviewCreateSerializer, ReviewDetailSerializer,
    NotificationSerializer, NurseEarningSerializer
)
from jamii_aide.google_serializers import GoogleAuthSerializer, GoogleLoginResponseSerializer
from jamii_aide.forms import SignupForm, LoginForm

from jamii_aide.mixins import ApiDebugMixin
from jamii_aide.tasks import send_email_task, send_payment_receipt_task

logger = logging.getLogger('jamii_aide.appointments')


def enqueue_task_or_run(task, *args, **kwargs):
    """Queue a Celery task; optionally fall back to inline execution."""
    try:
        task.delay(*args, **kwargs)
        return
    except Exception as exc:
        if not getattr(settings, 'CELERY_INLINE_FALLBACK', False):
            logger.error(
                'Celery enqueue failed for task=%s. Inline fallback disabled; task skipped. error=%s',
                getattr(task, 'name', repr(task)),
                exc,
            )
            return

        logger.warning(
            'Celery enqueue failed for task=%s. Running inline fallback. error=%s',
            getattr(task, 'name', repr(task)),
            exc,
        )

    try:
        task(*args, **kwargs)
    except Exception:
        logger.exception(
            'Inline fallback failed for task=%s',
            getattr(task, 'name', repr(task)),
        )


def create_notification(*, recipient, appointment, event_type, title, message):
    Notification.objects.create(
        recipient=recipient,
        appointment=appointment,
        event_type=event_type,
        title=title,
        message=message,
    )

    if recipient.email:
        enqueue_task_or_run(
            send_email_task,
            subject=title,
            message=message,
            recipient_list=[recipient.email],
        )


def is_end_user(user):
    return user.get_effective_role() == UserRole.USER


def is_admin_user(user):
    return user.get_effective_role() == UserRole.ADMIN


def is_organization_admin_user(user):
    return user.get_effective_role() == UserRole.ORGANIZATION_ADMIN


DEFAULT_WORKING_HOURS = (time(8, 0), time(17, 0))


def seed_default_availability(nurse):
    """Give a newly-approved nurse a default Mon-Fri 8am-5pm schedule if they have none yet."""
    if AvailabilitySlot.objects.filter(nurse=nurse).exists():
        return
    start, end = DEFAULT_WORKING_HOURS
    AvailabilitySlot.objects.bulk_create([
        AvailabilitySlot(nurse=nurse, day_of_week=day, start_time=start, end_time=end, is_available=True)
        for day in range(5)  # Monday-Friday
    ])


def get_end_user_profile(user):
    if not is_end_user(user):
        raise PermissionDenied('Only end users can access this resource.')
    profile, _ = EndUserProfile.objects.get_or_create(
        user=user,
        defaults={
            'current_country': '',
            'current_city': '',
        },
    )
    return profile


def get_nurse_profile(user):
    if user.get_effective_role() != UserRole.NURSE:
        raise PermissionDenied('Only healthcare nurses can access this resource.')
    nurse, _ = HealthcareNurse.objects.get_or_create(
        user=user,
        defaults={
            'license_number': '',
            'license_expiry': timezone.now().date(),
            'years_experience': 0,
            'status': NurseStatus.PENDING,
        },
    )
    return nurse


def get_organization_admin_profile(user):
    if not is_organization_admin_user(user):
        raise PermissionDenied('Only organization administrators can access this resource.')
    profile = OrganizationAdministrator.objects.select_related('organization').filter(
        user=user,
    ).first()
    if not profile:
        raise PermissionDenied('No organization admin profile is linked to this account.')
    return profile


def get_dashboard_url_for_role(user):
    effective_role = user.get_effective_role()
    if effective_role == UserRole.NURSE:
        return '/dashboard/nurse'
    if effective_role == UserRole.ADMIN:
        return '/dashboard/admin'
    if effective_role == UserRole.ORGANIZATION_ADMIN:
        return '/dashboard/organization-admin'
    return '/dashboard/user'


def normalize_role_value(value):
    if value is None:
        return None

    normalized = str(value).strip().lower()
    role_aliases = {
        'user': UserRole.USER,
        'end_user': UserRole.USER,
        'enduser': UserRole.USER,
        'diaspora_user': UserRole.USER,
        'nurse': UserRole.NURSE,
        'healthcare_nurse': UserRole.NURSE,
        'admin': UserRole.ADMIN,
        'administrator': UserRole.ADMIN,
        'organization_admin': UserRole.ORGANIZATION_ADMIN,
        'organization administrator': UserRole.ORGANIZATION_ADMIN,
        'organization-administrator': UserRole.ORGANIZATION_ADMIN,
        'organizationadministrator': UserRole.ORGANIZATION_ADMIN,
    }
    return role_aliases.get(normalized)


class SignupView(View):
    template_name = 'jamii_aide/signup.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect(get_dashboard_url_for_role(request.user))
        return render(request, self.template_name, {'form': SignupForm()})

    def post(self, request):
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            EndUserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'current_country': '',
                    'current_city': '',
                },
            )
            auth_login(request, user)
            messages.success(request, 'Your account has been created successfully.')
            return redirect(get_dashboard_url_for_role(user))
        messages.error(request, 'Please correct the errors below.')
        return render(request, self.template_name, {'form': form}, status=400)


class LoginPageView(View):
    template_name = 'jamii_aide/login.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect(get_dashboard_url_for_role(request.user))
        return render(request, self.template_name, {'form': LoginForm(request=request)})

    def post(self, request):
        form = LoginForm(request=request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            messages.success(request, 'Welcome back.')
            return redirect(get_dashboard_url_for_role(user))
        messages.error(request, 'Login failed. Please try again.')
        return render(request, self.template_name, {'form': form}, status=400)


@method_decorator(login_required, name='dispatch')
class RoleRedirectView(View):
    def get(self, request):
        return redirect(get_dashboard_url_for_role(request.user))


@method_decorator(login_required, name='dispatch')
class DashboardView(View):
    template_name = 'jamii_aide/dashboard.html'
    expected_role = None
    heading = ''

    def get(self, request):
        if request.user.get_effective_role() != self.expected_role:
            messages.error(request, 'You do not have permission to view that dashboard.')
            return redirect(get_dashboard_url_for_role(request.user))

        context = {
            'heading': self.heading,
            'effective_role': request.user.get_effective_role(),
            'effective_role_display': request.user.get_effective_role_display(),
        }

        if request.user.get_effective_role() == UserRole.NURSE:
            nurse = get_nurse_profile(request.user)
            context['assigned_appointments'] = Appointment.objects.select_related(
                'family_member', 'nurse__user', 'suggested_nurse__user', 'end_user_profile__user'
            ).filter(Q(nurse=nurse) | Q(suggested_nurse=nurse)).order_by('appointment_date', 'start_time')
        elif request.user.get_effective_role() == UserRole.ADMIN:
            context['recent_appointments'] = Appointment.objects.select_related(
                'family_member', 'nurse__user', 'suggested_nurse__user', 'end_user_profile__user'
            ).order_by('-updated_at')[:12]
        elif request.user.get_effective_role() == UserRole.ORGANIZATION_ADMIN:
            org_admin = get_organization_admin_profile(request.user)
            context['organization_name'] = org_admin.organization.name
            context['recent_appointments'] = Appointment.objects.select_related(
                'family_member', 'nurse__user', 'suggested_nurse__user', 'end_user_profile__user'
            ).filter(
                Q(nurse__organization=org_admin.organization) |
                Q(suggested_nurse__organization=org_admin.organization)
            ).distinct().order_by('-updated_at')[:12]
        elif request.user.get_effective_role() == UserRole.USER:
            end_user_profile = get_end_user_profile(request.user)
            context['recent_appointments'] = Appointment.objects.select_related(
                'family_member', 'nurse__user', 'suggested_nurse__user', 'end_user_profile__user'
            ).filter(end_user_profile=end_user_profile).order_by('-updated_at')[:12]

        return render(
            request,
            self.template_name,
            context,
        )


class UserDashboardView(DashboardView):
    expected_role = UserRole.USER
    heading = 'User Dashboard'


class NurseDashboardView(DashboardView):
    expected_role = UserRole.NURSE
    heading = 'Nurse Dashboard'


class AdminDashboardView(DashboardView):
    expected_role = UserRole.ADMIN
    heading = 'Admin Dashboard'


class OrganizationAdminDashboardView(DashboardView):
    expected_role = UserRole.ORGANIZATION_ADMIN
    heading = 'Organization Admin Dashboard'

# ============ AUTHENTICATION VIEWS ============

class RegisterView(APIView):
    """Register new user"""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()

            # Create role-specific profile
            if user.role == UserRole.USER:
                EndUserProfile.objects.create(
                    user=user,
                    current_country=request.data.get('current_country', ''),
                    current_city=request.data.get('current_city', '')
                )
            elif user.role == UserRole.NURSE:
                HealthcareNurse.objects.create(
                    user=user,
                    license_number=f"PENDING-{user.id.hex[:10].upper()}",
                    license_expiry=timezone.now().date(),
                    years_experience=0,
                    status=NurseStatus.PENDING,
                    is_verified=False,
                )
            elif user.role == UserRole.ORGANIZATION_ADMIN:
                organization = Organization.objects.create(
                    name=getattr(user, '_pending_organization_name', '') or f"{user.get_full_name()}'s Organization",
                    is_active=False,
                )
                OrganizationAdministrator.objects.create(
                    user=user,
                    organization=organization,
                )

            refresh = RefreshToken.for_user(user)
            return Response({
                'access_token': str(refresh.access_token),
                'refresh_token': str(refresh),
                'token_type': 'bearer',
                'user': UserSerializer(user).data
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LoginView(APIView):
    """Login user"""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            user.last_login = timezone.now()
            user.save()
            
            refresh = RefreshToken.for_user(user)
            return Response({
                'access_token': str(refresh.access_token),
                'refresh_token': str(refresh),
                'token_type': 'bearer',
                'user': UserSerializer(user).data
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CurrentUserView(APIView):
    """Get current user profile"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

class GoogleLoginView(APIView):
    """Login with Google"""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        """
        Authenticate with Google JWT token
        
        Expected payload:
        {
            "credential": "google_jwt_token"
        }
        """
        serializer = GoogleAuthSerializer(data=request.data)
        
        if serializer.is_valid():
            user = serializer.save()
            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])

            refresh = RefreshToken.for_user(user)
            response_data = {
                'access_token': str(refresh.access_token),
                'refresh_token': str(refresh),
                'token_type': 'bearer',
                'user': UserSerializer(user).data,
            }
            response_serializer = GoogleLoginResponseSerializer(data=response_data)
            response_serializer.is_valid(raise_exception=True)
            return Response(response_serializer.validated_data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
# ============ USER MANAGEMENT ============

class EndUserProfileViewSet(viewsets.ModelViewSet):
    """End user profiles."""
    serializer_class = EndUserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ['partial_update', 'update']:
            return EndUserProfileUpdateSerializer
        return EndUserProfileSerializer

    def get_queryset(self):
        if is_admin_user(self.request.user):
            return EndUserProfile.objects.select_related('user').order_by('-created_at')
        profile = get_end_user_profile(self.request.user)
        return EndUserProfile.objects.filter(id=profile.id)

    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get current user's end-user profile."""
        end_user_profile = get_end_user_profile(request.user)
        serializer = self.get_serializer(end_user_profile)
        return Response(serializer.data)


class EndUserViewSet(EndUserProfileViewSet):
    """End user profile endpoints."""

    def get_serializer_class(self):
        if self.action in ['partial_update', 'update']:
            return EndUserUpdateSerializer
        return EndUserSerializer


class OrganizationViewSet(ApiDebugMixin, viewsets.ModelViewSet):
    """System-admin management of organizations."""
    queryset = Organization.objects.all().order_by('name', 'id')
    serializer_class = OrganizationSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']

    def check_permissions(self, request):
        super().check_permissions(request)
        if not is_admin_user(request.user):
            raise PermissionDenied('Only admins can manage organizations.')


class OrganizationAdministratorViewSet(viewsets.ModelViewSet):
    """System-admin management of organization administrator profiles."""
    queryset = OrganizationAdministrator.objects.select_related('organization', 'user').all().order_by('-created_at')
    serializer_class = OrganizationAdministratorSerializer
    permission_classes = [permissions.IsAuthenticated]

    def check_permissions(self, request):
        super().check_permissions(request)
        if self.action == 'me' and is_organization_admin_user(request.user):
            return
        if not is_admin_user(request.user):
            raise PermissionDenied('Only admins can manage organization administrators.')

    @action(detail=False, methods=['get'], url_path='me')
    def me(self, request):
        profile = get_organization_admin_profile(request.user)
        serializer = self.get_serializer(profile)
        return Response(serializer.data)


class AdminUserViewSet(ApiDebugMixin, viewsets.ModelViewSet):
    """Admin management of users (role assignment, etc.)"""
    queryset = CustomUser.objects.all().order_by('-created_at', '-id')
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['first_name', 'last_name', 'email']

    def check_permissions(self, request):
        super().check_permissions(request)
        if not is_admin_user(request.user):
            raise PermissionDenied('Only admins can manage users.')

    def get_object(self):
        """Resolve by user UUID; for compatibility allow EndUserProfile UUIDs too."""
        try:
            return super().get_object()
        except Http404:
            profile = EndUserProfile.objects.filter(id=self.kwargs.get('pk')).select_related('user').first()
            if profile:
                return profile.user
            raise

    @action(detail=True, methods=['post'], url_path='change-role')
    def change_role(self, request, pk=None):
        user = self.get_object()
        new_role = normalize_role_value(request.data.get('role'))
        organization_id = request.data.get('organization_id')

        if new_role is None:
            raise ValidationError({'role': 'Invalid role provided.'})

        if new_role == UserRole.ADMIN or user.get_effective_role() == UserRole.ADMIN:
            raise ValidationError({'role': 'Admin role cannot be granted or changed through this action.'})

        organization = None
        if new_role == UserRole.ORGANIZATION_ADMIN:
            if not organization_id:
                raise ValidationError({'organization_id': 'organization_id is required for organization_admin role.'})
            organization = Organization.objects.filter(id=organization_id, is_active=True).first()
            if not organization:
                raise ValidationError({'organization_id': 'Invalid organization_id provided.'})
            
        user.role = new_role
        user.save(update_fields=['role'])

        # Ensure the correct profile exists for the new role
        if new_role == UserRole.NURSE:
            nurse_profile, _ = HealthcareNurse.objects.get_or_create(
                user=user,
                defaults={
                    'license_number': f'PENDING-{str(user.id)[:8]}', # Unique placeholder
                    'license_expiry': timezone.now().date(),
                    'years_experience': 0,
                    'status': NurseStatus.APPROVED,
                    'is_verified': True,
                    'is_active': True,
                }
            )
            seed_default_availability(nurse_profile)
        elif new_role == UserRole.USER:
            EndUserProfile.objects.get_or_create(
                user=user,
                defaults={'current_country': '', 'current_city': ''}
            )
        elif new_role == UserRole.ORGANIZATION_ADMIN:
            OrganizationAdministrator.objects.update_or_create(
                user=user,
                defaults={
                    'organization': organization,
                }
            )

        return Response(UserSerializer(user).data)

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        user = self.get_object()
        user.is_verified = True
        user.is_active = True
        user.save(update_fields=['is_verified', 'is_active'])

        effective_role = user.get_effective_role()
        if effective_role == UserRole.NURSE:
            HealthcareNurse.objects.filter(user=user).update(
                status=NurseStatus.APPROVED,
                is_verified=True,
                is_active=True,
            )
            nurse_profile = HealthcareNurse.objects.filter(user=user).first()
            if nurse_profile:
                seed_default_availability(nurse_profile)
        elif effective_role == UserRole.ORGANIZATION_ADMIN:
            org_admin = OrganizationAdministrator.objects.filter(user=user).select_related('organization').first()
            if org_admin and org_admin.organization:
                org_admin.organization.is_active = True
                org_admin.organization.save(update_fields=['is_active'])

        return Response(UserSerializer(user).data)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        user = self.get_object()
        user.is_verified = False
        user.is_active = False
        user.save(update_fields=['is_verified', 'is_active'])

        effective_role = user.get_effective_role()
        if effective_role == UserRole.NURSE:
            HealthcareNurse.objects.filter(user=user).update(
                status=NurseStatus.SUSPENDED,
                is_verified=False,
                is_active=False,
            )
        elif effective_role == UserRole.ORGANIZATION_ADMIN:
            org_admin = OrganizationAdministrator.objects.filter(user=user).select_related('organization').first()
            if org_admin and org_admin.organization:
                org_admin.organization.is_active = False
                org_admin.organization.save(update_fields=['is_active'])

        return Response(UserSerializer(user).data)

# ============ FAMILY MEMBERS ============

class FamilyMemberViewSet(ApiDebugMixin, viewsets.ModelViewSet):
    """Family member management"""
    serializer_class = FamilyMemberSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['first_name', 'last_name']
    ordering_fields = ['created_at', 'first_name', 'last_name']
    ordering = ['-created_at', '-id']

    def get_queryset(self):
        end_user_profile = get_end_user_profile(self.request.user)
        return FamilyMember.objects.filter(end_user_profile=end_user_profile)

    def create(self, request, *args, **kwargs):
        logger.info(
            'Family member create attempt user_id=%s role=%s payload_keys=%s',
            getattr(request.user, 'id', None),
            getattr(request.user, 'role', None),
            sorted(request.data.keys()),
        )
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(
                'Family member create validation failed user_id=%s errors=%s payload=%s',
                getattr(request.user, 'id', None),
                serializer.errors,
                dict(request.data),
            )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        logger.info(
            'Family member created id=%s user_id=%s',
            serializer.instance.id if serializer.instance else None,
            getattr(request.user, 'id', None),
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        end_user_profile = get_end_user_profile(self.request.user)
        serializer.save(end_user_profile=end_user_profile)

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return FamilyMemberDetailSerializer
        return FamilyMemberSerializer

# ============ HEALTHCARE NURSES ============

class HealthcareNurseViewSet(ApiDebugMixin, viewsets.ModelViewSet):
    """Healthcare nurse profiles"""
    queryset = HealthcareNurse.objects.all()
    serializer_class = HealthcareNurseSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'professional_type', 'is_verified', 'is_active']
    search_fields = ['user__first_name', 'user__last_name', 'specializations']
    ordering_fields = ['rating', 'total_appointments', 'created_at']
    ordering = ['-rating', '-created_at', '-id']

    def get_queryset(self):
        queryset = HealthcareNurse.objects.select_related('user', 'organization')
        if is_admin_user(self.request.user):
            return queryset
        if is_organization_admin_user(self.request.user):
            org_admin = get_organization_admin_profile(self.request.user)
            return queryset.filter(organization=org_admin.organization)
        return queryset.filter(is_active=True, status=NurseStatus.APPROVED)

    def get_queryset(self):
        queryset = HealthcareNurse.objects.select_related('user', 'organization')
        if is_admin_user(self.request.user):
            return queryset
        if is_organization_admin_user(self.request.user):
            org_admin = get_organization_admin_profile(self.request.user)
            return queryset.filter(organization=org_admin.organization)
        return queryset.filter(is_active=True, status=NurseStatus.APPROVED)

    def get_serializer_class(self):
        if self.action in ['retrieve', 'me']:
            return HealthcareNurseDetailSerializer
        elif self.action in ['update', 'partial_update']:
            return HealthcareNurseUpdateSerializer
        elif self.action == 'complete_profile':
            return HealthcareNurseCreateSerializer
        return HealthcareNurseSerializer

    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get current nurse profile"""
        nurse = get_nurse_profile(request.user)
        serializer = self.get_serializer(nurse)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def complete_profile(self, request):
        """Complete nurse profile after registration"""
        nurse = get_nurse_profile(request.user)
        serializer = HealthcareNurseCreateSerializer(nurse, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            nurse.status = NurseStatus.APPROVED
            nurse.is_verified = True
            nurse.is_active = True
            nurse.save()
            seed_default_availability(nurse)
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='toggle-availability')
    def toggle_availability(self, request, pk=None):
        """Nurse-controlled on/off switch for accepting new auto-matched requests."""
        nurse = self.get_object()
        if not (is_admin_user(request.user) or request.user.id == nurse.user_id):
            raise PermissionDenied('You can only manage your own availability toggle.')

        if 'is_accepting_requests' in request.data:
            nurse.is_accepting_requests = bool(request.data['is_accepting_requests'])
        else:
            nurse.is_accepting_requests = not nurse.is_accepting_requests
        nurse.save(update_fields=['is_accepting_requests'])
        return Response(self.get_serializer(nurse).data)

    @action(detail=True, methods=['get', 'post'])
    def availability(self, request, pk=None):
        """Get or create nurse availability slots."""
        nurse = self.get_object()
        if request.method == 'POST':
            if is_admin_user(request.user) or request.user.id == nurse.user_id:
                serializer = AvailabilitySlotSerializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                serializer.save(nurse=nurse)
                return Response(serializer.data, status=status.HTTP_201_CREATED)

            if is_organization_admin_user(request.user):
                org_admin = get_organization_admin_profile(request.user)
                if nurse.organization_id == org_admin.organization_id:
                    serializer = AvailabilitySlotSerializer(data=request.data)
                    serializer.is_valid(raise_exception=True)
                    serializer.save(nurse=nurse)
                    return Response(serializer.data, status=status.HTTP_201_CREATED)

            raise PermissionDenied('You can only manage your own availability.')

        slots = nurse.availability_slots.filter(is_available=True)
        serializer = AvailabilitySlotSerializer(slots, many=True)
        return Response(serializer.data)

    def perform_update(self, serializer):
        nurse = self.get_object()
        requested_org = serializer.validated_data.get('organization', nurse.organization)

        if is_admin_user(self.request.user):
            serializer.save()
            return

        if self.request.user.id == nurse.user_id:
            if requested_org != nurse.organization:
                raise PermissionDenied('You cannot change your own organization assignment.')
            serializer.save()
            return

        if is_organization_admin_user(self.request.user):
            org_admin = get_organization_admin_profile(self.request.user)
            if nurse.organization_id == org_admin.organization_id:
                if requested_org and requested_org.id != org_admin.organization_id:
                    raise PermissionDenied('You can only assign nurses to your organization.')
                serializer.save()
                return

        raise PermissionDenied('You do not have permission to update this nurse profile.')

    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get nurse performance statistics"""
        nurse = self.get_object()
        return Response({
            'total_appointments': nurse.total_appointments,
            'completed_appointments': nurse.completed_appointments,
            'rating': float(nurse.rating),
            'total_reviews': nurse.total_reviews,
        })

# ============ AVAILABILITY SLOTS ============

class AvailabilitySlotViewSet(viewsets.ModelViewSet):
    """Nurse availability management"""
    serializer_class = AvailabilitySlotSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        nurse = get_nurse_profile(self.request.user)
        return AvailabilitySlot.objects.filter(nurse=nurse)

    def perform_create(self, serializer):
        nurse = get_nurse_profile(self.request.user)
        serializer.save(nurse=nurse)

# ============ APPOINTMENTS ============

class AppointmentViewSet(ApiDebugMixin, viewsets.ModelViewSet):
    """Appointment management"""
    queryset = Appointment.objects.all()
    serializer_class = AppointmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'nurse', 'family_member', 'appointment_date']
    ordering_fields = ['appointment_date', 'created_at']
    ordering = ['-appointment_date', '-created_at', '-id']

    def get_serializer_class(self):
        if self.action == 'create':
            return AppointmentCreateSerializer
        elif self.action == 'suggest_nurse':
            return AppointmentSuggestNurseSerializer
        elif self.action == 'decision':
            return AppointmentDecisionSerializer
        elif self.action in ['update', 'partial_update']:
            return AppointmentUpdateSerializer
        elif self.action == 'retrieve':
            return AppointmentDetailSerializer
        return AppointmentSerializer

    def _is_admin(self, user):
        return is_admin_user(user)

    def _is_org_admin(self, user):
        return is_organization_admin_user(user)

    def _org_admin_organization(self, user):
        if not self._is_org_admin(user):
            return None
        return get_organization_admin_profile(user).organization

    def get_queryset(self):
        user = self.request.user
        if self._is_admin(user):
            return Appointment.objects.select_related(
                'family_member', 'nurse', 'suggested_nurse', 'end_user_profile__user'
            )
        if self._is_org_admin(user):
            organization = self._org_admin_organization(user)
            return Appointment.objects.select_related(
                'family_member', 'nurse', 'suggested_nurse', 'end_user_profile__user'
            ).filter(
                Q(nurse__organization=organization) |
                Q(suggested_nurse__organization=organization)
            ).distinct()
        if is_end_user(user):
            return Appointment.objects.select_related(
                'family_member', 'nurse', 'suggested_nurse', 'end_user_profile__user'
            ).filter(end_user_profile__user=user)
        if user.role == UserRole.NURSE:
            nurse = HealthcareNurse.objects.filter(user=user).first()
            if not nurse:
                return Appointment.objects.none()
            # Privacy-first scope: nurse users only see appointments assigned to them.
            # Include both direct assignment and suggested assignment for compatibility
            # with older records that may not have `nurse` populated yet.
            return Appointment.objects.select_related(
                'family_member', 'nurse', 'suggested_nurse', 'end_user_profile__user'
            ).filter(Q(nurse=nurse) | Q(suggested_nurse=nurse)).distinct()
        return Appointment.objects.none()

    def _get_service_type_preferences(self, service_type):
        preferences = {
            ServiceType.WELLNESS_VISIT: [ProfessionalType.CAREGIVER_NURSE, ProfessionalType.PHYSIOTHERAPIST],
            ServiceType.CARE_VISIT: [ProfessionalType.CAREGIVER_NURSE, ProfessionalType.PALLIATIVE_CARE_NURSE],
            ServiceType.CHRONIC_CONDITION_VISIT: [ProfessionalType.PALLIATIVE_CARE_NURSE, ProfessionalType.CAREGIVER_NURSE],
            ServiceType.DAILY_CARE: [ProfessionalType.CAREGIVER_NURSE],
            ServiceType.LIVE_IN_CARE: [ProfessionalType.CAREGIVER_NURSE, ProfessionalType.PALLIATIVE_CARE_NURSE],
            ServiceType.EMERGENCY_ACCOMPANIMENT: [ProfessionalType.CAREGIVER_NURSE, ProfessionalType.PALLIATIVE_CARE_NURSE],
        }
        return preferences.get(service_type, [ProfessionalType.CAREGIVER_NURSE])

    def _is_available_for_time(self, nurse, appointment):
        day_of_week = appointment.appointment_date.weekday()
        slots = nurse.availability_slots.filter(is_available=True, day_of_week=day_of_week)
        for slot in slots:
            if slot.start_time <= appointment.start_time and slot.end_time >= appointment.end_time:
                return True
        return False

    def _has_conflicting_assignment(self, nurse, appointment):
        overlapping_statuses = [
            AppointmentStatus.APPROVED,
            AppointmentStatus.CONFIRMED,
            AppointmentStatus.PENDING,
            AppointmentStatus.NURSE_SUGGESTED,
            AppointmentStatus.UNDER_REVIEW,
        ]
        return Appointment.objects.filter(
            nurse=nurse,
            appointment_date=appointment.appointment_date,
            status__in=overlapping_statuses,
        ).filter(
            Q(start_time__lt=appointment.end_time, end_time__gt=appointment.start_time)
        ).exists()

    def _select_best_nurse(self, appointment):
        preferred_types = self._get_service_type_preferences(appointment.service_type)
        visit_city = (appointment.visit_city or '').strip().lower()
        visit_city_tokens = {visit_city} | {token for token in visit_city.split() if token}

        primary_candidates = []
        queryset = HealthcareNurse.objects.filter(
            status=NurseStatus.APPROVED,
            is_active=True,
            is_verified=True,
            is_accepting_requests=True,
        ).select_related('user')

        for nurse in queryset:
            if nurse.professional_type != preferred_types[0]:
                continue
            if not self._is_available_for_time(nurse, appointment):
                continue
            if self._has_conflicting_assignment(nurse, appointment):
                continue

            matching_service_area = False
            for area in nurse.service_areas or []:
                area_value = str(area).strip().lower()
                if not area_value:
                    continue
                if area_value in visit_city_tokens or visit_city in area_value or area_value in visit_city:
                    matching_service_area = True
                    break

            score = 100
            if matching_service_area:
                score += 30
            score += int(nurse.rating * 10)
            score -= nurse.total_appointments * 2
            primary_candidates.append((score, nurse))

        if primary_candidates:
            primary_candidates.sort(key=lambda item: (-item[0], item[1].rating, item[1].total_appointments, item[1].created_at))
            return primary_candidates[0][1]

        return None

    def create(self, request, *args, **kwargs):
        logger.info(
            'Appointment create attempt user_id=%s role=%s payload_keys=%s',
            getattr(request.user, 'id', None),
            getattr(request.user, 'role', None),
            sorted(request.data.keys()),
        )
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(
                'Appointment create validation failed user_id=%s errors=%s',
                getattr(request.user, 'id', None),
                serializer.errors,
            )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        appointment = self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        created_id = appointment.id if appointment else None
        logger.info(
            'Appointment created id=%s user_id=%s family_member=%s status=%s',
            created_id,
            getattr(request.user, 'id', None),
            serializer.validated_data.get('family_member').id if serializer.validated_data.get('family_member') else None,
            appointment.status if appointment else None,
        )
        payload = AppointmentSerializer(appointment).data if appointment else serializer.data
        return Response(payload, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        if not is_end_user(self.request.user):
            logger.warning(
                'Appointment create forbidden user_id=%s role=%s',
                getattr(self.request.user, 'id', None),
                getattr(self.request.user, 'role', None),
            )
            raise PermissionDenied('Only end users can submit care requests.')
        end_user_profile = get_end_user_profile(self.request.user)
        appointment = serializer.save(
            end_user_profile=end_user_profile,
            status=AppointmentStatus.SUBMITTED,
            reviewed_by=None,
            rejection_reason=None,
            decision_at=None,
            nurse=None
        )

        auto_assigned_nurse = self._select_best_nurse(appointment)
        if auto_assigned_nurse:
            appointment.nurse = auto_assigned_nurse
            appointment.suggested_nurse = auto_assigned_nurse
            appointment.status = AppointmentStatus.APPROVED
            appointment.rejection_reason = None
            appointment.save(update_fields=['nurse', 'suggested_nurse', 'status', 'rejection_reason', 'updated_at'])
            create_notification(
                recipient=appointment.end_user_profile.user,
                appointment=appointment,
                event_type=NotificationEventType.REQUEST_APPROVED,
                title='Care Request Approved',
                message='Your care request has been automatically matched with a suitable nurse.',
            )
            logger.info(
                'Appointment auto-assigned id=%s nurse=%s service_type=%s city=%s',
                appointment.id,
                auto_assigned_nurse.id,
                appointment.service_type,
                appointment.visit_city,
            )
        else:
            logger.info(
                'Appointment kept pending id=%s service_type=%s city=%s',
                appointment.id,
                appointment.service_type,
                appointment.visit_city,
            )

        admin_users = CustomUser.objects.filter(
            Q(role=UserRole.ADMIN) | Q(is_staff=True),
            is_active=True,
        ).distinct()
        for admin_user in admin_users:
            create_notification(
                recipient=admin_user,
                appointment=appointment,
                event_type=NotificationEventType.REQUEST_SUBMITTED,
                title='New Care Request Submitted',
                message='A new care request has been submitted and is awaiting admin review.',
            )

        return appointment

    def perform_update(self, serializer):
        appointment = self.get_object()
        if self._is_admin(self.request.user):
            serializer.save()
            return
        if self._is_org_admin(self.request.user):
            organization = self._org_admin_organization(self.request.user)
            if (
                (appointment.nurse and appointment.nurse.organization_id == organization.id)
                or (appointment.suggested_nurse and appointment.suggested_nurse.organization_id == organization.id)
            ):
                serializer.save()
                return
            raise PermissionDenied('You can only update appointments involving your organization nurses.')
        if not is_end_user(self.request.user):
            raise PermissionDenied('Only end users or admins can update care requests.')
        if appointment.end_user_profile.user_id != self.request.user.id:
            raise PermissionDenied('You can only update your own care requests.')
        if appointment.status in [AppointmentStatus.APPROVED, AppointmentStatus.REJECTED]:
            raise PermissionDenied('Approved or rejected requests cannot be edited.')
        if 'status' in serializer.validated_data:
            raise ValidationError('Only admins can change appointment status.')
        serializer.save()

    @action(detail=False, methods=['get'], url_path='pending-matching')
    def pending_matching(self, request):
        """Admin queue for requests awaiting nurse matching/review."""
        if not self._is_admin(request.user) and not self._is_org_admin(request.user):
            raise PermissionDenied('Only admins can view pending matching queue.')
        queryset = self.get_queryset().filter(
            status__in=[
                AppointmentStatus.SUBMITTED,
                AppointmentStatus.UNDER_REVIEW,
                AppointmentStatus.NURSE_SUGGESTED,
            ]
        )
        serializer = AppointmentSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='suggest-nurse')
    def suggest_nurse(self, request, pk=None):
        """Admin suggests nurse for a care request."""
        if not self._is_admin(request.user) and not self._is_org_admin(request.user):
            raise PermissionDenied('Only admins can suggest nurses.')
        appointment = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        selected_nurse = serializer.validated_data['suggested_nurse']
        if self._is_org_admin(request.user):
            organization = self._org_admin_organization(request.user)
            if selected_nurse.organization_id != organization.id:
                raise PermissionDenied('You can only suggest nurses from your organization.')

        appointment.suggested_nurse = selected_nurse
        # Keep nurse assignment in sync so nurse portals querying by `nurse` can see the schedule immediately.
        appointment.nurse = selected_nurse
        appointment.status = AppointmentStatus.NURSE_SUGGESTED
        appointment.reviewed_by = request.user
        appointment.rejection_reason = None
        appointment.save()

        create_notification(
            recipient=appointment.end_user_profile.user,
            appointment=appointment,
            event_type=NotificationEventType.NURSE_SUGGESTED,
            title='Nurse Suggested',
            message='An admin has suggested a nurse for your care request.'
        )

        return Response(AppointmentSerializer(appointment).data)

    @action(detail=True, methods=['post'])
    def decision(self, request, pk=None):
        """Admin final decision: approve or reject care request."""
        if not self._is_admin(request.user) and not self._is_org_admin(request.user):
            raise PermissionDenied('Only admins can make final decisions.')
        appointment = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        decision = serializer.validated_data['decision']
        appointment.reviewed_by = request.user
        appointment.decision_at = timezone.now()

        if decision == AppointmentStatus.APPROVED:
            selected_nurse = serializer.validated_data.get('nurse') or appointment.suggested_nurse or appointment.nurse
            if not selected_nurse:
                raise ValidationError({'suggested_nurse': 'Suggest a nurse before approval.'})
            if self._is_org_admin(request.user):
                organization = self._org_admin_organization(request.user)
                if selected_nurse.organization_id != organization.id:
                    raise PermissionDenied('You can only approve appointments with nurses from your organization.')
            appointment.nurse = selected_nurse
            appointment.suggested_nurse = selected_nurse
            appointment.status = AppointmentStatus.APPROVED
            appointment.rejection_reason = None
            event_type = NotificationEventType.REQUEST_APPROVED
            title = 'Care Request Approved'
            message = 'Your care request has been approved and a nurse has been assigned.'
        else:
            appointment.status = AppointmentStatus.REJECTED
            appointment.rejection_reason = serializer.validated_data['rejection_reason']
            appointment.nurse = None
            event_type = NotificationEventType.REQUEST_REJECTED
            title = 'Care Request Rejected'
            message = f"Your care request was rejected. Reason: {appointment.rejection_reason}"

        appointment.save()
        create_notification(
            recipient=appointment.end_user_profile.user,
            appointment=appointment,
            event_type=event_type,
            title=title,
            message=message,
        )
        return Response(AppointmentSerializer(appointment).data)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """Confirm appointment"""
        appointment = self.get_object()
        if appointment.status not in [AppointmentStatus.APPROVED, AppointmentStatus.PENDING]:
            return Response(
                {'detail': 'Only approved requests can be confirmed'},
                status=status.HTTP_400_BAD_REQUEST
            )
        appointment.status = AppointmentStatus.CONFIRMED
        appointment.save()
        return Response(AppointmentSerializer(appointment).data)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Complete appointment"""
        appointment = self.get_object()
        if appointment.status != AppointmentStatus.CONFIRMED:
            return Response(
                {'detail': 'Only confirmed appointments can be completed'},
                status=status.HTTP_400_BAD_REQUEST
            )
        appointment.status = AppointmentStatus.COMPLETED
        appointment.nurse.completed_appointments += 1
        appointment.nurse.total_appointments += 1
        appointment.nurse.save()
        appointment.save()
        return Response(AppointmentSerializer(appointment).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel appointment"""
        appointment = Appointment.objects.filter(pk=pk).first()
        if not appointment:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        if appointment.end_user_profile.user_id != request.user.id:
            return Response(
                {'detail': 'You can only cancel your own appointments.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if appointment.status == AppointmentStatus.CANCELLED:
            return Response(AppointmentSerializer(appointment).data, status=status.HTTP_200_OK)

        if appointment.status not in [
            AppointmentStatus.SUBMITTED,
            AppointmentStatus.UNDER_REVIEW,
            AppointmentStatus.NURSE_SUGGESTED,
        ]:
            return Response(
                {'detail': 'Invalid status transition to CANCELLED for this appointment.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        appointment.status = AppointmentStatus.CANCELLED
        appointment.save(update_fields=['status', 'updated_at'])
        return Response(AppointmentSerializer(appointment).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def reschedule(self, request, pk=None):
        """Reschedule appointment"""
        appointment = self.get_object()
        if appointment.status in [AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED]:
            return Response({'detail': 'Cannot reschedule completed or cancelled appointments.'}, status=status.HTTP_400_BAD_REQUEST)
            
        new_date = request.data.get('appointment_date')
        start_time = request.data.get('start_time')
        end_time = request.data.get('end_time')
        
        if not all([new_date, start_time, end_time]):
            return Response({'detail': 'appointment_date, start_time, and end_time are required.'}, status=status.HTTP_400_BAD_REQUEST)
            
        appointment.appointment_date = new_date
        appointment.start_time = start_time
        appointment.end_time = end_time
        appointment.status = AppointmentStatus.RESCHEDULED
        appointment.save()
        
        return Response(AppointmentSerializer(appointment).data)

    @action(detail=True, methods=['post'], url_path='no-show')
    def no_show(self, request, pk=None):
        """Mark appointment as no-show"""
        appointment = self.get_object()
        if appointment.status != AppointmentStatus.CONFIRMED:
            return Response({'detail': 'Only confirmed appointments can be marked as no-show'}, status=status.HTTP_400_BAD_REQUEST)
        appointment.status = AppointmentStatus.NO_SHOW
        appointment.save()
        return Response(AppointmentSerializer(appointment).data)

# ============ HEALTH RECORDS ============

class HealthRecordViewSet(viewsets.ModelViewSet):
    """Health records management"""
    serializer_class = HealthRecordSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['type', 'family_member', 'is_private']
    ordering = ['-created_at']

    def get_queryset(self):
        end_user_profile = get_end_user_profile(self.request.user)
        return HealthRecord.objects.filter(end_user_profile=end_user_profile)

    def get_serializer_class(self):
        if self.action == 'create':
            return HealthRecordCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return HealthRecordUpdateSerializer
        return HealthRecordSerializer

    def perform_create(self, serializer):
        end_user_profile = get_end_user_profile(self.request.user)
        serializer.save(end_user_profile=end_user_profile)

# ============ PAYMENTS ============

class PaymentViewSet(viewsets.ModelViewSet):
    """Payment management"""
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'method']
    ordering = ['-created_at']

    def get_queryset(self):
        end_user_profile = get_end_user_profile(self.request.user)
        return Payment.objects.filter(end_user_profile=end_user_profile)

    def get_serializer_class(self):
        if self.action == 'create':
            return PaymentInitiateSerializer
        return PaymentSerializer

    def perform_create(self, serializer):
        end_user_profile = get_end_user_profile(self.request.user)
        payment = serializer.save(end_user_profile=end_user_profile)

        appointment_ids = serializer.validated_data.get('appointment_ids') or []
        if appointment_ids:
            appointments = Appointment.objects.filter(
                id__in=[a.id for a in appointment_ids],
                end_user_profile=end_user_profile,
            )
            if appointments.count() != len(appointment_ids):
                raise ValidationError('One or more appointments are not accessible.')
            appointments.update(payment=payment)

        if payment.method == 'MPESA' and not payment.mpesa_transaction_id:
            payment.mpesa_transaction_id = f"MPESA-{uuid.uuid4()}"
            payment.save(update_fields=['mpesa_transaction_id'])
        elif payment.method == 'STRIPE':
            # TODO: Generate Stripe PaymentIntent here
            # For now, just placeholder logic
            pass
        elif payment.method == 'PESAPAL':
            # TODO: Submit order to PesaPal API here
            # For now, just placeholder logic
            pass

    @action(
        detail=False,
        methods=['post'],
        permission_classes=[permissions.AllowAny],
        authentication_classes=[],
    )
    def mpesa_callback(self, request):
        """Handle M-Pesa payment callback"""
        mpesa_id = request.data.get('mpesa_transaction_id')
        payment = Payment.objects.filter(mpesa_transaction_id=mpesa_id).first()
        
        if not payment:
            return Response(
                {'status': 'failed', 'message': 'Payment not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        payment.status = PaymentStatus.COMPLETED
        payment.mpesa_receipt_number = request.data.get('mpesa_receipt_number')
        payment.transaction_date = timezone.now()
        payment.completed_at = timezone.now()
        payment.save()
        
        # Trigger async task to send receipt email.
        enqueue_task_or_run(send_payment_receipt_task, payment.id)
        
        return Response({'status': 'success', 'message': 'Payment processed'})

    @action(
        detail=False,
        methods=['post'],
        permission_classes=[permissions.AllowAny],
        authentication_classes=[],
    )
    def stripe_webhook(self, request):
        """Handle Stripe payment webhook"""
        # Placeholder for Stripe webhook logic
        # You'll need to verify the Stripe signature and process the event
        return Response({'status': 'success', 'message': 'Stripe webhook received'})

    @action(
        detail=False,
        methods=['get', 'post'],
        permission_classes=[permissions.AllowAny],
        authentication_classes=[],
    )
    def pesapal_ipn(self, request):
        """Handle PesaPal IPN callback"""
        # Placeholder for PesaPal IPN logic
        # Typically involves querying PesaPal for transaction status using tracking ID
        return Response({'status': 'success', 'message': 'PesaPal IPN received'})

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get payment statistics"""
        end_user_profile = get_end_user_profile(self.request.user)
        payments = Payment.objects.filter(
            end_user_profile=end_user_profile,
            status=PaymentStatus.COMPLETED
        )
        total_spent = sum(p.amount for p in payments)
        count = payments.count()
        
        return Response({
            'total_spent': float(total_spent),
            'payment_count': count,
            'average_payment': float(total_spent / count) if count > 0 else 0,
            'currency': 'KES'
        })

    @action(detail=True, methods=['post'])
    def refund(self, request, pk=None):
        """Refund a payment"""
        payment = self.get_object()
        if payment.status != PaymentStatus.COMPLETED:
            return Response(
                {'detail': 'Only completed payments can be refunded'},
                status=status.HTTP_400_BAD_REQUEST
            )
        payment.status = PaymentStatus.REFUNDED
        payment.save()
        return Response(PaymentSerializer(payment).data)


class NotificationViewSet(ApiDebugMixin, viewsets.ReadOnlyModelViewSet):
    """User notification feed"""
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['is_read', 'event_type']
    ordering_fields = ['created_at']
    ordering = ['-created_at', '-id']

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        if notification.is_read:
            return Response(NotificationSerializer(notification).data)
        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return Response(NotificationSerializer(notification).data)

    @action(detail=False, methods=['post'], url_path='mark-all-read')
    def mark_all_read(self, request):
        self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({'detail': 'All notifications marked as read.'})

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        count = self.get_queryset().filter(is_read=False).count()
        return Response({'unread_count': count})

# ============ NURSE EARNINGS ============

class NurseEarningViewSet(viewsets.ModelViewSet):
    """Nurse earnings management"""
    serializer_class = NurseEarningSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['payment_status', 'nurse']
    ordering = ['-payment_period_end']

    def get_queryset(self):
        if is_admin_user(self.request.user):
            return NurseEarning.objects.all()
        if self.request.user.role == UserRole.NURSE:
            nurse = get_nurse_profile(self.request.user)
            return NurseEarning.objects.filter(nurse=nurse)
        return NurseEarning.objects.none()

    def perform_create(self, serializer):
        if not is_admin_user(self.request.user):
            raise PermissionDenied('Only admins can create nurse earnings.')
        serializer.save()

    def perform_update(self, serializer):
        if not is_admin_user(self.request.user):
            raise PermissionDenied('Only admins can update nurse earnings.')
        serializer.save()
        
    @action(detail=True, methods=['post'], url_path='mark-paid')
    def mark_paid(self, request, pk=None):
        if not is_admin_user(request.user):
            raise PermissionDenied('Only admins can mark earnings as paid.')
        earning = self.get_object()
        earning.payment_status = PaymentStatus.COMPLETED
        earning.paid_at = timezone.now()
        earning.save(update_fields=['payment_status', 'paid_at'])
        return Response(self.get_serializer(earning).data)

# ============ REVIEWS ============

class ReviewViewSet(viewsets.ModelViewSet):
    """Review and rating management"""
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['nurse', 'rating']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'create':
            return ReviewCreateSerializer
        elif self.action == 'retrieve':
            return ReviewDetailSerializer
        return ReviewSerializer

    def perform_create(self, serializer):
        end_user_profile = get_end_user_profile(self.request.user)
        appointment = serializer.validated_data['appointment']
        
        if appointment.status != AppointmentStatus.COMPLETED:
            raise ValidationError('Can only review completed appointments')
        
        serializer.save(
            end_user_profile=end_user_profile,
            nurse=appointment.nurse
        )
        
        nurse = appointment.nurse
        reviews = Review.objects.filter(nurse=nurse)
        if reviews.exists():
            avg_rating = reviews.aggregate(Avg('rating'))['rating__avg']
            nurse.rating = Decimal(str(avg_rating))
            nurse.total_reviews = reviews.count()
            nurse.save()

    @action(detail=False, methods=['get'], url_path='nurse/(?P<nurse_id>[^/.]+)/stats')
    def nurse_stats(self, request, nurse_id=None):
        """Get review statistics for a nurse"""
        nurse = HealthcareNurse.objects.get(id=nurse_id)
        reviews = Review.objects.filter(nurse=nurse)
        
        if not reviews.exists():
            return Response({
                'average_rating': 0,
                'total_reviews': 0,
                'rating_distribution': {}
            })
        
        rating_dist = {}
        for i in range(1, 6):
            count = reviews.filter(rating=i).count()
            rating_dist[str(i)] = count
        
        avg_rating = reviews.aggregate(Avg('rating'))['rating__avg']
        
        return Response({
            'average_rating': round(float(avg_rating), 2),
            'total_reviews': reviews.count(),
            'rating_distribution': rating_dist
        })
