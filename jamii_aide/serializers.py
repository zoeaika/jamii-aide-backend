from rest_framework import serializers
from django.utils import timezone
from uuid import uuid4
from jamii_aide.models import (
    CustomUser, EndUserProfile, HealthcareNurse, FamilyMember,
    AvailabilitySlot, Appointment, HealthRecord,
    Payment, Review, AppointmentStatus, Notification, UserRole,
    NurseEarning
)

# ============ AUTH SERIALIZERS ============

class UserSerializer(serializers.ModelSerializer):
    """Serializer for user registration and profile"""
    password = serializers.CharField(write_only=True, min_length=8)
    role = serializers.SerializerMethodField()
    
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

    def get_role(self, obj):
        return obj.get_effective_role()

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

    def validate_email(self, value):
        email = value.strip().lower()
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return email

    def validate_phone(self, value):
        phone = value.strip()
        if not phone:
            return ''
        if CustomUser.objects.filter(phone=phone).exists():
            raise serializers.ValidationError('An account with this phone number already exists.')
        return phone

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
        validated_data['role'] = UserRole.USER
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
            user = CustomUser.objects.filter(email__iexact=email.strip().lower()).first()
            if user and user.check_password(password):
                if not user.is_active:
                    raise serializers.ValidationError('This account is inactive.')
                attrs['user'] = user
                return attrs
        
        raise serializers.ValidationError('Invalid email or password')

# ============ END USER PROFILE SERIALIZERS ============

class EndUserProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.UUIDField(source='user.id', read_only=True)
    
    class Meta:
        model = EndUserProfile
        fields = [
            'id', 'user_id', 'user', 'current_country', 'current_city',
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
    name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    age = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    relationship = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    conditions = serializers.ListField(
        child=serializers.CharField(allow_blank=True),
        write_only=True,
        required=False,
        allow_empty=True,
    )
    firstName = serializers.CharField(write_only=True, required=False, allow_blank=True)
    lastName = serializers.CharField(write_only=True, required=False, allow_blank=True)
    dateOfBirth = serializers.DateField(write_only=True, required=False)
    idNumber = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    profileImage = serializers.ImageField(write_only=True, required=False, allow_null=True)
    phone_number = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    phoneNumber = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    location = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    bloodType = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    knownAllergies = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    chronicConditions = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    currentMedications = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    emergencyContactName = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    emergencyPhoneNumber = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    emergencyPhone = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    isActive = serializers.BooleanField(write_only=True, required=False)
    full_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = FamilyMember
        fields = [
            'id', 'end_user_profile', 'first_name', 'last_name',
            'full_name', 'name', 'age', 'relationship', 'conditions', 'firstName', 'lastName',
            'date_of_birth', 'gender', 'id_number', 'profile_image',
            'dateOfBirth', 'idNumber', 'profileImage',
            'phone', 'phone_number', 'phoneNumber', 'city', 'location', 'address',
            'email', 'blood_type', 'bloodType', 'known_allergies', 'knownAllergies',
            'chronic_conditions', 'chronicConditions', 'current_medications', 'currentMedications',
            'emergency_contact', 'emergencyContactName', 'emergency_phone', 'emergencyPhone', 'emergencyPhoneNumber',
            'is_active', 'isActive',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'end_user_profile', 'created_at', 'updated_at']

    def get_full_name(self, obj):
        return str(obj)

    def to_internal_value(self, data):
        if hasattr(data, 'copy'):
            data = data.copy()

        name = data.get('name')
        if name and not data.get('first_name') and not data.get('last_name'):
            name_parts = str(name).strip().split(None, 1)
            if name_parts:
                data['first_name'] = name_parts[0]
                data['last_name'] = name_parts[1] if len(name_parts) > 1 else 'Family Member'

        full_name = data.get('full_name')
        if full_name and not data.get('first_name') and not data.get('last_name'):
            name_parts = str(full_name).strip().split(None, 1)
            if name_parts:
                data['first_name'] = name_parts[0]
                if len(name_parts) > 1:
                    data['last_name'] = name_parts[1]

        if data.get('first_name') and data.get('last_name') == '':
            data['last_name'] = 'Family Member'

        alias_map = {
            'firstName': 'first_name',
            'lastName': 'last_name',
            'dateOfBirth': 'date_of_birth',
            'idNumber': 'id_number',
            'profileImage': 'profile_image',
            'phoneNumber': 'phone',
            'bloodType': 'blood_type',
            'knownAllergies': 'known_allergies',
            'chronicConditions': 'chronic_conditions',
            'currentMedications': 'current_medications',
            'emergencyContactName': 'emergency_contact',
            'emergencyPhoneNumber': 'emergency_phone',
            'emergencyPhone': 'emergency_phone',
            'isActive': 'is_active',
        }
        for alias, canonical in alias_map.items():
            value = data.get(alias)
            if value is not None and data.get(canonical) in (None, ''):
                data[canonical] = value

        if data.get('phone') in (None, '') and data.get('phone_number') not in (None, ''):
            data['phone'] = data.get('phone_number')
        if data.get('phone') in (None, '') and data.get('phoneNumber') not in (None, ''):
            data['phone'] = data.get('phoneNumber')
        if data.get('city') in (None, '') and data.get('location') not in (None, ''):
            data['city'] = data.get('location')
        if data.get('chronic_conditions') in (None, '') and data.get('medical_conditions') not in (None, ''):
            data['chronic_conditions'] = data.get('medical_conditions')
        if data.get('chronic_conditions') in (None, '') and data.get('conditions'):
            if isinstance(data.get('conditions'), list):
                data['chronic_conditions'] = ', '.join([str(item).strip() for item in data.get('conditions') if str(item).strip()])
            else:
                data['chronic_conditions'] = data.get('conditions')
        if not data.get('date_of_birth') and data.get('age') not in (None, ''):
            try:
                age_value = int(data.get('age'))
                today = timezone.now().date()
                birth_year = today.year - age_value
                data['date_of_birth'] = today.replace(year=birth_year)
            except (TypeError, ValueError):
                pass
            except ValueError:
                today = timezone.now().date()
                birth_year = today.year - int(data.get('age'))
                data['date_of_birth'] = today.replace(month=1, day=1, year=birth_year)
        if not data.get('gender'):
            data['gender'] = 'OTHER'
        if data.get('gender'):
            data['gender'] = str(data['gender']).upper()

        return super().to_internal_value(data)

    def validate(self, attrs):
        for alias in [
            'name', 'age', 'relationship', 'conditions',
            'firstName', 'lastName', 'dateOfBirth', 'idNumber', 'profileImage',
            'phoneNumber', 'bloodType', 'knownAllergies', 'chronicConditions',
            'currentMedications', 'emergencyContactName', 'emergencyPhoneNumber',
            'emergencyPhone', 'isActive',
        ]:
            attrs.pop(alias, None)

        phone_number = attrs.pop('phone_number', None)
        location = attrs.pop('location', None)

        if phone_number is not None and attrs.get('phone') in (None, ''):
            attrs['phone'] = phone_number
        if location is not None and attrs.get('city') in (None, ''):
            attrs['city'] = location
        if attrs.get('gender'):
            attrs['gender'] = str(attrs['gender']).upper()
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
        read_only_fields = ['id', 'nurse', 'created_at', 'updated_at']

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if not request or not getattr(request, 'user', None) or not request.user.is_authenticated:
            return

        family_member_field = self.fields.get('family_member')
        if family_member_field is None:
            return

        if request.user.role == UserRole.USER:
            end_user_profile, _ = EndUserProfile.objects.get_or_create(user=request.user)
            family_member_field.queryset = FamilyMember.objects.filter(
                end_user_profile=end_user_profile,
                is_active=True,
            )
        elif request.user.role == UserRole.ADMIN or request.user.is_staff:
            family_member_field.queryset = FamilyMember.objects.filter(is_active=True)
        else:
            family_member_field.queryset = FamilyMember.objects.none()

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
            'id',
            'family_member', 'type', 'title', 'content',
            'appointment', 'blood_pressure', 'heart_rate',
            'temperature', 'weight',
            'is_private', 'is_confidential',
        ]
        read_only_fields = ['id']

class HealthRecordUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = HealthRecord
        fields = [
            'title', 'content', 'blood_pressure', 'heart_rate',
            'temperature', 'weight'
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
            'id', 'amount', 'method', 'description', 'appointment_ids',
            'status', 'mpesa_transaction_id',
        ]
        read_only_fields = ['id']

    def create(self, validated_data):
        validated_data.pop('appointment_ids', None)
        return super().create(validated_data)

# ============ NURSE EARNING SERIALIZERS ============

class NurseEarningSerializer(serializers.ModelSerializer):
    class Meta:
        model = NurseEarning
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'paid_at']

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

class NotificationSerializer(serializers.ModelSerializer):
    event_type_display = serializers.CharField(source='get_event_type_display', read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id', 'recipient', 'appointment', 'event_type', 'event_type_display',
            'title', 'message', 'is_read', 'created_at'
        ]
        read_only_fields = ['id', 'recipient', 'created_at']
