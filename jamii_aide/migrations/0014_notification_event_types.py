from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jamii_aide', '0013_healthcarenurse_is_accepting_requests'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='event_type',
            field=models.CharField(
                max_length=30,
                choices=[
                    ('REQUEST_SUBMITTED', 'Request Submitted'),
                    ('NURSE_SUGGESTED', 'Nurse Suggested'),
                    ('REQUEST_APPROVED', 'Request Approved'),
                    ('REQUEST_REJECTED', 'Request Rejected'),
                    ('NURSE_VERIFIED', 'Nurse Verified'),
                    ('NURSE_REJECTED', 'Nurse Rejected'),
                    ('ORGANIZATION_VERIFIED', 'Organization Verified'),
                    ('ORGANIZATION_REJECTED', 'Organization Rejected'),
                    ('ROLE_CHANGED', 'Role Changed'),
                ],
            ),
        ),
    ]
