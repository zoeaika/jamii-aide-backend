from rest_framework import serializers
from django.contrib.auth.hashers import make_password
from django.contrib.auth import authenticate
from uuid import uuid4
from jamii_aide.models import (
    CustomUser, EndUserProfile, HealthcareNurse, FamilyMember,
    AvailabilitySlot, Appointment, HealthRecord, Prescription,
    Payment, Review, NurseEarning, AppointmentStatus, Notification
)

# ============ AUTH SERIALIZERS ============

class UserSerializer(serializers.ModelSerializer):
    """Serializer for user registration and profile"""
    password = serializers.CharField(write_only=True, min_length=8)
    
    class Meta:
        model = CustomUser
        fields = [
            'id', 'email', 'phone', 'first_name', 'last_name',
            'role', 'profile_image', 'is_verified', 'is_active',
            'password', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'is_verified', 'is_active']
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = CustomUser.objects.create(**validated_data)
        user.set_password(password)
        user.save()
        return user

class RegisterSerializer(serializers.Serializer):
    """Register new user"""
    email = serializers.EmailField()
    phone = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(min_length=8, write_only=True)
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    role = serializers.ChoiceField(
        choices=['END_USER', 'HEALTHCARE_NURSE', 'ADMIN']
    )

    def create(self, validated_data):
        password = validated_data.pop('password')
        phone = validated_data.get('phone')
        if phone == '':
            validated_data['phone'] = None
        base_username = validated_data.get('email', '').split('@')[0] or f"user_{uuid4().hex[:8]}"
        username = base_username
        while CustomUser.objects.filter(username=username).exists():
            username = f"{base_username}_{uuid4().hex[:6]}"
        validated_data['username'] = username
        user = CustomUser.objects.create(**validated_data)
        user.set_password(password)
        user.save()
        return user

class LoginSerializer(serializers.Serializer):
    """Login serializer"""
    email = serializers.EmailField()
    password = serializers.CharField()

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        
        if email and password:
            user = CustomUser.objects.filter(email=email).first()
            if user and user.check_password(password):
                attrs['user'] = user
                return attrs
        
        raise serializers.ValidationError('Invalid email or password')

# ============ END USER PROFILE SERIALIZERS ============

class EndUserProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = EndUserProfile
        fields = [
            'id', 'user', 'current_country', 'current_city',
            'timezone', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

class EndUserProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EndUserProfile
        fields = ['current_country', 'current_city', 'timezone']


class EndUserSerializer(EndUserProfileSerializer):
    pass


class EndUserUpdateSerializer(EndUserProfileUpdateSerializer):
    pass

# ============ FAMILY MEMBER SERIALIZERS ============

class FamilyMemberSerializer(serializers.ModelSerializer):
    # Frontend/backward-compat aliases
    phone_number = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    location = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = FamilyMember
        fields = [
            'id', 'end_user_profile', 'first_name', 'last_name',
            'date_of_birth', 'gender', 'id_number', 'profile_image',
            'phone', 'phone_number', 'city', 'location', 'address',
            'email', 'blood_type', 'known_allergies',
            'chronic_conditions', 'current_medications',
            'emergency_contact', 'emergency_phone', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'end_user_profile', 'created_at', 'updated_at']

    def validate(self, attrs):
        phone_number = attrs.pop('phone_number', None)
        location = attrs.pop('location', None)

        if phone_number is not None and attrs.get('phone') in (None, ''):
            attrs['phone'] = phone_number
        if location is not None and attrs.get('city') in (None, ''):
            attrs['city'] = location
        return attrs

class FamilyMemberDetailSerializer(FamilyMemberSerializer):
    """Detailed family member with related data"""
    pass

# ============ HEALTHCARE NURSE SERIALIZERS ============

class AvailabilitySlotSerializer(serializers.ModelSerializer):
    day_of_week_display = serializers.CharField(source='get_day_of_week_display', read_only=True)
    
    class Meta:
        model = AvailabilitySlot
        fields = [
            'id', 'nurse', 'day_of_week', 'day_of_week_display',
            'start_time', 'end_time', 'is_available',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

class HealthcareNurseSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    professional_type_display = serializers.CharField(source='get_professional_type_display', read_only=True)
    
    class Meta:
        model = HealthcareNurse
        fields = [
            'id', 'user', 'license_number', 'license_expiry',
            'professional_type', 'professional_type_display',
            'specializations', 'languages', 'years_experience',
            'bio', 'certifications', 'service_areas',
            'total_appointments', 'completed_appointments',
            'rating', 'total_reviews', 'is_verified', 'is_active',
            'status', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'total_appointments', 'completed_appointments',
            'rating', 'total_reviews', 'created_at', 'updated_at'
        ]

class HealthcareNurseDetailSerializer(HealthcareNurseSerializer):
    """Nurse with availability slots"""
    availability_slots = AvailabilitySlotSerializer(many=True, read_only=True)
    
    class Meta(HealthcareNurseSerializer.Meta):
        fields = HealthcareNurseSerializer.Meta.fields + ['availability_slots']

class HealthcareNurseUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = HealthcareNurse
        fields = [
            'professional_type', 'bio', 'specializations', 'languages', 'service_areas'
        ]

class HealthcareNurseCreateSerializer(serializers.ModelSerializer):
    """For completing nurse profile after registration"""
    class Meta:
        model = HealthcareNurse
        fields = [
            'license_number', 'license_expiry', 'professional_type', 'specializations',
            'languages', 'years_experience', 'bio', 'certifications',
            'service_areas'
        ]

# ============ APPOINTMENT SERIALIZERS ============

class AppointmentSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = Appointment
        fields = [
            'id', 'family_member', 'nurse', 'suggested_nurse', 'end_user_profile',
            'appointment_date', 'start_time', 'end_time',
            'reason', 'notes', 'additional_notes', 'service_type', 'shift_type',
            'evaluation_type', 'admission_clause_accepted',
            'admission_support_in_subscription', 'admission_questionnaire',
            'visit_address', 'visit_city', 'status', 'status_display',
            'reviewed_by', 'rejection_reason', 'decision_at', 'amount',
            'payment', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

class AppointmentDetailSerializer(AppointmentSerializer):
    """Detailed appointment with related data"""
    family_member = FamilyMemberSerializer(read_only=True)
    nurse = HealthcareNurseSerializer(read_only=True)

class AppointmentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = [
            'family_member', 'appointment_date',
            'start_time', 'end_time', 'reason', 'service_type',
            'shift_type', 'evaluation_type', 'visit_address',
            'visit_city', 'notes', 'additional_notes',
            'admission_clause_accepted', 'admission_support_in_subscription',
            'admission_questionnaire'
        ]

    def validate(self, attrs):
        questionnaire = attrs.get('admission_questionnaire') or {}
        needs_admission_details = (
            attrs.get('admission_clause_accepted')
            or attrs.get('admission_support_in_subscription')
        )
        if needs_admission_details and not questionnaire:
            raise serializers.ValidationError({
                'admission_questionnaire': 'Admission questionnaire is required when admission support is enabled.'
            })

        required_keys = [
            'insurance_details',
            'last_procedure',
            'medical_conditions',
            'prescriptions',
            'allergies',
            'emergency_contact',
            'consent_for_emergency_admission',
        ]
        if questionnaire:
            missing_keys = [key for key in required_keys if key not in questionnaire]
            if missing_keys:
                raise serializers.ValidationError({
                    'admission_questionnaire': f"Missing required fields: {', '.join(missing_keys)}"
                })
        return attrs

class AppointmentUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = [
            'appointment_date', 'start_time', 'end_time',
            'reason', 'notes', 'additional_notes', 'shift_type',
            'evaluation_type', 'visit_address', 'visit_city',
            'admission_clause_accepted', 'admission_support_in_subscription',
            'admission_questionnaire', 'status'
        ]


class AppointmentSuggestNurseSerializer(serializers.Serializer):
    suggested_nurse = serializers.PrimaryKeyRelatedField(
        queryset=HealthcareNurse.objects.filter(status='APPROVED', is_active=True)
    )


class AppointmentDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(
        choices=[AppointmentStatus.APPROVED, AppointmentStatus.REJECTED]
    )
    rejection_reason = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs['decision'] == AppointmentStatus.REJECTED and not attrs.get('rejection_reason'):
            raise serializers.ValidationError({
                'rejection_reason': 'Rejection reason is required when rejecting a request.'
            })
        return attrs

# ============ HEALTH RECORD SERIALIZERS ============

class HealthRecordSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source='get_type_display', read_only=True)
    
    class Meta:
        model = HealthRecord
        fields = [
            'id', 'family_member', 'nurse', 'end_user_profile',
            'appointment', 'type', 'type_display', 'title', 'content',
            'blood_pressure', 'heart_rate', 'temperature', 'weight',
            'file', 'is_private', 'is_confidential',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

class HealthRecordCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = HealthRecord
        fields = [
            'family_member', 'type', 'title', 'content',
            'appointment', 'blood_pressure', 'heart_rate',
            'temperature', 'weight'
        ]

class HealthRecordUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = HealthRecord
        fields = [
            'title', 'content', 'blood_pressure', 'heart_rate',
            'temperature', 'weight'
        ]

# ============ PRESCRIPTION SERIALIZERS ============

class PrescriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Prescription
        fields = [
            'id', 'end_user_profile', 'medication_name', 'dosage',
            'frequency', 'duration', 'start_date', 'end_date',
            'prescribed_by', 'notes', 'file', 'is_active',
            'refills_remaining', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

class PrescriptionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Prescription
        fields = [
            'medication_name', 'dosage', 'frequency', 'duration',
            'start_date', 'end_date', 'prescribed_by', 'notes'
        ]

class PrescriptionUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Prescription
        fields = [
            'medication_name', 'dosage', 'frequency', 'duration',
            'end_date', 'notes', 'is_active'
        ]

# ============ PAYMENT SERIALIZERS ============

class PaymentSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    method_display = serializers.CharField(source='get_method_display', read_only=True)
    
    class Meta:
        model = Payment
        fields = [
            'id', 'end_user_profile', 'amount', 'currency', 'method',
            'method_display', 'status', 'status_display',
            'mpesa_transaction_id', 'mpesa_receipt_number',
            'card_last_four', 'description', 'transaction_date',
            'completed_at', 'failure_reason', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'completed_at',
            'mpesa_transaction_id', 'mpesa_receipt_number'
        ]

class PaymentInitiateSerializer(serializers.ModelSerializer):
    appointment_ids = serializers.PrimaryKeyRelatedField(
        queryset=Appointment.objects.all(),
        many=True,
        required=False
    )
    
    class Meta:
        model = Payment
        fields = [
            'amount', 'method', 'description', 'appointment_ids'
        ]

# ============ REVIEW SERIALIZERS ============

class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = [
            'id', 'appointment', 'nurse', 'end_user_profile',
            'rating', 'title', 'comment', 'professionalism',
            'punctuality', 'communication', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

class ReviewCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = [
            'appointment', 'rating', 'title', 'comment',
            'professionalism', 'punctuality', 'communication'
        ]

class ReviewDetailSerializer(ReviewSerializer):
    """Detailed review with nurse info"""
    nurse = HealthcareNurseSerializer(read_only=True)
    end_user_profile = EndUserProfileSerializer(read_only=True)

# ============ NURSE EARNING SERIALIZERS ============

class NurseEarningSerializer(serializers.ModelSerializer):
    class Meta:
        model = NurseEarning
        fields = [
            'id', 'nurse', 'appointment_count', 'amount', 'currency',
            'payment_period_start', 'payment_period_end',
            'payment_status', 'paid_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class NotificationSerializer(serializers.ModelSerializer):
    event_type_display = serializers.CharField(source='get_event_type_display', read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id', 'recipient', 'appointment', 'event_type', 'event_type_display',
            'title', 'message', 'is_read', 'created_at'
        ]
        read_only_fields = ['id', 'recipient', 'created_at']
