"""
Test suite to verify USER role standardization
- Register always creates USER role
- Google auth always creates USER role  
- /me endpoint returns USER role
- Admin role change validates USER, NURSE, ADMIN, and ORGANIZATION_ADMIN roles
"""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch

from jamii_aide.models import CustomUser, UserRole, EndUserProfile, HealthcareNurse, NurseStatus, Organization
from django.utils import timezone


class RegisterRoleStandardizationTests(APITestCase):
    """Verify register endpoint always creates USER role"""

    def test_register_creates_user_role_when_no_role_provided(self):
        """Public signup without role parameter creates USER"""
        response = self.client.post(
            reverse("register"),
            {
                "email": "norole@example.com",
                "password": "StrongPass123!",
                "first_name": "No",
                "last_name": "Role",
                "current_country": "Kenya",
                "current_city": "Nairobi",
            },
            format="json",
        )
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user"]["role"], "user")
        
        created_user = CustomUser.objects.get(email="norole@example.com")
        self.assertEqual(created_user.role, UserRole.USER)
        self.assertTrue(EndUserProfile.objects.filter(user=created_user).exists())

    def test_register_rejects_role_parameter_and_creates_user(self):
        """Public signup ignores any role parameter and creates USER"""
        # Try to register as ADMIN
        response = self.client.post(
            reverse("register"),
            {
                "email": "forced_admin@example.com",
                "password": "StrongPass123!",
                "first_name": "Forced",
                "last_name": "Admin",
                "role": UserRole.ADMIN,
                "current_country": "Kenya",
                "current_city": "Nairobi",
            },
            format="json",
        )
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user"]["role"], "user")
        
        created_user = CustomUser.objects.get(email="forced_admin@example.com")
        self.assertEqual(created_user.role, UserRole.USER)
        self.assertFalse(created_user.is_staff)
        
        # Try to register as NURSE
        response2 = self.client.post(
            reverse("register"),
            {
                "email": "forced_nurse@example.com",
                "password": "StrongPass123!",
                "first_name": "Forced",
                "last_name": "Nurse",
                "role": UserRole.NURSE,
                "current_country": "Kenya",
                "current_city": "Nairobi",
            },
            format="json",
        )
        
        self.assertEqual(response2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response2.data["user"]["role"], "user")
        
        created_user2 = CustomUser.objects.get(email="forced_nurse@example.com")
        self.assertEqual(created_user2.role, UserRole.USER)

    def test_register_only_creates_enduser_profile_for_user_role(self):
        """Verify that register creates EndUserProfile for USER role users"""
        response = self.client.post(
            reverse("register"),
            {
                "email": "profile@example.com",
                "password": "StrongPass123!",
                "first_name": "Profile",
                "last_name": "User",
                "current_country": "USA",
                "current_city": "New York",
            },
            format="json",
        )
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        user = CustomUser.objects.get(email="profile@example.com")
        profile = EndUserProfile.objects.get(user=user)
        self.assertEqual(profile.current_country, "USA")
        self.assertEqual(profile.current_city, "New York")


class GoogleAuthRoleStandardizationTests(APITestCase):
    """Verify google auth endpoint always creates USER role"""

    @patch("jamii_aide.google_serializers.id_token.verify_oauth2_token")
    def test_google_auth_creates_user_role_for_new_user(self, mock_verify):
        """Google auth creates new user with USER role"""
        mock_verify.return_value = {
            "iss": "https://accounts.google.com",
            "sub": "google-user-new-123",
            "email": "newgoogleuser@example.com",
            "email_verified": True,
            "given_name": "Google",
            "family_name": "User",
        }
        
        response = self.client.post(
            reverse("google-login"),
            {"credential": "valid-google-token"},
            format="json",
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["role"], "user")
        
        user = CustomUser.objects.get(email="newgoogleuser@example.com")
        self.assertEqual(user.role, UserRole.USER)
        self.assertTrue(user.is_verified)
        self.assertTrue(EndUserProfile.objects.filter(user=user).exists())

    @patch("jamii_aide.google_serializers.id_token.verify_oauth2_token")
    def test_google_auth_preserves_user_role_for_existing_user(self, mock_verify):
        """Google auth doesn't change role of existing USER"""
        existing_user = CustomUser.objects.create_user(
            username="google_existing",
            email="googleexisting@example.com",
            password="OldPass123!",
            role=UserRole.USER,
        )
        EndUserProfile.objects.create(user=existing_user, current_country="Kenya")
        
        mock_verify.return_value = {
            "iss": "https://accounts.google.com",
            "sub": "google-user-existing-456",
            "email": "googleexisting@example.com",
            "email_verified": True,
            "given_name": "Updated",
            "family_name": "Name",
        }
        
        response = self.client.post(
            reverse("google-login"),
            {"credential": "existing-google-token"},
            format="json",
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["role"], "user")
        
        existing_user.refresh_from_db()
        self.assertEqual(existing_user.role, UserRole.USER)


class MeEndpointRoleTests(APITestCase):
    """Verify /me endpoint returns correct USER role"""

    def test_me_endpoint_returns_user_role(self):
        """GET /api/auth/me/ returns USER role for authenticated user"""
        user = CustomUser.objects.create_user(
            username="me_user",
            email="meuser@example.com",
            password="StrongPass123!",
            role=UserRole.USER,
        )
        
        self.client.force_authenticate(user=user)
        response = self.client.get(reverse("current-user"))
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], "user")
        self.assertEqual(response.data["email"], "meuser@example.com")

    def test_me_endpoint_returns_nurse_role_when_changed_to_nurse(self):
        """GET /api/auth/me/ returns NURSE role after admin role change"""
        admin = CustomUser.objects.create_user(
            username="admin_user",
            email="admin@example.com",
            password="AdminPass123!",
            role=UserRole.ADMIN,
            is_staff=True,
        )
        
        user = CustomUser.objects.create_user(
            username="nurse_candidate",
            email="nursecand@example.com",
            password="CandPass123!",
            role=UserRole.USER,
        )
        EndUserProfile.objects.create(user=user, current_country="Kenya")
        
        # Admin changes role to NURSE
        self.client.force_authenticate(user=admin)
        response = self.client.post(
            reverse("admin-user-change-role", kwargs={"pk": user.id}),
            {"role": UserRole.NURSE},
            format="json",
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], "nurse")
        
        # Verify /me returns NURSE by refreshing from database
        user.refresh_from_db()
        self.client.force_authenticate(user=user)
        me_response = self.client.get(reverse("current-user"))
        
        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        self.assertEqual(me_response.data["role"], "nurse")


class AdminRoleChangeValidationTests(APITestCase):
    """Verify admin role change validates USER, NURSE, ADMIN, ORGANIZATION_ADMIN."""

    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="AdminPass123!",
            role=UserRole.ADMIN,
            is_staff=True,
        )
        
        self.target_user = CustomUser.objects.create_user(
            username="target",
            email="target@example.com",
            password="TargetPass123!",
            role=UserRole.USER,
        )
        EndUserProfile.objects.create(user=self.target_user, current_country="Kenya")

    def test_admin_can_change_user_to_nurse(self):
        """Admin can change USER role to NURSE"""
        self.client.force_authenticate(user=self.admin)
        
        response = self.client.post(
            reverse("admin-user-change-role", kwargs={"pk": self.target_user.id}),
            {"role": UserRole.NURSE},
            format="json",
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], "nurse")
        
        self.target_user.refresh_from_db()
        self.assertEqual(self.target_user.role, UserRole.NURSE)
        self.assertTrue(HealthcareNurse.objects.filter(user=self.target_user).exists())

    def test_admin_can_change_user_to_admin(self):
        """Admin can change USER role to ADMIN"""
        self.client.force_authenticate(user=self.admin)
        
        response = self.client.post(
            reverse("admin-user-change-role", kwargs={"pk": self.target_user.id}),
            {"role": UserRole.ADMIN},
            format="json",
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], "admin")
        
        self.target_user.refresh_from_db()
        self.assertEqual(self.target_user.role, UserRole.ADMIN)

    def test_admin_can_change_nurse_back_to_user(self):
        """Admin can change NURSE role back to USER"""
        nurse = CustomUser.objects.create_user(
            username="nurse",
            email="nurse@example.com",
            password="NursePass123!",
            role=UserRole.NURSE,
        )
        HealthcareNurse.objects.create(
            user=nurse,
            license_number="NURSE-001",
            license_expiry=timezone.now().date(),
            years_experience=5,
            status=NurseStatus.APPROVED,
        )
        
        self.client.force_authenticate(user=self.admin)
        
        response = self.client.post(
            reverse("admin-user-change-role", kwargs={"pk": nurse.id}),
            {"role": UserRole.USER},
            format="json",
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], "user")
        
        nurse.refresh_from_db()
        self.assertEqual(nurse.role, UserRole.USER)
        self.assertTrue(EndUserProfile.objects.filter(user=nurse).exists())

    def test_admin_rejects_invalid_role(self):
        """Admin cannot change to invalid role"""
        self.client.force_authenticate(user=self.admin)
        
        response = self.client.post(
            reverse("admin-user-change-role", kwargs={"pk": self.target_user.id}),
            {"role": "INVALID_ROLE"},
            format="json",
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("role", response.data)

    def test_non_admin_cannot_change_roles(self):
        """Non-admin cannot change user roles"""
        regular_user = CustomUser.objects.create_user(
            username="regular",
            email="regular@example.com",
            password="RegularPass123!",
            role=UserRole.USER,
        )
        
        self.client.force_authenticate(user=regular_user)
        
        response = self.client.post(
            reverse("admin-user-change-role", kwargs={"pk": self.target_user.id}),
            {"role": UserRole.NURSE},
            format="json",
        )
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_role_change_validates_against_supported_roles(self):
        """Role change accepts supported role constants."""
        self.client.force_authenticate(user=self.admin)
        
        # Test each valid role
        for valid_role in [UserRole.USER, UserRole.NURSE, UserRole.ADMIN]:
            response = self.client.post(
                reverse("admin-user-change-role", kwargs={"pk": self.target_user.id}),
                {"role": valid_role},
                format="json",
            )
            
            self.assertEqual(response.status_code, status.HTTP_200_OK, 
                           f"Failed to set role to {valid_role}")
            self.assertEqual(response.data["role"], valid_role)

        # organization_admin requires organization_id
        organization = Organization.objects.create(name="Acme Health", code="ACME")
        org_response = self.client.post(
            reverse("admin-user-change-role", kwargs={"pk": self.target_user.id}),
            {"role": UserRole.ORGANIZATION_ADMIN, "organization_id": str(organization.id)},
            format="json",
        )
        self.assertEqual(org_response.status_code, status.HTTP_200_OK)
        self.assertEqual(org_response.data["role"], UserRole.ORGANIZATION_ADMIN)
