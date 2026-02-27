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
    Notification,
    NotificationEventType,
    ProfessionalType,
    ShiftType,
    UserRole,
)


class AppointmentNotificationFlowTests(APITestCase):
    def setUp(self):
        self.admin_user = CustomUser.objects.create_user(
            username="admin1",
            email="admin1@example.com",
            password="StrongPass123!",
            role=UserRole.ADMIN,
            is_staff=True,
        )

        self.end_user_user = CustomUser.objects.create_user(
            username="diaspora1",
            email="diaspora1@example.com",
            password="StrongPass123!",
            role=UserRole.END_USER,
        )
        self.end_user_profile = EndUserProfile.objects.create(
            user=self.end_user_user,
            current_country="USA",
            current_city="Dallas",
        )

        self.nurse_user = CustomUser.objects.create_user(
            username="nurse1",
            email="nurse1@example.com",
            password="StrongPass123!",
            role=UserRole.HEALTHCARE_NURSE,
        )
        self.nurse = HealthcareNurse.objects.create(
            user=self.nurse_user,
            license_number="NURSE-001",
            license_expiry=date.today() + timedelta(days=365),
            years_experience=5,
            status="APPROVED",
            is_active=True,
        )

        self.family_member = FamilyMember.objects.create(
            end_user_profile=self.end_user_profile,
            first_name="Mary",
            last_name="Wanjiku",
            date_of_birth=date(1958, 1, 1),
            gender="FEMALE",
        )

        self.appointment = Appointment.objects.create(
            family_member=self.family_member,
            end_user_profile=self.end_user_profile,
            appointment_date=date.today() + timedelta(days=1),
            start_time=time(9, 0),
            end_time=time(11, 0),
            reason="Post-discharge care",
            service_type="Home Visit",
            shift_type=ShiftType.DAILY_PER_HOUR_12H,
            visit_address="Westlands",
            visit_city="Nairobi",
            status=AppointmentStatus.SUBMITTED,
        )

    def test_admin_suggest_nurse_creates_notification_for_request_owner(self):
        self.client.force_authenticate(user=self.admin_user)

        url = reverse("appointment-suggest-nurse", kwargs={"pk": self.appointment.id})
        response = self.client.post(url, {"suggested_nurse": str(self.nurse.id)}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.suggested_nurse, self.nurse)
        self.assertEqual(self.appointment.status, AppointmentStatus.NURSE_SUGGESTED)

        notification = Notification.objects.get(
            appointment=self.appointment,
            recipient=self.end_user_user,
            event_type=NotificationEventType.NURSE_SUGGESTED,
        )
        self.assertIn("suggested a nurse", notification.message.lower())

    def test_admin_decision_creates_approved_and_rejected_notifications(self):
        self.client.force_authenticate(user=self.admin_user)

        suggest_url = reverse("appointment-suggest-nurse", kwargs={"pk": self.appointment.id})
        self.client.post(suggest_url, {"suggested_nurse": str(self.nurse.id)}, format="json")

        decision_url = reverse("appointment-decision", kwargs={"pk": self.appointment.id})
        approved_response = self.client.post(
            decision_url,
            {"decision": AppointmentStatus.APPROVED},
            format="json",
        )
        self.assertEqual(approved_response.status_code, status.HTTP_200_OK)

        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, AppointmentStatus.APPROVED)
        self.assertEqual(self.appointment.nurse, self.nurse)
        self.assertTrue(
            Notification.objects.filter(
                appointment=self.appointment,
                recipient=self.end_user_user,
                event_type=NotificationEventType.REQUEST_APPROVED,
            ).exists()
        )

        second_appointment = Appointment.objects.create(
            family_member=self.family_member,
            end_user_profile=self.end_user_profile,
            appointment_date=date.today() + timedelta(days=2),
            start_time=time(10, 0),
            end_time=time(12, 0),
            reason="Admission support",
            service_type="Home Visit",
            shift_type=ShiftType.LIVE_IN_24H,
            visit_address="Kilimani",
            visit_city="Nairobi",
            status=AppointmentStatus.SUBMITTED,
        )

        rejected_response = self.client.post(
            reverse("appointment-decision", kwargs={"pk": second_appointment.id}),
            {"decision": AppointmentStatus.REJECTED, "rejection_reason": "Incomplete medical details"},
            format="json",
        )
        self.assertEqual(rejected_response.status_code, status.HTTP_200_OK)

        second_appointment.refresh_from_db()
        self.assertEqual(second_appointment.status, AppointmentStatus.REJECTED)

        rejected_notification = Notification.objects.get(
            appointment=second_appointment,
            recipient=self.end_user_user,
            event_type=NotificationEventType.REQUEST_REJECTED,
        )
        self.assertIn("incomplete medical details", rejected_notification.message.lower())

    def test_notifications_are_scoped_to_authenticated_recipient(self):
        other_user = CustomUser.objects.create_user(
            username="diaspora2",
            email="diaspora2@example.com",
            password="StrongPass123!",
            role=UserRole.END_USER,
        )

        own_notification = Notification.objects.create(
            recipient=self.end_user_user,
            appointment=self.appointment,
            event_type=NotificationEventType.NURSE_SUGGESTED,
            title="Nurse Suggested",
            message="Admin suggested a nurse.",
        )
        other_notification = Notification.objects.create(
            recipient=other_user,
            appointment=self.appointment,
            event_type=NotificationEventType.REQUEST_APPROVED,
            title="Care Request Approved",
            message="Approved.",
        )

        self.client.force_authenticate(user=self.end_user_user)

        list_response = self.client.get(reverse("notification-list"))
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        payload = list_response.data.get("results", list_response.data)
        returned_ids = {item["id"] for item in payload}
        self.assertIn(str(own_notification.id), returned_ids)
        self.assertNotIn(str(other_notification.id), returned_ids)

        mark_read_response = self.client.post(
            reverse("notification-mark-read", kwargs={"pk": own_notification.id})
        )
        self.assertEqual(mark_read_response.status_code, status.HTTP_200_OK)
        own_notification.refresh_from_db()
        self.assertTrue(own_notification.is_read)

        forbidden_mark_response = self.client.post(
            reverse("notification-mark-read", kwargs={"pk": other_notification.id})
        )
        self.assertEqual(forbidden_mark_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_notification_unread_count_endpoint(self):
        Notification.objects.create(
            recipient=self.end_user_user,
            appointment=self.appointment,
            event_type=NotificationEventType.NURSE_SUGGESTED,
            title="Nurse Suggested",
            message="Admin suggested a nurse.",
            is_read=False,
        )
        Notification.objects.create(
            recipient=self.end_user_user,
            appointment=self.appointment,
            event_type=NotificationEventType.REQUEST_APPROVED,
            title="Approved",
            message="Approved.",
            is_read=True,
        )

        self.client.force_authenticate(user=self.end_user_user)
        response = self.client.get(reverse("notification-unread-count"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["unread_count"], 1)

    def test_non_admin_cannot_call_admin_appointment_actions(self):
        self.client.force_authenticate(user=self.end_user_user)

        suggest_response = self.client.post(
            reverse("appointment-suggest-nurse", kwargs={"pk": self.appointment.id}),
            {"suggested_nurse": str(self.nurse.id)},
            format="json",
        )
        self.assertEqual(suggest_response.status_code, status.HTTP_403_FORBIDDEN)

        decision_response = self.client.post(
            reverse("appointment-decision", kwargs={"pk": self.appointment.id}),
            {"decision": AppointmentStatus.REJECTED, "rejection_reason": "N/A"},
            format="json",
        )
        self.assertEqual(decision_response.status_code, status.HTTP_403_FORBIDDEN)

        pending_response = self.client.get(reverse("appointment-pending-matching"))
        self.assertEqual(pending_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_transitions_are_blocked(self):
        self.client.force_authenticate(user=self.admin_user)

        decision_without_nurse = self.client.post(
            reverse("appointment-decision", kwargs={"pk": self.appointment.id}),
            {"decision": AppointmentStatus.APPROVED},
            format="json",
        )
        self.assertEqual(decision_without_nurse.status_code, status.HTTP_400_BAD_REQUEST)

        reject_without_reason = self.client.post(
            reverse("appointment-decision", kwargs={"pk": self.appointment.id}),
            {"decision": AppointmentStatus.REJECTED},
            format="json",
        )
        self.assertEqual(reject_without_reason.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.force_authenticate(user=self.end_user_user)
        confirm_invalid_status = self.client.post(
            reverse("appointment-confirm", kwargs={"pk": self.appointment.id})
        )
        self.assertEqual(confirm_invalid_status.status_code, status.HTTP_400_BAD_REQUEST)

    def test_end_user_role_can_submit_care_request(self):
        end_user = CustomUser.objects.create_user(
            username="end_user_1",
            email="end_user_1@example.com",
            password="StrongPass123!",
            role=UserRole.END_USER,
        )
        end_user_profile = EndUserProfile.objects.create(
            user=end_user,
            current_country="UK",
            current_city="London",
        )
        family_member = FamilyMember.objects.create(
            end_user_profile=end_user_profile,
            first_name="John",
            last_name="Doe",
            date_of_birth=date(1960, 5, 5),
            gender="MALE",
        )

        self.client.force_authenticate(user=end_user)
        response = self.client.post(
            reverse("appointment-list"),
            {
                "family_member": str(family_member.id),
                "appointment_date": str(date.today() + timedelta(days=3)),
                "start_time": "09:00:00",
                "end_time": "11:00:00",
                "reason": "Home care support",
                "service_type": "Home Visit",
                "shift_type": ShiftType.DAILY_PER_HOUR_12H,
                "visit_address": "Karen",
                "visit_city": "Nairobi",
                "notes": "Needs mobility support",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Appointment.objects.get(
            end_user_profile=end_user_profile,
            reason="Home care support",
            service_type="Home Visit",
        )
        self.assertEqual(created.status, AppointmentStatus.SUBMITTED)


class HealthcareNurseProfessionalTypeTests(APITestCase):
    def setUp(self):
        self.admin_user = CustomUser.objects.create_user(
            username="admin_nurse_filters",
            email="admin_nurse_filters@example.com",
            password="StrongPass123!",
            role=UserRole.ADMIN,
            is_staff=True,
        )

        physio_user = CustomUser.objects.create_user(
            username="physio_user",
            email="physio@example.com",
            password="StrongPass123!",
            role=UserRole.HEALTHCARE_NURSE,
        )
        self.physio = HealthcareNurse.objects.create(
            user=physio_user,
            license_number="NURSE-PHYSIO-001",
            license_expiry=date.today() + timedelta(days=365),
            professional_type=ProfessionalType.PHYSIOTHERAPIST,
            years_experience=6,
            status="APPROVED",
            is_active=True,
        )

        caregiver_user = CustomUser.objects.create_user(
            username="caregiver_user",
            email="caregiver@example.com",
            password="StrongPass123!",
            role=UserRole.HEALTHCARE_NURSE,
        )
        self.caregiver = HealthcareNurse.objects.create(
            user=caregiver_user,
            license_number="NURSE-CARE-001",
            license_expiry=date.today() + timedelta(days=365),
            professional_type=ProfessionalType.CAREGIVER_NURSE,
            years_experience=4,
            status="APPROVED",
            is_active=True,
        )

    def test_nurse_list_can_be_filtered_by_professional_type(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(
            reverse("nurse-list"),
            {"professional_type": ProfessionalType.PHYSIOTHERAPIST},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.data.get("results", response.data)
        returned_ids = {item["id"] for item in payload}
        self.assertIn(str(self.physio.id), returned_ids)
        self.assertNotIn(str(self.caregiver.id), returned_ids)

    def test_nurse_detail_includes_professional_type_display(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("nurse-detail", kwargs={"pk": self.physio.id}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["professional_type"], ProfessionalType.PHYSIOTHERAPIST)
        self.assertEqual(response.data["professional_type_display"], "Physiotherapist")


class FamilyMemberFlowTests(APITestCase):
    def setUp(self):
        self.end_user = CustomUser.objects.create_user(
            username="family_member_user",
            email="family_member_user@example.com",
            password="StrongPass123!",
            role=UserRole.END_USER,
        )
        self.end_user_profile = EndUserProfile.objects.create(
            user=self.end_user,
            current_country="USA",
            current_city="Seattle",
        )

    def test_end_user_can_create_family_member_without_end_user_profile_in_payload(self):
        self.client.force_authenticate(user=self.end_user)

        response = self.client.post(
            reverse("family-member-list"),
            {
                "first_name": "Asha",
                "last_name": "Njeri",
                "date_of_birth": "1959-06-01",
                "gender": "FEMALE",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = FamilyMember.objects.get(first_name="Asha", last_name="Njeri")
        self.assertEqual(created.end_user_profile, self.end_user_profile)

    def test_saved_family_member_appears_in_list_for_owner(self):
        member = FamilyMember.objects.create(
            end_user_profile=self.end_user_profile,
            first_name="Saved",
            last_name="Person",
            date_of_birth=date(1962, 1, 1),
            gender="MALE",
        )

        self.client.force_authenticate(user=self.end_user)
        response = self.client.get(reverse("family-member-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.data.get("results", response.data)
        returned_ids = {item["id"] for item in payload}
        self.assertIn(str(member.id), returned_ids)

    def test_family_member_list_auto_creates_missing_profile_for_end_user(self):
        user_without_profile = CustomUser.objects.create_user(
            username="missing_profile_user",
            email="missing_profile_user@example.com",
            password="StrongPass123!",
            role=UserRole.END_USER,
        )
        self.assertFalse(EndUserProfile.objects.filter(user=user_without_profile).exists())

        self.client.force_authenticate(user=user_without_profile)
        response = self.client.get(reverse("family-member-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(EndUserProfile.objects.filter(user=user_without_profile).exists())
        payload = response.data.get("results", response.data)
        self.assertEqual(payload, [])
