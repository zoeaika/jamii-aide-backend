from datetime import date, time, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from jamii_aide.models import (
    AvailabilitySlot,
    Appointment,
    AppointmentStatus,
    CustomUser,
    EndUserProfile,
    FamilyMember,
    HealthcareNurse,
    HealthRecord,
    Notification,
    NotificationEventType,
    Organization,
    OrganizationAdministrator,
    Payment,
    PaymentMethod,
    PaymentStatus,
    ProfessionalType,
    ServiceType,
    Review,
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
            role=UserRole.USER,
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
            role=UserRole.NURSE,
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
            service_type=ServiceType.WELLNESS_VISIT,
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
        self.assertEqual(self.appointment.nurse, self.nurse)
        self.assertEqual(self.appointment.status, AppointmentStatus.NURSE_SUGGESTED)

        notification = Notification.objects.get(
            appointment=self.appointment,
            recipient=self.end_user_user,
            event_type=NotificationEventType.NURSE_SUGGESTED,
        )
        self.assertIn("suggested a nurse", notification.message.lower())

    def test_admin_decision_creates_approved_and_rejected_notifications(self):
        self.client.force_authenticate(user=self.admin_user)

        decision_url = reverse("appointment-decision", kwargs={"pk": self.appointment.id})
        approved_response = self.client.post(
            decision_url,
            {"decision": AppointmentStatus.APPROVED, "assigned_nurse": str(self.nurse.id)},
            format="json",
        )
        self.assertEqual(approved_response.status_code, status.HTTP_200_OK)
        self.assertEqual(approved_response.data["nurse"]["id"], str(self.nurse.id))
        self.assertEqual(approved_response.data["nurse"]["user"]["email"], self.nurse_user.email)

        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, AppointmentStatus.APPROVED)
        self.assertEqual(self.appointment.nurse, self.nurse)
        self.assertEqual(self.appointment.suggested_nurse, self.nurse)
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
            service_type=ServiceType.WELLNESS_VISIT,
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

    def test_nurse_profile_exposes_assigned_schedule(self):
        self.client.force_authenticate(user=self.admin_user)
        self.client.post(
            reverse("appointment-suggest-nurse", kwargs={"pk": self.appointment.id}),
            {"suggested_nurse": str(self.nurse.id)},
            format="json",
        )
        self.client.post(
            reverse("appointment-decision", kwargs={"pk": self.appointment.id}),
            {"decision": AppointmentStatus.APPROVED},
            format="json",
        )

        self.client.force_authenticate(user=self.nurse_user)
        response = self.client.get(reverse("nurse-me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assigned_ids = {item["id"] for item in response.data["assigned_appointments"]}
        self.assertIn(str(self.appointment.id), assigned_ids)
        self.assertEqual(response.data["assigned_appointments"][0]["family_member"]["id"], str(self.family_member.id))

    def test_notifications_are_scoped_to_authenticated_recipient(self):
        other_user = CustomUser.objects.create_user(
            username="diaspora2",
            email="diaspora2@example.com",
            password="StrongPass123!",
            role=UserRole.USER,
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

    def test_appointment_auto_assigns_a_matching_available_nurse(self):
        nurse_user = CustomUser.objects.create_user(
            username="nurse_auto",
            email="nurse_auto@example.com",
            password="StrongPass123!",
            role=UserRole.NURSE,
        )
        nurse = HealthcareNurse.objects.create(
            user=nurse_user,
            license_number="NURSE-AUTO-001",
            license_expiry=date.today() + timedelta(days=365),
            professional_type=ProfessionalType.CAREGIVER_NURSE,
            years_experience=6,
            service_areas=["Nairobi", "Kisumu"],
            status="APPROVED",
            is_active=True,
            is_verified=True,
        )
        AvailabilitySlot.objects.create(
            nurse=nurse,
            day_of_week=(date.today() + timedelta(days=1)).weekday(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_available=True,
        )

        self.client.force_authenticate(user=self.end_user_user)
        response = self.client.post(
            reverse("appointment-list"),
            {
                "family_member": str(self.family_member.id),
                "appointment_date": str(date.today() + timedelta(days=1)),
                "start_time": "09:00:00",
                "end_time": "11:00:00",
                "reason": "Home care support",
                "service_type": ServiceType.CARE_VISIT,
                "shift_type": ShiftType.DAILY_PER_HOUR_12H,
                "visit_address": "Westlands",
                "visit_city": "Nairobi",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["nurse"]["id"], str(nurse.id))
        self.assertEqual(response.data["suggested_nurse"]["id"], str(nurse.id))
        created = Appointment.objects.get(id=response.data["id"])
        self.assertEqual(created.nurse, nurse)
        self.assertEqual(created.suggested_nurse, nurse)
        self.assertEqual(created.status, AppointmentStatus.APPROVED)

    def test_appointment_stays_pending_when_no_suitable_nurse_is_available(self):
        nurse_user = CustomUser.objects.create_user(
            username="nurse_unavailable",
            email="nurse_unavailable@example.com",
            password="StrongPass123!",
            role=UserRole.NURSE,
        )
        nurse = HealthcareNurse.objects.create(
            user=nurse_user,
            license_number="NURSE-AUTO-002",
            license_expiry=date.today() + timedelta(days=365),
            professional_type=ProfessionalType.PALLIATIVE_CARE_NURSE,
            years_experience=4,
            service_areas=["Nakuru"],
            status="APPROVED",
            is_active=True,
            is_verified=True,
        )
        AvailabilitySlot.objects.create(
            nurse=nurse,
            day_of_week=(date.today() + timedelta(days=2)).weekday(),
            start_time=time(8, 0),
            end_time=time(16, 0),
            is_available=True,
        )

        self.client.force_authenticate(user=self.end_user_user)
        response = self.client.post(
            reverse("appointment-list"),
            {
                "family_member": str(self.family_member.id),
                "appointment_date": str(date.today() + timedelta(days=2)),
                "start_time": "09:00:00",
                "end_time": "11:00:00",
                "reason": "Home care support",
                "service_type": ServiceType.CARE_VISIT,
                "shift_type": ShiftType.DAILY_PER_HOUR_12H,
                "visit_address": "Westlands",
                "visit_city": "Nairobi",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Appointment.objects.get(id=response.data["id"])
        self.assertIsNone(created.nurse)
        self.assertEqual(created.status, AppointmentStatus.SUBMITTED)

    def test_end_user_role_can_submit_care_request(self):
        end_user = CustomUser.objects.create_user(
            username="end_user_1",
            email="end_user_1@example.com",
            password="StrongPass123!",
            role=UserRole.USER,
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
                "service_type": ServiceType.WELLNESS_VISIT,
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
            service_type=ServiceType.WELLNESS_VISIT,
        )
        self.assertEqual(created.status, AppointmentStatus.SUBMITTED)
        admin_notification = Notification.objects.get(
            recipient=self.admin_user,
            appointment=created,
            event_type=NotificationEventType.REQUEST_SUBMITTED,
        )
        self.assertIn("awaiting admin review", admin_notification.message.lower())

    def test_end_user_can_submit_care_request_with_frontend_alias_payload(self):
        end_user = CustomUser.objects.create_user(
            username="end_user_alias",
            email="end_user_alias@example.com",
            password="StrongPass123!",
            role=UserRole.USER,
        )
        end_user_profile = EndUserProfile.objects.create(
            user=end_user,
            current_country="UK",
            current_city="London",
        )
        family_member = FamilyMember.objects.create(
            end_user_profile=end_user_profile,
            first_name="Grace",
            last_name="Doe",
            date_of_birth=date(1962, 5, 5),
            gender="FEMALE",
        )

        self.client.force_authenticate(user=end_user)
        response = self.client.post(
            reverse("appointment-list"),
            {
                "member": str(family_member.id),
                "appointmentDate": str(date.today() + timedelta(days=5)),
                "startTime": "09:00:00",
                "endTime": "11:00:00",
                "reason": "Recurring wellness support",
                "serviceType": "Wellness Visit",
                "shiftType": "12 hours",
                "visitAddress": "Westlands",
                "visitCity": "Nairobi",
                "additionalNotes": "Created from Next.js recurrence flow",
                "repeatMode": "WEEKLY",
                "repeatUntil": str(date.today() + timedelta(days=20)),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Appointment.objects.get(
            end_user_profile=end_user_profile,
            reason="Recurring wellness support",
        )
        self.assertEqual(created.family_member, family_member)
        self.assertEqual(created.service_type, ServiceType.WELLNESS_VISIT)
        self.assertEqual(created.shift_type, ShiftType.DAILY_PER_HOUR_12H)
        self.assertEqual(created.additional_notes, "Created from Next.js recurrence flow")

    def test_end_user_cannot_submit_care_request_for_other_users_family_member(self):
        requester = CustomUser.objects.create_user(
            username="requester_user",
            email="requester_user@example.com",
            password="StrongPass123!",
            role=UserRole.USER,
        )
        requester_profile = EndUserProfile.objects.create(
            user=requester,
            current_country="UK",
            current_city="London",
        )
        owner = CustomUser.objects.create_user(
            username="owner_user",
            email="owner_user@example.com",
            password="StrongPass123!",
            role=UserRole.USER,
        )
        owner_profile = EndUserProfile.objects.create(
            user=owner,
            current_country="Kenya",
            current_city="Nairobi",
        )
        other_family_member = FamilyMember.objects.create(
            end_user_profile=owner_profile,
            first_name="Else",
            last_name="Owned",
            date_of_birth=date(1964, 7, 7),
            gender="FEMALE",
        )

        self.client.force_authenticate(user=requester)
        response = self.client.post(
            reverse("appointment-list"),
            {
                "family_member": str(other_family_member.id),
                "appointment_date": str(date.today() + timedelta(days=3)),
                "start_time": "09:00:00",
                "end_time": "11:00:00",
                "reason": "Home care support",
                "service_type": ServiceType.WELLNESS_VISIT,
                "shift_type": ShiftType.DAILY_PER_HOUR_12H,
                "visit_address": "Karen",
                "visit_city": "Nairobi",
                "notes": "Needs mobility support",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("family_member", response.data)
        self.assertFalse(
            Appointment.objects.filter(
                end_user_profile=requester_profile,
                family_member=other_family_member,
            ).exists()
        )

    def test_end_user_cannot_submit_care_request_with_invalid_service_type(self):
        self.client.force_authenticate(user=self.end_user_user)

        response = self.client.post(
            reverse("appointment-list"),
            {
                "family_member": str(self.family_member.id),
                "appointment_date": str(date.today() + timedelta(days=3)),
                "start_time": "09:00:00",
                "end_time": "11:00:00",
                "reason": "Home care support",
                "service_type": "HOME_VISIT",
                "shift_type": ShiftType.DAILY_PER_HOUR_12H,
                "visit_address": "Karen",
                "visit_city": "Nairobi",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("service_type", response.data)

    def test_owner_can_cancel_from_allowed_status(self):
        self.client.force_authenticate(user=self.end_user_user)

        response = self.client.post(
            reverse("appointment-cancel", kwargs={"pk": self.appointment.id})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, AppointmentStatus.CANCELLED)

    def test_cancel_is_idempotent_if_already_cancelled(self):
        self.appointment.status = AppointmentStatus.CANCELLED
        self.appointment.save(update_fields=["status", "updated_at"])

        self.client.force_authenticate(user=self.end_user_user)
        response = self.client.post(
            reverse("appointment-cancel", kwargs={"pk": self.appointment.id})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], AppointmentStatus.CANCELLED)

    def test_cancel_enforces_ownership_with_403(self):
        other_user = CustomUser.objects.create_user(
            username="other_owner",
            email="other_owner@example.com",
            password="StrongPass123!",
            role=UserRole.USER,
        )
        EndUserProfile.objects.create(
            user=other_user,
            current_country="Canada",
            current_city="Toronto",
        )

        self.client.force_authenticate(user=other_user)
        response = self.client.post(
            reverse("appointment-cancel", kwargs={"pk": self.appointment.id})
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cancel_returns_404_when_appointment_not_found(self):
        self.client.force_authenticate(user=self.end_user_user)
        response = self.client.post(
            reverse("appointment-cancel", kwargs={"pk": "00000000-0000-0000-0000-000000000000"})
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cancel_returns_400_for_invalid_status_transition(self):
        self.appointment.status = AppointmentStatus.APPROVED
        self.appointment.save(update_fields=["status", "updated_at"])

        self.client.force_authenticate(user=self.end_user_user)
        response = self.client.post(
            reverse("appointment-cancel", kwargs={"pk": self.appointment.id})
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_nurse_list_is_scoped_to_assigned_appointments_only(self):
        other_nurse_user = CustomUser.objects.create_user(
            username="nurse2",
            email="nurse2@example.com",
            password="StrongPass123!",
            role=UserRole.NURSE,
        )
        other_nurse = HealthcareNurse.objects.create(
            user=other_nurse_user,
            license_number="NURSE-002",
            license_expiry=date.today() + timedelta(days=365),
            years_experience=4,
            status="APPROVED",
            is_active=True,
        )

        own_assigned = Appointment.objects.create(
            family_member=self.family_member,
            end_user_profile=self.end_user_profile,
            appointment_date=date.today() + timedelta(days=4),
            start_time=time(9, 0),
            end_time=time(10, 0),
            reason="Own nurse assignment",
            service_type=ServiceType.CARE_VISIT,
            shift_type=ShiftType.DAILY_PER_HOUR_12H,
            visit_address="Westlands",
            visit_city="Nairobi",
            status=AppointmentStatus.APPROVED,
            nurse=self.nurse,
        )
        other_assigned = Appointment.objects.create(
            family_member=self.family_member,
            end_user_profile=self.end_user_profile,
            appointment_date=date.today() + timedelta(days=5),
            start_time=time(10, 0),
            end_time=time(11, 0),
            reason="Other nurse assignment",
            service_type=ServiceType.CARE_VISIT,
            shift_type=ShiftType.DAILY_PER_HOUR_12H,
            visit_address="Kilimani",
            visit_city="Nairobi",
            status=AppointmentStatus.APPROVED,
            nurse=other_nurse,
        )

        self.client.force_authenticate(user=self.nurse_user)
        response = self.client.get(reverse("appointment-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.data.get("results", response.data)
        returned_ids = {item["id"] for item in payload}
        self.assertIn(str(own_assigned.id), returned_ids)
        self.assertNotIn(str(other_assigned.id), returned_ids)

    def test_nurse_schedule_can_filter_by_date_and_status(self):
        target_date = date.today() + timedelta(days=6)
        own_approved = Appointment.objects.create(
            family_member=self.family_member,
            end_user_profile=self.end_user_profile,
            appointment_date=target_date,
            start_time=time(8, 0),
            end_time=time(9, 0),
            reason="Approved schedule item",
            service_type=ServiceType.DAILY_CARE,
            shift_type=ShiftType.DAILY_PER_HOUR_12H,
            visit_address="CBD",
            visit_city="Nairobi",
            status=AppointmentStatus.APPROVED,
            nurse=self.nurse,
        )
        Appointment.objects.create(
            family_member=self.family_member,
            end_user_profile=self.end_user_profile,
            appointment_date=target_date,
            start_time=time(10, 0),
            end_time=time(11, 0),
            reason="Confirmed schedule item",
            service_type=ServiceType.DAILY_CARE,
            shift_type=ShiftType.DAILY_PER_HOUR_12H,
            visit_address="CBD",
            visit_city="Nairobi",
            status=AppointmentStatus.CONFIRMED,
            nurse=self.nurse,
        )
        Appointment.objects.create(
            family_member=self.family_member,
            end_user_profile=self.end_user_profile,
            appointment_date=target_date,
            start_time=time(12, 0),
            end_time=time(13, 0),
            reason="Different status item",
            service_type=ServiceType.DAILY_CARE,
            shift_type=ShiftType.DAILY_PER_HOUR_12H,
            visit_address="CBD",
            visit_city="Nairobi",
            status=AppointmentStatus.SUBMITTED,
            nurse=self.nurse,
        )

        self.client.force_authenticate(user=self.nurse_user)
        response = self.client.get(
            reverse("appointment-list"),
            {
                "appointment_date": str(target_date),
                "status": AppointmentStatus.APPROVED,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.data.get("results", response.data)
        returned_ids = {item["id"] for item in payload}
        self.assertIn(str(own_approved.id), returned_ids)
        for item in payload:
            self.assertEqual(item["status"], AppointmentStatus.APPROVED)

    def test_nurse_list_includes_approved_records_assigned_via_suggested_nurse(self):
        fallback_assigned = Appointment.objects.create(
            family_member=self.family_member,
            end_user_profile=self.end_user_profile,
            appointment_date=date.today() + timedelta(days=7),
            start_time=time(14, 0),
            end_time=time(15, 0),
            reason="Legacy suggested assignment",
            service_type=ServiceType.CARE_VISIT,
            shift_type=ShiftType.DAILY_PER_HOUR_12H,
            visit_address="South B",
            visit_city="Nairobi",
            status=AppointmentStatus.APPROVED,
            nurse=None,
            suggested_nurse=self.nurse,
        )

        self.client.force_authenticate(user=self.nurse_user)
        response = self.client.get(
            reverse("appointment-list"),
            {"status": AppointmentStatus.APPROVED},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.data.get("results", response.data)
        returned_ids = {item["id"] for item in payload}
        self.assertIn(str(fallback_assigned.id), returned_ids)

    def test_nurse_me_includes_legacy_suggested_nurse_assignments(self):
        legacy_assigned = Appointment.objects.create(
            family_member=self.family_member,
            end_user_profile=self.end_user_profile,
            appointment_date=date.today() + timedelta(days=8),
            start_time=time(16, 0),
            end_time=time(17, 0),
            reason="Legacy suggested-only assignment",
            service_type=ServiceType.CARE_VISIT,
            shift_type=ShiftType.DAILY_PER_HOUR_12H,
            visit_address="South C",
            visit_city="Nairobi",
            status=AppointmentStatus.APPROVED,
            nurse=None,
            suggested_nurse=self.nurse,
        )

        self.client.force_authenticate(user=self.nurse_user)
        response = self.client.get(reverse("nurse-me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assigned_ids = {item["id"] for item in response.data["assigned_appointments"]}
        self.assertIn(str(legacy_assigned.id), assigned_ids)


class AuthenticationFlowTests(APITestCase):
    def test_user_can_register_with_email_password_and_get_jwt_tokens(self):
        response = self.client.post(
            reverse("register"),
            {
                "email": "newuser@example.com",
                "password": "StrongPass123!",
                "first_name": "New",
                "last_name": "User",
                "current_country": "Kenya",
                "current_city": "Nairobi",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("access_token", response.data)
        self.assertIn("refresh_token", response.data)
        self.assertEqual(response.data["token_type"], "bearer")

        user = CustomUser.objects.get(email="newuser@example.com")
        self.assertTrue(user.check_password("StrongPass123!"))
        self.assertTrue(
            EndUserProfile.objects.filter(
                user=user,
                current_country="Kenya",
                current_city="Nairobi",
            ).exists()
        )

    def test_user_can_login_with_email_password(self):
        user = CustomUser.objects.create_user(
            username="login_user",
            email="login@example.com",
            password="StrongPass123!",
            role=UserRole.USER,
        )

        response = self.client.post(
            reverse("login"),
            {
                "email": "login@example.com",
                "password": "StrongPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access_token", response.data)
        self.assertIn("refresh_token", response.data)
        self.assertEqual(response.data["user"]["id"], str(user.id))

    def test_register_rejects_duplicate_email(self):
        CustomUser.objects.create_user(
            username="existing_user",
            email="existing@example.com",
            password="StrongPass123!",
            role=UserRole.USER,
        )

        response = self.client.post(
            reverse("register"),
            {
                "email": "existing@example.com",
                "password": "StrongPass123!",
                "first_name": "Existing",
                "last_name": "User",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_register_ignores_elevated_role_input_and_creates_standard_user(self):
        response = self.client.post(
            reverse("register"),
            {
                "email": "forced-admin@example.com",
                "password": "StrongPass123!",
                "first_name": "Forced",
                "last_name": "Admin",
                "role": UserRole.ADMIN,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created_user = CustomUser.objects.get(email="forced-admin@example.com")
        self.assertEqual(created_user.role, UserRole.USER)
        self.assertFalse(created_user.is_staff)

    @patch("jamii_aide.google_serializers.id_token.verify_oauth2_token")
    def test_google_login_creates_verified_end_user_and_profile(self, mock_verify):
        mock_verify.return_value = {
            "iss": "https://accounts.google.com",
            "sub": "google-user-123",
            "email": "googleuser@example.com",
            "email_verified": True,
            "given_name": "Google",
            "family_name": "User",
        }

        response = self.client.post(
            reverse("google-login"),
            {"credential": "valid-google-id-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["token_type"], "bearer")
        self.assertEqual(response.data["user"]["email"], "googleuser@example.com")

        user = CustomUser.objects.get(email="googleuser@example.com")
        self.assertEqual(user.role, UserRole.USER)
        self.assertTrue(user.is_verified)
        self.assertTrue(EndUserProfile.objects.filter(user=user).exists())

    @patch("jamii_aide.google_serializers.id_token.verify_oauth2_token")
    def test_google_login_passes_clock_skew_to_verifier(self, mock_verify):
        mock_verify.return_value = {
            "iss": "https://accounts.google.com",
            "sub": "google-user-skew-123",
            "email": "skew@example.com",
            "email_verified": True,
        }

        response = self.client.post(
            reverse("google-login"),
            {"credential": "skew-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_verify.assert_called_once()
        self.assertEqual(mock_verify.call_args.kwargs["clock_skew_in_seconds"], 5)

    @patch("jamii_aide.google_serializers.id_token.verify_oauth2_token")
    def test_google_login_updates_existing_user(self, mock_verify):
        existing_user = CustomUser.objects.create_user(
            username="google_existing",
            email="googleexisting@example.com",
            password="StrongPass123!",
            first_name="Old",
            last_name="Name",
            role=UserRole.USER,
            is_verified=False,
        )

        mock_verify.return_value = {
            "iss": "https://accounts.google.com",
            "sub": "google-user-789",
            "email": "googleexisting@example.com",
            "email_verified": True,
            "given_name": "Updated",
            "family_name": "Person",
        }

        response = self.client.post(
            reverse("google-login"),
            {"credential": "existing-user-google-id-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        existing_user.refresh_from_db()
        self.assertEqual(existing_user.first_name, "Updated")
        self.assertEqual(existing_user.last_name, "Person")
        self.assertTrue(existing_user.is_verified)

    @patch("jamii_aide.google_serializers.id_token.verify_oauth2_token")
    def test_google_login_accepts_id_token_field(self, mock_verify):
        mock_verify.return_value = {
            "iss": "https://accounts.google.com",
            "sub": "google-user-321",
            "email": "altfield@example.com",
            "email_verified": True,
        }

        response = self.client.post(
            reverse("google-login"),
            {"id_token": "alternate-google-id-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["email"], "altfield@example.com")

    @patch("jamii_aide.google_serializers.id_token.verify_oauth2_token")
    def test_google_login_rejects_unverified_email(self, mock_verify):
        mock_verify.return_value = {
            "iss": "https://accounts.google.com",
            "sub": "google-user-456",
            "email": "pending@example.com",
            "email_verified": False,
        }

        response = self.client.post(
            reverse("google-login"),
            {"credential": "unverified-google-id-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("non_field_errors", response.data)
        self.assertIn("verified", str(response.data["non_field_errors"][0]))


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
            role=UserRole.NURSE,
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
            role=UserRole.NURSE,
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


class WebAuthenticationFlowTests(TestCase):
    def test_signup_creates_standard_user_profile_and_redirects_to_user_dashboard(self):
        response = self.client.post(
            reverse("signup-page"),
            {
                "username": "web_signup_user",
                "email": "websignup@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertRedirects(response, reverse("dashboard-user"))
        created_user = CustomUser.objects.get(username="web_signup_user")
        self.assertEqual(created_user.role, UserRole.USER)
        self.assertTrue(EndUserProfile.objects.filter(user=created_user).exists())

    def test_login_redirects_nurse_to_nurse_dashboard(self):
        nurse_user = CustomUser.objects.create_user(
            username="web_nurse",
            email="webnurse@example.com",
            password="StrongPass123!",
            role=UserRole.NURSE,
        )

        response = self.client.post(
            reverse("login-page"),
            {
                "username": nurse_user.username,
                "password": "StrongPass123!",
            },
        )

        self.assertRedirects(response, reverse("dashboard-nurse"))

    def test_login_redirects_superuser_to_admin_dashboard(self):
        superuser = CustomUser.objects.create_superuser(
            username="web_admin",
            email="webadmin@example.com",
            password="StrongPass123!",
        )

        response = self.client.post(
            reverse("login-page"),
            {
                "username": superuser.username,
                "password": "StrongPass123!",
            },
        )

        superuser.refresh_from_db()
        self.assertEqual(superuser.role, UserRole.ADMIN)
        self.assertRedirects(response, reverse("dashboard-admin"))

    def test_existing_staff_user_with_standard_role_redirects_to_admin_dashboard(self):
        staff_user = CustomUser.objects.create_user(
            username="legacy_admin",
            email="legacy_admin@example.com",
            password="StrongPass123!",
            role=UserRole.USER,
            is_staff=True,
        )

        response = self.client.post(
            reverse("login-page"),
            {
                "username": staff_user.username,
                "password": "StrongPass123!",
            },
        )

        self.assertRedirects(response, reverse("dashboard-admin"))

    def test_nurse_dashboard_shows_assigned_schedule(self):
        nurse_user = CustomUser.objects.create_user(
            username="dashboard_nurse",
            email="dashboard_nurse@example.com",
            password="StrongPass123!",
            role=UserRole.NURSE,
        )
        nurse = HealthcareNurse.objects.create(
            user=nurse_user,
            license_number="NURSE-DASH-1",
            license_expiry=date.today() + timedelta(days=365),
            years_experience=4,
            status="APPROVED",
            is_active=True,
        )
        end_user = CustomUser.objects.create_user(
            username="dashboard_user",
            email="dashboard_user@example.com",
            password="StrongPass123!",
            role=UserRole.USER,
        )
        end_user_profile = EndUserProfile.objects.create(
            user=end_user,
            current_country="Kenya",
            current_city="Nairobi",
        )
        family_member = FamilyMember.objects.create(
            end_user_profile=end_user_profile,
            first_name="Test",
            last_name="Patient",
            date_of_birth=date(1965, 6, 1),
            gender="FEMALE",
        )
        Appointment.objects.create(
            family_member=family_member,
            end_user_profile=end_user_profile,
            appointment_date=date.today() + timedelta(days=2),
            start_time=time(9, 0),
            end_time=time(10, 0),
            reason="Care visit",
            service_type=ServiceType.CARE_VISIT,
            shift_type=ShiftType.DAILY_PER_HOUR_12H,
            visit_address="Westlands",
            visit_city="Nairobi",
            status=AppointmentStatus.APPROVED,
            nurse=nurse,
        )

        self.client.force_login(nurse_user)
        response = self.client.get(reverse("dashboard-nurse"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Assigned Appointments")
        self.assertContains(response, "Test Patient")

    def test_admin_dashboard_shows_assigned_nurse(self):
        admin_user = CustomUser.objects.create_user(
            username="dashboard_admin",
            email="dashboard_admin@example.com",
            password="StrongPass123!",
            role=UserRole.ADMIN,
            is_staff=True,
        )
        nurse_user = CustomUser.objects.create_user(
            username="dashboard_admin_nurse",
            email="dashboard_admin_nurse@example.com",
            password="StrongPass123!",
            role=UserRole.NURSE,
        )
        nurse = HealthcareNurse.objects.create(
            user=nurse_user,
            license_number="NURSE-DASH-2",
            license_expiry=date.today() + timedelta(days=365),
            years_experience=7,
            status="APPROVED",
            is_active=True,
        )
        end_user = CustomUser.objects.create_user(
            username="dashboard_owner",
            email="dashboard_owner@example.com",
            password="StrongPass123!",
            role=UserRole.USER,
        )
        end_user_profile = EndUserProfile.objects.create(
            user=end_user,
            current_country="Kenya",
            current_city="Mombasa",
        )
        family_member = FamilyMember.objects.create(
            end_user_profile=end_user_profile,
            first_name="Admin",
            last_name="Target",
            date_of_birth=date(1968, 2, 2),
            gender="MALE",
        )
        Appointment.objects.create(
            family_member=family_member,
            end_user_profile=end_user_profile,
            appointment_date=date.today() + timedelta(days=3),
            start_time=time(11, 0),
            end_time=time(12, 0),
            reason="Approval check",
            service_type=ServiceType.CARE_VISIT,
            shift_type=ShiftType.DAILY_PER_HOUR_12H,
            visit_address="CBD",
            visit_city="Nairobi",
            status=AppointmentStatus.APPROVED,
            nurse=nurse,
        )

        self.client.force_login(admin_user)
        response = self.client.get(reverse("dashboard-admin"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Recent Appointments")
        self.assertContains(response, nurse_user.get_full_name() or nurse_user.email)


@override_settings(SECURE_SSL_REDIRECT=False)
class FamilyMemberFlowTests(APITestCase):
    def setUp(self):
        self.end_user = CustomUser.objects.create_user(
            username="family_member_user",
            email="family_member_user@example.com",
            password="StrongPass123!",
            role=UserRole.USER,
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

    def test_end_user_can_create_family_member_with_frontend_alias_fields(self):
        self.client.force_authenticate(user=self.end_user)

        response = self.client.post(
            reverse("family-member-list"),
            {
                "full_name": "Mary Wanjiku",
                "dateOfBirth": "1958-02-10",
                "gender": "female",
                "phoneNumber": "+254700000001",
                "location": "Nairobi",
                "bloodType": "O+",
                "knownAllergies": "Penicillin",
                "emergencyContactName": "Jane Wanjiku",
                "emergencyPhone": "+254700000002",
                "isActive": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = FamilyMember.objects.get(first_name="Mary", last_name="Wanjiku")
        self.assertEqual(created.phone, "+254700000001")
        self.assertEqual(created.city, "Nairobi")
        self.assertEqual(created.gender, "FEMALE")
        self.assertEqual(created.blood_type, "O+")
        self.assertEqual(created.known_allergies, "Penicillin")
        self.assertEqual(created.emergency_contact, "Jane Wanjiku")
        self.assertEqual(created.emergency_phone, "+254700000002")

    def test_end_user_can_create_family_member_with_legacy_minimal_payload(self):
        self.client.force_authenticate(user=self.end_user)

        response = self.client.post(
            reverse("family-member-list"),
            {
                "name": "zoe",
                "first_name": "zoe",
                "last_name": "",
                "age": 67,
                "relationship": "Sibling",
                "phone": "25412345678",
                "location": "Nyali",
                "city": "Nyali",
                "address": "Bamburi",
                "medical_conditions": "Diabetes",
                "conditions": ["Diabetes"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = FamilyMember.objects.get(first_name="zoe")
        self.assertEqual(created.last_name, "Family Member")
        self.assertEqual(created.gender, "OTHER")
        self.assertEqual(created.city, "Nyali")
        self.assertEqual(created.address, "Bamburi")
        self.assertEqual(created.phone, "25412345678")
        self.assertEqual(created.chronic_conditions, "Diabetes")

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
        self.assertEqual(payload[0]["full_name"], "Saved Person")

    def test_owner_can_retrieve_single_family_member_by_uuid_id(self):
        member = FamilyMember.objects.create(
            end_user_profile=self.end_user_profile,
            first_name="Detail",
            last_name="Member",
            date_of_birth=date(1962, 1, 1),
            gender="MALE",
        )

        self.client.force_authenticate(user=self.end_user)
        response = self.client.get(reverse("family-member-detail", kwargs={"pk": str(member.id)}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(member.id))
        self.assertEqual(response.data["full_name"], "Detail Member")

    def test_family_member_list_excludes_other_users_members(self):
        other_user = CustomUser.objects.create_user(
            username="other_family_member_user",
            email="other_family_member_user@example.com",
            password="StrongPass123!",
            role=UserRole.USER,
        )
        other_profile = EndUserProfile.objects.create(
            user=other_user,
            current_country="Kenya",
            current_city="Nairobi",
        )
        FamilyMember.objects.create(
            end_user_profile=other_profile,
            first_name="Hidden",
            last_name="Person",
            date_of_birth=date(1955, 5, 5),
            gender="FEMALE",
        )

        self.client.force_authenticate(user=self.end_user)
        response = self.client.get(reverse("family-member-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.data.get("results", response.data)
        returned_names = {item["full_name"] for item in payload}
        self.assertNotIn("Hidden Person", returned_names)

    def test_family_member_list_auto_creates_missing_profile_for_end_user(self):
        user_without_profile = CustomUser.objects.create_user(
            username="missing_profile_user",
            email="missing_profile_user@example.com",
            password="StrongPass123!",
            role=UserRole.USER,
        )
        self.assertFalse(EndUserProfile.objects.filter(user=user_without_profile).exists())

        self.client.force_authenticate(user=user_without_profile)
        response = self.client.get(reverse("family-member-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(EndUserProfile.objects.filter(user=user_without_profile).exists())
        payload = response.data.get("results", response.data)
        self.assertEqual(payload, [])


class AdminEndUserAccessTests(APITestCase):
    def setUp(self):
        self.admin_user = CustomUser.objects.create_user(
            username="admin_users_view",
            email="admin_users_view@example.com",
            password="StrongPass123!",
            role=UserRole.ADMIN,
            is_staff=True,
        )
        self.end_user = CustomUser.objects.create_user(
            username="listed_end_user",
            email="listed_end_user@example.com",
            password="StrongPass123!",
            role=UserRole.USER,
        )
        self.end_user_profile = EndUserProfile.objects.create(
            user=self.end_user,
            current_country="Kenya",
            current_city="Nairobi",
        )

    def test_admin_can_list_end_users_for_dashboard_counts(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(reverse("end-user-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.data.get("results", response.data)
        returned_ids = {item["id"] for item in payload}
        self.assertIn(str(self.end_user_profile.id), returned_ids)

        listed_profile = next((item for item in payload if item["id"] == str(self.end_user_profile.id)), None)
        self.assertIsNotNone(listed_profile)
        self.assertEqual(listed_profile["user_id"], str(self.end_user.id))

    def test_admin_can_change_role_using_end_user_profile_id(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse("admin-user-change-role", kwargs={"pk": str(self.end_user_profile.id)}),
            {"role": UserRole.NURSE},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.end_user.refresh_from_db()
        self.assertEqual(self.end_user.role, UserRole.NURSE)
        nurse_profile = HealthcareNurse.objects.get(user=self.end_user)
        self.assertEqual(nurse_profile.status, "APPROVED")
        self.assertTrue(nurse_profile.is_verified)

    def test_admin_can_change_role_using_user_id(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse("admin-user-change-role", kwargs={"pk": str(self.end_user.id)}),
            {"role": UserRole.NURSE},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.end_user.refresh_from_db()
        self.assertEqual(self.end_user.role, UserRole.NURSE)
        nurse_profile = HealthcareNurse.objects.get(user=self.end_user)
        self.assertEqual(nurse_profile.status, "APPROVED")
        self.assertTrue(nurse_profile.is_verified)

    def test_admin_can_change_role_with_uppercase_role_value(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse("admin-user-change-role", kwargs={"pk": str(self.end_user.id)}),
            {"role": "ADMIN"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.end_user.refresh_from_db()
        self.assertEqual(self.end_user.role, UserRole.ADMIN)

    def test_admin_can_change_role_with_legacy_role_value(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            reverse("admin-user-change-role", kwargs={"pk": str(self.end_user.id)}),
            {"role": "END_USER"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.end_user.refresh_from_db()
        self.assertEqual(self.end_user.role, UserRole.USER)


class NurseAvailabilitySlotFlowTests(APITestCase):
    def setUp(self):
        self.nurse_user = CustomUser.objects.create_user(
            username="slot_nurse",
            email="slot_nurse@example.com",
            password="StrongPass123!",
            role=UserRole.NURSE,
        )
        self.nurse = HealthcareNurse.objects.create(
            user=self.nurse_user,
            license_number="SLOT-NURSE-001",
            license_expiry=date.today() + timedelta(days=365),
            years_experience=3,
            status="APPROVED",
            is_active=True,
        )

        self.end_user = CustomUser.objects.create_user(
            username="slot_end_user",
            email="slot_end_user@example.com",
            password="StrongPass123!",
            role=UserRole.USER,
        )
        EndUserProfile.objects.create(user=self.end_user, current_country="USA", current_city="Boston")

    def test_nurse_can_create_and_list_own_availability_slots(self):
        self.client.force_authenticate(user=self.nurse_user)

        create_response = self.client.post(
            reverse("availability-slot-list"),
            {
                "day_of_week": 1,
                "start_time": "09:00:00",
                "end_time": "12:00:00",
                "is_available": True,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        list_response = self.client.get(reverse("availability-slot-list"))
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        payload = list_response.data.get("results", list_response.data)
        self.assertEqual(len(payload), 1)
        self.assertEqual(str(payload[0]["nurse"]), str(self.nurse.id))

    def test_nurse_can_mark_availability_via_nurse_detail_endpoint(self):
        self.client.force_authenticate(user=self.nurse_user)

        response = self.client.post(
            reverse("nurse-availability", kwargs={"pk": str(self.nurse.id)}),
            {
                "day_of_week": 2,
                "start_time": "08:00:00",
                "end_time": "11:00:00",
                "is_available": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(AvailabilitySlot.objects.filter(nurse=self.nurse).count(), 1)

    def test_nurse_cannot_mark_availability_for_other_nurse(self):
        other_user = CustomUser.objects.create_user(
            username="other_slot_nurse",
            email="other_slot_nurse@example.com",
            password="StrongPass123!",
            role=UserRole.NURSE,
        )
        other_nurse = HealthcareNurse.objects.create(
            user=other_user,
            license_number="SLOT-NURSE-002",
            license_expiry=date.today() + timedelta(days=365),
            years_experience=2,
            status="APPROVED",
            is_active=True,
        )
        self.client.force_authenticate(user=self.nurse_user)

        response = self.client.post(
            reverse("nurse-availability", kwargs={"pk": str(other_nurse.id)}),
            {
                "day_of_week": 3,
                "start_time": "10:00:00",
                "end_time": "13:00:00",
                "is_available": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_end_user_cannot_access_availability_slots(self):
        self.client.force_authenticate(user=self.end_user)
        response = self.client.get(reverse("availability-slot-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class HealthRecordPaymentReviewFlowTests(APITestCase):
    def setUp(self):
        self.admin_user = CustomUser.objects.create_user(
            username="records_admin",
            email="records_admin@example.com",
            password="StrongPass123!",
            role=UserRole.ADMIN,
            is_staff=True,
        )

        self.end_user = CustomUser.objects.create_user(
            username="records_user",
            email="records_user@example.com",
            password="StrongPass123!",
            role=UserRole.USER,
        )
        self.end_user_profile = EndUserProfile.objects.create(
            user=self.end_user,
            current_country="USA",
            current_city="Miami",
        )
        self.family_member = FamilyMember.objects.create(
            end_user_profile=self.end_user_profile,
            first_name="Jane",
            last_name="Doe",
            date_of_birth=date(1960, 1, 1),
            gender="FEMALE",
        )

        self.nurse_user = CustomUser.objects.create_user(
            username="records_nurse",
            email="records_nurse@example.com",
            password="StrongPass123!",
            role=UserRole.NURSE,
        )
        self.nurse = HealthcareNurse.objects.create(
            user=self.nurse_user,
            license_number="REC-NURSE-001",
            license_expiry=date.today() + timedelta(days=365),
            years_experience=6,
            status="APPROVED",
            is_active=True,
        )

        self.appointment = Appointment.objects.create(
            family_member=self.family_member,
            end_user_profile=self.end_user_profile,
            appointment_date=date.today() + timedelta(days=3),
            start_time=time(9, 0),
            end_time=time(11, 0),
            reason="Follow-up",
            service_type=ServiceType.WELLNESS_VISIT,
            shift_type=ShiftType.DAILY_PER_HOUR_12H,
            visit_address="CBD",
            visit_city="Nairobi",
            status=AppointmentStatus.COMPLETED,
            nurse=self.nurse,
        )

    def test_end_user_can_create_health_record_and_it_is_scoped(self):
        self.client.force_authenticate(user=self.end_user)

        create_response = self.client.post(
            reverse("health-record-list"),
            {
                "family_member": str(self.family_member.id),
                "type": "GENERAL_NOTE",
                "title": "Vitals",
                "content": "BP stable",
                "is_private": True,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        record_id = create_response.data["id"]

        list_response = self.client.get(reverse("health-record-list"))
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        payload = list_response.data.get("results", list_response.data)
        returned_ids = {item["id"] for item in payload}
        self.assertIn(record_id, returned_ids)

        other_user = CustomUser.objects.create_user(
            username="other_records_user",
            email="other_records_user@example.com",
            password="StrongPass123!",
            role=UserRole.USER,
        )
        EndUserProfile.objects.create(user=other_user, current_country="USA", current_city="LA")

        self.client.force_authenticate(user=other_user)
        other_list = self.client.get(reverse("health-record-list"))
        self.assertEqual(other_list.status_code, status.HTTP_200_OK)
        other_payload = other_list.data.get("results", other_list.data)
        self.assertEqual(other_payload, [])

    @patch("jamii_aide.views.mpesa.stk_push")
    def test_end_user_can_initiate_payment_and_stats_aggregate_completed(self, mock_stk_push):
        def fake_stk_push(payment, phone_number):
            payment.provider_reference = "ws_CO_TEST123"
            payment.save(update_fields=["provider_reference"])

        mock_stk_push.side_effect = fake_stk_push

        self.client.force_authenticate(user=self.end_user)

        payment_response = self.client.post(
            reverse("payment-list"),
            {
                "amount": "2500.00",
                "method": PaymentMethod.MPESA,
                "description": "Appointment payment",
                "appointment_ids": [str(self.appointment.id)],
                "phone_number": "0712345678",
            },
            format="json",
        )
        self.assertEqual(payment_response.status_code, status.HTTP_201_CREATED)
        checkout_request_id = payment_response.data["provider_reference"]

        stats_before = self.client.get(reverse("payment-stats"))
        self.assertEqual(stats_before.status_code, status.HTTP_200_OK)
        self.assertEqual(stats_before.data["total_spent"], 0)

        self.client.logout()
        callback_response = self.client.post(
            reverse("payment-mpesa-callback"),
            {
                "Body": {
                    "stkCallback": {
                        "CheckoutRequestID": checkout_request_id,
                        "ResultCode": 0,
                        "ResultDesc": "Success",
                        "CallbackMetadata": {
                            "Item": [
                                {"Name": "Amount", "Value": 2500},
                                {"Name": "MpesaReceiptNumber", "Value": "RCP-001"},
                            ]
                        },
                    }
                }
            },
            format="json",
        )
        self.assertEqual(callback_response.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=self.end_user)
        stats_after = self.client.get(reverse("payment-stats"))
        self.assertEqual(stats_after.status_code, status.HTTP_200_OK)
        self.assertEqual(stats_after.data["total_spent"], 2500.0)
        self.assertEqual(stats_after.data["payment_count"], 1)

    def test_end_user_can_review_completed_appointment_and_review_is_created(self):
        self.client.force_authenticate(user=self.end_user)

        create_response = self.client.post(
            reverse("review-list"),
            {
                "appointment": str(self.appointment.id),
                "rating": 5,
                "comment": "Great care",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        review = Review.objects.get(appointment=self.appointment)

        self.assertEqual(review.nurse, self.nurse)
