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
        migrations.RemoveIndex(
            model_name="appointment",
            name="appointment_diaspor_fc9994_idx",
        ),
        migrations.RemoveIndex(
            model_name="familymember",
            name="family_memb_diaspor_5b6285_idx",
        ),
        migrations.RemoveIndex(
            model_name="healthrecord",
            name="health_reco_diaspor_88f4f2_idx",
        ),
        migrations.RemoveIndex(
            model_name="payment",
            name="payments_diaspor_4ee1ae_idx",
        ),
        migrations.RemoveIndex(
            model_name="prescription",
            name="prescriptio_diaspor_04ca77_idx",
        ),
        migrations.RenameModel(
            old_name="DasporaUser",
            new_name="EndUserProfile",
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
        migrations.AddIndex(
            model_name="appointment",
            index=models.Index(fields=["end_user_profile"], name="appointment_end_use_a92f86_idx"),
        ),
        migrations.AddIndex(
            model_name="familymember",
            index=models.Index(fields=["end_user_profile"], name="family_memb_end_use_3c9703_idx"),
        ),
        migrations.AddIndex(
            model_name="healthrecord",
            index=models.Index(fields=["end_user_profile"], name="health_reco_end_use_31a0b5_idx"),
        ),
        migrations.AddIndex(
            model_name="payment",
            index=models.Index(fields=["end_user_profile"], name="payments_end_use_a3a40a_idx"),
        ),
        migrations.AddIndex(
            model_name="prescription",
            index=models.Index(fields=["end_user_profile"], name="prescriptio_end_use_d014ca_idx"),
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
    ]
