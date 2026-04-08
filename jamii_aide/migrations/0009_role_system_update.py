from django.db import migrations, models


def migrate_roles_forward(apps, schema_editor):
    CustomUser = apps.get_model("jamii_aide", "CustomUser")
    CustomUser.objects.filter(role="END_USER").update(role="user")
    CustomUser.objects.filter(role="HEALTHCARE_NURSE").update(role="nurse")
    CustomUser.objects.filter(role="ADMIN").update(role="admin")


def migrate_roles_backward(apps, schema_editor):
    CustomUser = apps.get_model("jamii_aide", "CustomUser")
    CustomUser.objects.filter(role="user").update(role="END_USER")
    CustomUser.objects.filter(role="nurse").update(role="HEALTHCARE_NURSE")
    CustomUser.objects.filter(role="admin").update(role="ADMIN")


class Migration(migrations.Migration):

    dependencies = [
        ("jamii_aide", "0008_familymember_address_familymember_city"),
    ]

    operations = [
        migrations.RunPython(migrate_roles_forward, migrate_roles_backward),
        migrations.AlterField(
            model_name="customuser",
            name="role",
            field=models.CharField(
                choices=[("user", "User"), ("nurse", "Nurse"), ("admin", "Admin")],
                default="user",
                max_length=20,
            ),
        ),
    ]
