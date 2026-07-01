from django.db import migrations, models


def approve_pending_nurses_forward(apps, schema_editor):
    HealthcareNurse = apps.get_model("jamii_aide", "HealthcareNurse")
    HealthcareNurse.objects.filter(status="PENDING").update(
        status="APPROVED",
        is_verified=True,
        is_active=True,
    )


def approve_pending_nurses_backward(apps, schema_editor):
    HealthcareNurse = apps.get_model("jamii_aide", "HealthcareNurse")
    HealthcareNurse.objects.filter(status="APPROVED", is_verified=True).update(
        status="PENDING",
        is_verified=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("jamii_aide", "0010_alter_appointment_service_type"),
    ]

    operations = [
        migrations.RunPython(approve_pending_nurses_forward, approve_pending_nurses_backward),
        migrations.AlterField(
            model_name="healthcarenurse",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending Review"),
                    ("APPROVED", "Approved"),
                    ("SUSPENDED", "Suspended"),
                ],
                default="APPROVED",
                max_length=20,
            ),
        ),
    ]
