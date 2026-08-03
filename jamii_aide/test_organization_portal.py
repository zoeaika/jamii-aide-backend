from datetime import date, time, timedelta

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from jamii_aide.models import (
    Appointment,
    AppointmentStatus,
    CustomUser,
    EndUserProfile,
    FamilyMember,
    HealthcareNurse,
    Organization,
    OrganizationAdministrator,
    ServiceType,
    ShiftType,
    UserRole,
)


class OrganizationPortalAccessTests(APITestCase):
    def setUp(self):
        self.sys_admin = CustomUser.objects.create_user(
            username="sys_admin",
            email="sys_admin@example.com",
            password="StrongPass123!",
            role=UserRole.ADMIN,
            is_staff=True,
        )

        self.org_a = Organization.objects.create(name="Org A", code="ORGA")
        self.org_b = Organization.objects.create(name="Org B", code="ORGB")

        self.org_admin_user = CustomUser.objects.create_user(
            username="org_admin",
            email="org_admin@example.com",
            password="StrongPass123!",
            role=UserRole.ORGANIZATION_ADMIN,
        )
        OrganizationAdministrator.objects.create(
            user=self.org_admin_user,
            organization=self.org_a,
            job_title="Operations Manager",
            is_active=True,
        )

        self.nurse_a_user = CustomUser.objects.create_user(
            username="nurse_a",
            email="nurse_a@example.com",
            password="StrongPass123!",
            role=UserRole.NURSE,
        )
        self.nurse_a = HealthcareNurse.objects.create(
            user=self.nurse_a_user,
            organization=self.org_a,
            license_number="NURSE-ORGA-001",
            license_expiry=date.today() + timedelta(days=365),
            years_experience=5,
            status="APPROVED",
            is_active=True,
        )

        self.nurse_b_user = CustomUser.objects.create_user(
            username="nurse_b",
            email="nurse_b@example.com",
            password="StrongPass123!",
            role=UserRole.NURSE,
        )
        self.nurse_b = HealthcareNurse.objects.create(
            user=self.nurse_b_user,
            organization=self.org_b,
            license_number="NURSE-ORGB-001",
            license_expiry=date.today() + timedelta(days=365),
            years_experience=4,
            status="APPROVED",
            is_active=True,
        )

        self.end_user = CustomUser.objects.create_user(
            username="family_owner",
            email="family_owner@example.com",
            password="StrongPass123!",
            role=UserRole.USER,
        )
        self.end_user_profile = EndUserProfile.objects.create(
            user=self.end_user,
            current_country="Kenya",
            current_city="Nairobi",
        )
        self.family_member = FamilyMember.objects.create(
            end_user_profile=self.end_user_profile,
            first_name="Mary",
            last_name="Kamau",
            date_of_birth=date(1960, 1, 1),
            gender="FEMALE",
        )

        self.appointment_for_org_a = Appointment.objects.create(
            family_member=self.family_member,
            end_user_profile=self.end_user_profile,
            appointment_date=date.today() + timedelta(days=2),
            start_time=time(9, 0),
            end_time=time(11, 0),
            reason="Check-in",
            service_type=ServiceType.WELLNESS_VISIT,
            shift_type=ShiftType.DAILY_PER_HOUR_12H,
            visit_address="Westlands",
            visit_city="Nairobi",
            status=AppointmentStatus.APPROVED,
            nurse=self.nurse_a,
            suggested_nurse=self.nurse_a,
        )
        self.appointment_for_org_b = Appointment.objects.create(
            family_member=self.family_member,
            end_user_profile=self.end_user_profile,
            appointment_date=date.today() + timedelta(days=3),
            start_time=time(10, 0),
            end_time=time(12, 0),
            reason="Follow-up",
            service_type=ServiceType.CARE_VISIT,
            shift_type=ShiftType.DAILY_PER_HOUR_12H,
            visit_address="Kilimani",
            visit_city="Nairobi",
            status=AppointmentStatus.APPROVED,
            nurse=self.nurse_b,
            suggested_nurse=self.nurse_b,
        )

    def test_org_admin_sees_only_own_organization_nurses(self):
        self.client.force_authenticate(user=self.org_admin_user)

        response = self.client.get(reverse("nurse-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.data.get("results", response.data)
        returned_ids = {item["id"] for item in payload}
        self.assertIn(str(self.nurse_a.id), returned_ids)
        self.assertNotIn(str(self.nurse_b.id), returned_ids)

    def test_org_admin_sees_only_appointments_for_own_nurses(self):
        self.client.force_authenticate(user=self.org_admin_user)

        response = self.client.get(reverse("appointment-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.data.get("results", response.data)
        returned_ids = {item["id"] for item in payload}
        self.assertIn(str(self.appointment_for_org_a.id), returned_ids)
        self.assertNotIn(str(self.appointment_for_org_b.id), returned_ids)

    def test_admin_change_role_to_org_admin_requires_organization_id(self):
        target_user = CustomUser.objects.create_user(
            username="target_user",
            email="target_user@example.com",
            password="StrongPass123!",
            role=UserRole.USER,
        )

        self.client.force_authenticate(user=self.sys_admin)

        missing_org_response = self.client.post(
            reverse("admin-user-change-role", kwargs={"pk": str(target_user.id)}),
            {"role": UserRole.ORGANIZATION_ADMIN},
            format="json",
        )
        self.assertEqual(missing_org_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("organization_id", missing_org_response.data)

        success_response = self.client.post(
            reverse("admin-user-change-role", kwargs={"pk": str(target_user.id)}),
            {"role": UserRole.ORGANIZATION_ADMIN, "organization_id": str(self.org_b.id)},
            format="json",
        )
        self.assertEqual(success_response.status_code, status.HTTP_200_OK)
        target_user.refresh_from_db()
        self.assertEqual(target_user.role, UserRole.ORGANIZATION_ADMIN)
        admin_profile = OrganizationAdministrator.objects.get(user=target_user)
        self.assertEqual(admin_profile.organization, self.org_b)
