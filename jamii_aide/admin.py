from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from jamii_aide.models import (
    Appointment,
    CustomUser,
    EndUserProfile,
    FamilyMember,
    HealthcareNurse,
    Notification,
    Organization,
    OrganizationAdministrator,
    Payment,
)


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    ordering = ("email",)
    list_display = ("username", "email", "role", "is_staff", "is_superuser", "is_active")
    fieldsets = UserAdmin.fieldsets + (
        (
            "Jamii Aide",
            {
                "fields": (
                    "role",
                    "phone",
                    "profile_image",
                    "is_verified",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "Jamii Aide",
            {
                "fields": ("email", "role"),
            },
        ),
    )
    readonly_fields = ("created_at", "updated_at", "last_login")


@admin.register(EndUserProfile)
class EndUserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "current_country", "current_city", "created_at")
    search_fields = ("user__email", "user__username", "current_country", "current_city")
    readonly_fields = ("created_at", "updated_at")


@admin.register(FamilyMember)
class FamilyMemberAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "end_user_profile", "city", "is_active", "created_at")
    list_filter = ("is_active", "gender", "city", "created_at")
    search_fields = (
        "first_name",
        "last_name",
        "email",
        "phone",
        "end_user_profile__user__email",
        "end_user_profile__user__username",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(HealthcareNurse)
class HealthcareNurseAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "professional_type", "status", "is_verified", "is_active", "rating")
    list_filter = ("organization", "professional_type", "status", "is_verified", "is_active")
    search_fields = ("user__email", "user__username", "license_number", "specializations")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "updated_at")


@admin.register(OrganizationAdministrator)
class OrganizationAdministratorAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "created_at")
    list_filter = ("organization", "created_at")
    search_fields = ("user__email", "user__username", "organization__name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "family_member",
        "end_user_profile",
        "status",
        "appointment_date",
        "start_time",
        "nurse",
        "suggested_nurse",
        "created_at",
    )
    list_filter = ("status", "appointment_date", "visit_city", "service_type", "shift_type", "created_at")
    search_fields = (
        "id",
        "family_member__first_name",
        "family_member__last_name",
        "end_user_profile__user__email",
        "end_user_profile__user__username",
        "reason",
        "visit_address",
        "visit_city",
    )
    autocomplete_fields = ("family_member", "end_user_profile", "nurse", "suggested_nurse", "reviewed_by", "payment")
    readonly_fields = ("created_at", "updated_at", "decision_at")
    date_hierarchy = "appointment_date"


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "event_type", "appointment", "is_read", "created_at")
    list_filter = ("event_type", "is_read", "created_at")
    search_fields = ("recipient__email", "recipient__username", "title", "message")
    readonly_fields = ("created_at",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "end_user_profile", "amount", "currency", "method", "status", "created_at")
    list_filter = ("method", "status", "currency", "created_at")
    search_fields = (
        "id",
        "end_user_profile__user__email",
        "end_user_profile__user__username",
        "description",
        "mpesa_transaction_id",
        "mpesa_receipt_number",
        "provider_reference",
    )
    readonly_fields = ("created_at", "updated_at", "transaction_date", "completed_at")
