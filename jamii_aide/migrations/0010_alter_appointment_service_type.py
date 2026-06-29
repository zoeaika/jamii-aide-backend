from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jamii_aide", "0009_role_system_update"),
    ]

    operations = [
        migrations.AlterField(
            model_name="appointment",
            name="service_type",
            field=models.CharField(
                choices=[
                    ("WELLNESS_VISIT", "Wellness Visit"),
                    ("CARE_VISIT", "Care Visit"),
                    ("CHRONIC_CONDITION_VISIT", "Chronic Condition Visit"),
                    ("DAILY_CARE", "Daily Care"),
                    ("LIVE_IN_CARE", "Live-in Care"),
                    ("EMERGENCY_ACCOMPANIMENT", "Emergency Accompaniment"),
                ],
                max_length=40,
            ),
        ),
    ]
