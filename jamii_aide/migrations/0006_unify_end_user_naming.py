from django.db import migrations, models


def normalize_user_roles(apps, schema_editor):
    CustomUser = apps.get_model("jamii_aide", "CustomUser")
    CustomUser.objects.filter(role="DIASPORA_USER").update(role="END_USER")


class Migration(migrations.Migration):

    dependencies = [
        ("jamii_aide", "0005_alter_customuser_role"),
    ]

    operations = [
        migrations.RunPython(normalize_user_roles, migrations.RunPython.noop),
        migrations.RenameModel(
            old_name="DasporaUser",
            new_name="EndUserProfile",
        ),
        migrations.AlterModelOptions(
            name="enduserprofile",
            options={
                "verbose_name": "End User Profile",
                "verbose_name_plural": "End User Profiles",
            },
        ),
        migrations.AlterModelTable(
            name="enduserprofile",
            table="end_user_profiles",
        ),
        migrations.AlterField(
            model_name="customuser",
            name="role",
            field=models.CharField(
                choices=[
                    ("END_USER", "End User"),
                    ("HEALTHCARE_NURSE", "Healthcare Nurse"),
                    ("ADMIN", "Administrator"),
                ],
                default="END_USER",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="enduserprofile",
            name="user",
            field=models.OneToOneField(
                on_delete=models.deletion.CASCADE,
                related_name="end_user_profile",
                to="jamii_aide.customuser",
            ),
        ),
        migrations.RenameField(
            model_name="familymember",
            old_name="diaspora_user",
            new_name="end_user_profile",
        ),
        migrations.RenameField(
            model_name="appointment",
            old_name="diaspora_user",
            new_name="end_user_profile",
        ),
        migrations.RenameField(
            model_name="healthrecord",
            old_name="diaspora_user",
            new_name="end_user_profile",
        ),
        migrations.RenameField(
            model_name="prescription",
            old_name="diaspora_user",
            new_name="end_user_profile",
        ),
        migrations.RenameField(
            model_name="payment",
            old_name="diaspora_user",
            new_name="end_user_profile",
        ),
        migrations.RenameField(
            model_name="review",
            old_name="diaspora_user",
            new_name="end_user_profile",
        ),
    ]
