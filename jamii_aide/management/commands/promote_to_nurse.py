from django.core.management.base import BaseCommand
from django.utils import timezone
import datetime
from jamii_aide.models import CustomUser, HealthcareNurse, UserRole

class Command(BaseCommand):
    help = 'Promote an existing user to an approved Healthcare Nurse'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str, help='The email of the user to promote')
        parser.add_argument('--license', type=str, help='Optional specific license number', default='')

    def handle(self, *args, **kwargs):
        email = kwargs['email']
        license_number = kwargs['license']

        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'User with email {email} does not exist.'))
            return

        # 1. Update the User Role
        if user.role != UserRole.NURSE:
            user.role = UserRole.NURSE
            user.save(update_fields=['role'])
            self.stdout.write(self.style.SUCCESS(f'Changed role to NURSE for {email}.'))
        else:
            self.stdout.write(self.style.WARNING(f'User {email} is already a nurse.'))

        # 2. Create the Nurse Profile
        if not license_number:
            license_number = f'TEMP-{user.id.hex[:8]}'

        nurse, created = HealthcareNurse.objects.get_or_create(
            user=user,
            defaults={
                'license_number': license_number,
                'license_expiry': timezone.now().date() + datetime.timedelta(days=365),
                'years_experience': 0,
                'status': 'APPROVED',
                'is_active': True,
                'is_verified': True,
                'professional_type': 'CAREGIVER_NURSE'
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f'Created approved HealthcareNurse profile for {email}.'))
        else:
            self.stdout.write(self.style.WARNING(f'HealthcareNurse profile already existed for {email}.'))