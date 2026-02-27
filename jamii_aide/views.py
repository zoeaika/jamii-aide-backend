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
from allauth.socialaccount.models import SocialAccount
import uuid
import requests

from jamii_aide.models import (
    CustomUser, EndUserProfile, HealthcareNurse, FamilyMember,
    AvailabilitySlot, Appointment, HealthRecord, Prescription,
    Payment, Review, NurseEarning, AppointmentStatus, PaymentStatus, UserRole,
    Notification, NotificationEventType
)
from jamii_aide.serializers import (
    UserSerializer, RegisterSerializer, LoginSerializer,
    EndUserProfileSerializer, EndUserProfileUpdateSerializer,
    EndUserSerializer, EndUserUpdateSerializer,
    FamilyMemberSerializer, FamilyMemberDetailSerializer,
    HealthcareNurseSerializer, HealthcareNurseDetailSerializer,
    HealthcareNurseUpdateSerializer, HealthcareNurseCreateSerializer,
    AvailabilitySlotSerializer,
    AppointmentSerializer, AppointmentDetailSerializer,
    AppointmentCreateSerializer, AppointmentUpdateSerializer,
    AppointmentSuggestNurseSerializer, AppointmentDecisionSerializer,
    HealthRecordSerializer, HealthRecordCreateSerializer,
    HealthRecordUpdateSerializer,
    PrescriptionSerializer, PrescriptionCreateSerializer,
    PrescriptionUpdateSerializer,
    PaymentSerializer, PaymentInitiateSerializer,
    ReviewSerializer, ReviewCreateSerializer, ReviewDetailSerializer,
    NurseEarningSerializer, NotificationSerializer
)
from jamii_aide.google_serializers import GoogleAuthSerializer, GoogleLoginResponseSerializer


def create_notification(*, recipient, appointment, event_type, title, message):
    Notification.objects.create(
        recipient=recipient,
        appointment=appointment,
        event_type=event_type,
        title=title,
        message=message,
    )


def is_end_user(user):
    return user.role == UserRole.END_USER


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

# ============ AUTHENTICATION VIEWS ============

class RegisterView(APIView):
    """Register new user"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            
            # Create role-specific profile
            if user.role == UserRole.END_USER:
                EndUserProfile.objects.create(
                    user=user,
                    current_country=request.data.get('current_country', ''),
                    current_city=request.data.get('current_city', '')
                )
            elif user.role == 'HEALTHCARE_NURSE':
                HealthcareNurse.objects.create(
                    user=user,
                    license_number='',
                    license_expiry=timezone.now().date(),
                    years_experience=0,
                    status='PENDING'
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

# ============ FAMILY MEMBERS ============

class FamilyMemberViewSet(viewsets.ModelViewSet):
    """Family member management"""
    serializer_class = FamilyMemberSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['is_active']
    search_fields = ['first_name', 'last_name']

    def get_queryset(self):
        end_user_profile = get_end_user_profile(self.request.user)
        return FamilyMember.objects.filter(end_user_profile=end_user_profile)

    def perform_create(self, serializer):
        end_user_profile = get_end_user_profile(self.request.user)
        serializer.save(end_user_profile=end_user_profile)

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return FamilyMemberDetailSerializer
        return FamilyMemberSerializer

# ============ HEALTHCARE NURSES ============

class HealthcareNurseViewSet(viewsets.ModelViewSet):
    """Healthcare nurse profiles"""
    queryset = HealthcareNurse.objects.all()
    serializer_class = HealthcareNurseSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'professional_type', 'is_verified', 'is_active']
    search_fields = ['user__first_name', 'user__last_name', 'specializations']
    ordering_fields = ['rating', 'total_appointments', 'created_at']
    ordering = ['-rating']

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
        nurse = HealthcareNurse.objects.get(user=request.user)
        serializer = self.get_serializer(nurse)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def complete_profile(self, request):
        """Complete nurse profile after registration"""
        nurse = HealthcareNurse.objects.get(user=request.user)
        serializer = HealthcareNurseCreateSerializer(nurse, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            nurse.status = 'PENDING'
            nurse.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def availability(self, request, pk=None):
        """Get nurse availability"""
        nurse = self.get_object()
        slots = nurse.availability_slots.filter(is_available=True)
        serializer = AvailabilitySlotSerializer(slots, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get nurse performance statistics"""
        nurse = self.get_object()
        reviews = Review.objects.filter(nurse=nurse)
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
        nurse = HealthcareNurse.objects.get(user=self.request.user)
        return AvailabilitySlot.objects.filter(nurse=nurse)

    def perform_create(self, serializer):
        nurse = HealthcareNurse.objects.get(user=self.request.user)
        serializer.save(nurse=nurse)

# ============ APPOINTMENTS ============

class AppointmentViewSet(viewsets.ModelViewSet):
    """Appointment management"""
    queryset = Appointment.objects.all()
    serializer_class = AppointmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'nurse', 'family_member']
    ordering_fields = ['appointment_date', 'created_at']
    ordering = ['-appointment_date']

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
        return user.role == UserRole.ADMIN or user.is_staff

    def get_queryset(self):
        user = self.request.user
        if self._is_admin(user):
            return Appointment.objects.all()
        if is_end_user(user):
            return Appointment.objects.filter(end_user_profile__user=user)
        if user.role == UserRole.HEALTHCARE_NURSE:
            nurse = HealthcareNurse.objects.filter(user=user).first()
            if not nurse:
                return Appointment.objects.none()
            return Appointment.objects.filter(Q(nurse=nurse) | Q(suggested_nurse=nurse))
        return Appointment.objects.none()

    def perform_create(self, serializer):
        if not is_end_user(self.request.user):
            raise PermissionDenied('Only end users can submit care requests.')
        end_user_profile = get_end_user_profile(self.request.user)
        serializer.save(
            end_user_profile=end_user_profile,
            status=AppointmentStatus.SUBMITTED,
            reviewed_by=None,
            rejection_reason=None,
            decision_at=None,
            nurse=None
        )

    def perform_update(self, serializer):
        appointment = self.get_object()
        if self._is_admin(self.request.user):
            serializer.save()
            return
        if not is_end_user(self.request.user):
            raise PermissionDenied('Only end users or admins can update care requests.')
        if appointment.end_user_profile.user_id != self.request.user.id:
            raise PermissionDenied('You can only update your own care requests.')
        if appointment.status in [AppointmentStatus.APPROVED, AppointmentStatus.REJECTED]:
            raise PermissionDenied('Approved or rejected requests cannot be edited.')
        serializer.save()

    @action(detail=False, methods=['get'], url_path='pending-matching')
    def pending_matching(self, request):
        """Admin queue for requests awaiting nurse matching/review."""
        if not self._is_admin(request.user):
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
        if not self._is_admin(request.user):
            raise PermissionDenied('Only admins can suggest nurses.')
        appointment = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        appointment.suggested_nurse = serializer.validated_data['suggested_nurse']
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
        if not self._is_admin(request.user):
            raise PermissionDenied('Only admins can make final decisions.')
        appointment = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        decision = serializer.validated_data['decision']
        appointment.reviewed_by = request.user
        appointment.decision_at = timezone.now()

        if decision == AppointmentStatus.APPROVED:
            selected_nurse = appointment.suggested_nurse or appointment.nurse
            if not selected_nurse:
                raise ValidationError({'suggested_nurse': 'Suggest a nurse before approval.'})
            appointment.nurse = selected_nurse
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
        appointment = self.get_object()
        if appointment.status not in [
            AppointmentStatus.SUBMITTED,
            AppointmentStatus.UNDER_REVIEW,
            AppointmentStatus.NURSE_SUGGESTED,
            AppointmentStatus.APPROVED,
            AppointmentStatus.PENDING,
            AppointmentStatus.CONFIRMED,
        ]:
            return Response(
                {'detail': 'Cannot cancel this appointment'},
                status=status.HTTP_400_BAD_REQUEST
            )
        appointment.status = AppointmentStatus.CANCELLED
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

# ============ PRESCRIPTIONS ============

class PrescriptionViewSet(viewsets.ModelViewSet):
    """Prescription management"""
    serializer_class = PrescriptionSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['is_active']
    ordering = ['-start_date']

    def get_queryset(self):
        end_user_profile = get_end_user_profile(self.request.user)
        return Prescription.objects.filter(end_user_profile=end_user_profile)

    def get_serializer_class(self):
        if self.action == 'create':
            return PrescriptionCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return PrescriptionUpdateSerializer
        return PrescriptionSerializer

    def perform_create(self, serializer):
        end_user_profile = get_end_user_profile(self.request.user)
        serializer.save(end_user_profile=end_user_profile)

    @action(detail=True, methods=['post'])
    def refill(self, request, pk=None):
        """Request prescription refill"""
        prescription = self.get_object()
        if prescription.refills_remaining <= 0:
            return Response(
                {'detail': 'No refills remaining'},
                status=status.HTTP_400_BAD_REQUEST
            )
        prescription.refills_remaining -= 1
        prescription.save()
        return Response(PrescriptionSerializer(prescription).data)

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
        serializer.save(end_user_profile=end_user_profile)

    @action(detail=False, methods=['post'])
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
        
        return Response({'status': 'success', 'message': 'Payment processed'})

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


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """User notification feed"""
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['is_read', 'event_type']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

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
