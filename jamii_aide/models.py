from django.db import models
from django.contrib.auth.models import AbstractUser, UserManager
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
import uuid

# ============ CHOICE FIELDS ============

class UserRole(models.TextChoices):
    USER = "user", "User"
    NURSE = "nurse", "Nurse"
    ADMIN = "admin", "Admin"
    ORGANIZATION_ADMIN = "organization_admin", "Organization Admin"


class CustomUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('role', UserRole.ADMIN)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return super().create_superuser(username, email=email, password=password, **extra_fields)

class AppointmentStatus(models.TextChoices):
    SUBMITTED = "SUBMITTED", "Submitted"
    UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
    NURSE_SUGGESTED = "NURSE_SUGGESTED", "Nurse Suggested"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    PENDING = "PENDING", "Pending"
    CONFIRMED = "CONFIRMED", "Confirmed"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"
    NO_SHOW = "NO_SHOW", "No Show"
    RESCHEDULED = "RESCHEDULED", "Rescheduled"


class ShiftType(models.TextChoices):
    DAILY_PER_HOUR_12H = "DAILY_PER_HOUR_12H", "Daily Per Hour - 12 Hrs"
    LIVE_IN_24H = "LIVE_IN_24H", "Live In - 24 Hrs"


class ServiceType(models.TextChoices):
    WELLNESS_VISIT = "WELLNESS_VISIT", "Wellness Visit"
    CARE_VISIT = "CARE_VISIT", "Care Visit"
    CHRONIC_CONDITION_VISIT = "CHRONIC_CONDITION_VISIT", "Chronic Condition Visit"
    DAILY_CARE = "DAILY_CARE", "Daily Care"
    LIVE_IN_CARE = "LIVE_IN_CARE", "Live-in Care"
    EMERGENCY_ACCOMPANIMENT = "EMERGENCY_ACCOMPANIMENT", "Emergency Accompaniment"


class EvaluationType(models.TextChoices):
    ONLINE_CALL = "ONLINE_CALL", "Online Call"
    PHYSICAL_VISIT = "PHYSICAL_VISIT", "Physical Visit"

class HealthRecordType(models.TextChoices):
    APPOINTMENT_NOTES = "APPOINTMENT_NOTES", "Appointment Notes"
    LAB_RESULT = "LAB_RESULT", "Lab Result"
    VITAL_SIGNS = "VITAL_SIGNS", "Vital Signs"
    DIAGNOSIS = "DIAGNOSIS", "Diagnosis"
    GENERAL_NOTE = "GENERAL_NOTE", "General Note"

class PaymentStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"
    REFUNDED = "REFUNDED", "Refunded"

class PaymentMethod(models.TextChoices):
    MPESA = "MPESA", "M-Pesa"
    CARD = "CARD", "Card"
    BANK_TRANSFER = "BANK_TRANSFER", "Bank Transfer"

class NurseStatus(models.TextChoices):
    PENDING = "PENDING", "Pending Review"
    APPROVED = "APPROVED", "Approved"
    SUSPENDED = "SUSPENDED", "Suspended"


class ProfessionalType(models.TextChoices):
    PHYSIOTHERAPIST = "PHYSIOTHERAPIST", "Physiotherapist"
    CAREGIVER_NURSE = "CAREGIVER_NURSE", "Caregiver Nurse"
    PALLIATIVE_CARE_NURSE = "PALLIATIVE_CARE_NURSE", "Palliative Care Nurse"


class NotificationEventType(models.TextChoices):
    REQUEST_SUBMITTED = "REQUEST_SUBMITTED", "Request Submitted"
    NURSE_SUGGESTED = "NURSE_SUGGESTED", "Nurse Suggested"
    REQUEST_APPROVED = "REQUEST_APPROVED", "Request Approved"
    REQUEST_REJECTED = "REQUEST_REJECTED", "Request Rejected"
    NURSE_VERIFIED = "NURSE_VERIFIED", "Nurse Verified"
    NURSE_REJECTED = "NURSE_REJECTED", "Nurse Rejected"
    ORGANIZATION_VERIFIED = "ORGANIZATION_VERIFIED", "Organization Verified"
    ORGANIZATION_REJECTED = "ORGANIZATION_REJECTED", "Organization Rejected"
    ROLE_CHANGED = "ROLE_CHANGED", "Role Changed"

# ============ CUSTOM USER MODEL ============

class CustomUser(AbstractUser):
    """Custom user model with role-based access"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, null=True, unique=True)
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.USER
    )
    profile_image = models.ImageField(upload_to='profiles/', blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login = models.DateTimeField(blank=True, null=True)

    objects = CustomUserManager()

    class Meta:
        db_table = 'users'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['role']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"

    def get_effective_role(self):
        if self.is_staff or self.is_superuser:
            return UserRole.ADMIN
        return self.role

    def get_effective_role_display(self):
        return UserRole(self.get_effective_role()).label

# ============ DIASPORA USER ============

class EndUserProfile(models.Model):
    """Profile for end users managing family members."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='end_user_profile'
    )
    current_country = models.CharField(max_length=100)
    current_city = models.CharField(max_length=100, blank=True, null=True)
    timezone = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'end_user_profiles'
        verbose_name = 'End User Profile'
        verbose_name_plural = 'End User Profiles'

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.current_country}"


class Organization(models.Model):
    """Organization that groups nurses and organization administrators."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'organizations'
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.name


class OrganizationAdministrator(models.Model):
    """Profile that links an organization admin user to an organization."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='organization_admin_profile',
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='administrators',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'organization_administrators'
        verbose_name = 'Organization Administrator'
        verbose_name_plural = 'Organization Administrators'
        indexes = [
            models.Index(fields=['organization']),
        ]

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.organization.name}"

# ============ HEALTHCARE NURSE ============

class HealthcareNurse(models.Model):
    """Profile for healthcare nurses providing services"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='healthcare_nurse'
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name='nurses',
        blank=True,
        null=True,
    )
    license_number = models.CharField(max_length=50, unique=True)
    license_expiry = models.DateField()
    professional_type = models.CharField(
        max_length=30,
        choices=ProfessionalType.choices,
        default=ProfessionalType.CAREGIVER_NURSE,
        db_index=True,
    )
    specializations = models.JSONField(default=list)  # ["Geriatric Care", "Wound Care"]
    languages = models.JSONField(default=list)  # ["English", "Swahili", "Luo"]
    years_experience = models.IntegerField(validators=[MinValueValidator(0)])
    bio = models.TextField(blank=True, null=True)
    certifications = models.JSONField(default=list)  # URLs
    service_areas = models.JSONField(default=list)  # ["Nairobi", "Kisumu"]
    
    # Performance metrics
    total_appointments = models.IntegerField(default=0)
    completed_appointments = models.IntegerField(default=0)
    rating = models.FloatField(default=0.0, validators=[MinValueValidator(0), MaxValueValidator(5)])
    total_reviews = models.IntegerField(default=0)
    
    # Status
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    status = models.CharField(
        max_length=20,
        choices=NurseStatus.choices,
        default=NurseStatus.APPROVED
    )
    # Nurse-controlled toggle for accepting new auto-matched requests, separate from
    # is_active (which reflects admin approval/suspension of the account).
    is_accepting_requests = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'healthcare_nurses'
        verbose_name = 'Healthcare Nurse'
        verbose_name_plural = 'Healthcare Nurses'
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['professional_type']),
            models.Index(fields=['is_verified']),
            models.Index(fields=['rating']),
            models.Index(fields=['organization']),
        ]

    def __str__(self):
        return f"Nurse {self.user.get_full_name()} ({self.license_number})"

# ============ FAMILY MEMBER ============

class FamilyMember(models.Model):
    """Person back home receiving care"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    end_user_profile = models.ForeignKey(
        EndUserProfile,
        on_delete=models.CASCADE,
        related_name='family_members'
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    gender = models.CharField(
        max_length=10,
        choices=[('MALE', 'Male'), ('FEMALE', 'Female'), ('OTHER', 'Other')]
    )
    id_number = models.CharField(max_length=50, blank=True, null=True)
    profile_image = models.ImageField(upload_to='family/', blank=True, null=True)
    
    # Contact
    phone = models.CharField(max_length=20, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    
    # Health info
    blood_type = models.CharField(max_length=5, blank=True, null=True)
    known_allergies = models.TextField(blank=True, null=True)
    chronic_conditions = models.TextField(blank=True, null=True)
    current_medications = models.TextField(blank=True, null=True)
    emergency_contact = models.CharField(max_length=100, blank=True, null=True)
    emergency_phone = models.CharField(max_length=20, blank=True, null=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'family_members'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['end_user_profile']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

# ============ AVAILABILITY SLOT ============

class AvailabilitySlot(models.Model):
    """Nurse availability schedule"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nurse = models.ForeignKey(
        HealthcareNurse,
        on_delete=models.CASCADE,
        related_name='availability_slots'
    )
    DAY_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]
    day_of_week = models.IntegerField(choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'availability_slots'
        unique_together = ['nurse', 'day_of_week', 'start_time']
        ordering = ['day_of_week', 'start_time']

    def __str__(self):
        return f"{self.nurse.user.get_full_name()} - {self.get_day_of_week_display()} {self.start_time}-{self.end_time}"

# ============ APPOINTMENT ============

class Appointment(models.Model):
    """Booking between diaspora user and nurse"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    family_member = models.ForeignKey(
        FamilyMember,
        on_delete=models.CASCADE,
        related_name='appointments'
    )
    nurse = models.ForeignKey(
        HealthcareNurse,
        on_delete=models.CASCADE,
        related_name='appointments',
        blank=True,
        null=True
    )
    suggested_nurse = models.ForeignKey(
        HealthcareNurse,
        on_delete=models.SET_NULL,
        related_name='suggested_appointments',
        blank=True,
        null=True
    )
    end_user_profile = models.ForeignKey(
        EndUserProfile,
        on_delete=models.CASCADE,
        related_name='appointments'
    )
    
    appointment_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    reason = models.CharField(max_length=255)
    notes = models.TextField(blank=True, null=True)
    additional_notes = models.TextField(blank=True, null=True)
    service_type = models.CharField(
        max_length=40,
        choices=ServiceType.choices,
    )
    shift_type = models.CharField(
        max_length=30,
        choices=ShiftType.choices,
        default=ShiftType.DAILY_PER_HOUR_12H
    )
    evaluation_type = models.CharField(
        max_length=20,
        choices=EvaluationType.choices,
        blank=True,
        null=True
    )
    admission_clause_accepted = models.BooleanField(default=False)
    admission_support_in_subscription = models.BooleanField(default=False)
    admission_questionnaire = models.JSONField(default=dict, blank=True)
    
    # Location
    visit_address = models.CharField(max_length=255)
    visit_city = models.CharField(max_length=100)
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=AppointmentStatus.choices,
        default=AppointmentStatus.SUBMITTED,
        db_index=True
    )
    reviewed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        related_name='reviewed_appointments',
        blank=True,
        null=True
    )
    rejection_reason = models.TextField(blank=True, null=True)
    decision_at = models.DateTimeField(blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=1000.00)
    payment = models.ForeignKey(
        'Payment',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='appointments'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'appointments'
        ordering = ['-appointment_date']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['appointment_date']),
            models.Index(fields=['end_user_profile']),
            models.Index(fields=['nurse']),
        ]

    def __str__(self):
        return f"Appointment - {self.family_member.first_name} with {self.nurse.user.get_full_name()}"

# ============ HEALTH RECORD ============

class HealthRecord(models.Model):
    """Health notes, vital signs, diagnoses, etc."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    family_member = models.ForeignKey(
        FamilyMember,
        on_delete=models.CASCADE,
        related_name='health_records'
    )
    nurse = models.ForeignKey(
        HealthcareNurse,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='health_records'
    )
    end_user_profile = models.ForeignKey(
        EndUserProfile,
        on_delete=models.CASCADE,
        related_name='health_records'
    )
    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='health_records'
    )
    
    type = models.CharField(
        max_length=20,
        choices=HealthRecordType.choices,
        db_index=True
    )
    title = models.CharField(max_length=255)
    content = models.TextField(blank=True, null=True)
    
    # Vital signs
    blood_pressure = models.CharField(max_length=20, blank=True, null=True)  # 120/80
    heart_rate = models.IntegerField(blank=True, null=True)
    temperature = models.FloatField(blank=True, null=True)
    weight = models.FloatField(blank=True, null=True)
    
    # Files
    file = models.FileField(upload_to='health_records/', blank=True, null=True)
    
    is_private = models.BooleanField(default=False)
    is_confidential = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'health_records'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['type']),
            models.Index(fields=['family_member']),
            models.Index(fields=['end_user_profile']),
        ]

    def __str__(self):
        return f"{self.get_type_display()} - {self.title}"

# ============ PAYMENT ============

class Payment(models.Model):
    """Payment transactions"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    end_user_profile = models.ForeignKey(
        EndUserProfile,
        on_delete=models.CASCADE,
        related_name='payments'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='KES')
    method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        db_index=True
    )
    
    # M-Pesa
    mpesa_transaction_id = models.CharField(max_length=100, blank=True, null=True)
    mpesa_receipt_number = models.CharField(max_length=100, blank=True, null=True)
    
    # Card
    card_last_four = models.CharField(max_length=4, blank=True, null=True)
    
    description = models.TextField()
    transaction_date = models.DateTimeField(blank=True, null=True, db_index=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    failure_reason = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payments'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['end_user_profile']),
        ]

    def __str__(self):
        return f"Payment - {self.amount} {self.currency} ({self.get_status_display()})"

# ============ NURSE EARNING ============

class NurseEarning(models.Model):
    """Track nurse earnings"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nurse = models.ForeignKey(
        HealthcareNurse,
        on_delete=models.CASCADE,
        related_name='earnings'
    )
    appointment_count = models.IntegerField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='KES')
    payment_period_start = models.DateField()
    payment_period_end = models.DateField()
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        db_index=True
    )
    paid_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'nurse_earnings'
        ordering = ['-payment_period_end']
        indexes = [
            models.Index(fields=['nurse']),
            models.Index(fields=['payment_status']),
        ]

    def __str__(self):
        return f"{self.nurse.user.get_full_name()} - {self.amount} {self.currency}"

# ============ REVIEW ============

class Review(models.Model):
    """Appointment reviews and ratings"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.CASCADE,
        related_name='review'
    )
    nurse = models.ForeignKey(
        HealthcareNurse,
        on_delete=models.CASCADE,
        related_name='reviews'
    )
    end_user_profile = models.ForeignKey(
        EndUserProfile,
        on_delete=models.CASCADE,
        related_name='reviews'
    )
    
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField(max_length=255, blank=True, null=True)
    comment = models.TextField(blank=True, null=True)
    
    # Detailed ratings
    professionalism = models.IntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    punctuality = models.IntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    communication = models.IntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reviews'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['nurse']),
            models.Index(fields=['rating']),
        ]

    def __str__(self):
        return f"Review - {self.nurse.user.get_full_name()} ({self.rating}★)"

class Notification(models.Model):
    """User notification events."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name='notifications',
        blank=True,
        null=True
    )
    event_type = models.CharField(max_length=30, choices=NotificationEventType.choices)
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient']),
            models.Index(fields=['event_type']),
            models.Index(fields=['is_read']),
        ]

    def __str__(self):
        return f"{self.recipient.email} - {self.event_type}"
