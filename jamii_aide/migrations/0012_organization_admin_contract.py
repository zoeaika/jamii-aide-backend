from django.db import migrations, models
import django.db.models.deletion
import uuid


def migrate_roles_forward(apps, schema_editor):
    CustomUser = apps.get_model('jamii_aide', 'CustomUser')
    CustomUser.objects.filter(role='organizationAdmin').update(role='organization_admin')


def migrate_roles_backward(apps, schema_editor):
    CustomUser = apps.get_model('jamii_aide', 'CustomUser')
    CustomUser.objects.filter(role='organization_admin').update(role='organizationAdmin')


class Migration(migrations.Migration):

    dependencies = [
        ('jamii_aide', '0011_backfill_pending_nurses'),
    ]

    operations = [
        migrations.CreateModel(
            name='Organization',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255, unique=True)),
                ('description', models.TextField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'organizations',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='OrganizationAdministrator',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='administrators', to='jamii_aide.organization')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='organization_admin_profile', to='jamii_aide.customuser')),
            ],
            options={
                'db_table': 'organization_administrators',
                'verbose_name': 'Organization Administrator',
                'verbose_name_plural': 'Organization Administrators',
            },
        ),
        migrations.AddField(
            model_name='healthcarenurse',
            name='organization',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='nurses', to='jamii_aide.organization'),
        ),
        migrations.RunPython(migrate_roles_forward, migrate_roles_backward),
        migrations.AlterField(
            model_name='customuser',
            name='role',
            field=models.CharField(
                choices=[
                    ('user', 'User'),
                    ('nurse', 'Nurse'),
                    ('admin', 'Admin'),
                    ('organization_admin', 'Organization Admin'),
                ],
                default='user',
                max_length=20,
            ),
        ),
        migrations.AddIndex(
            model_name='organization',
            index=models.Index(fields=['name'], name='organizatio_name_67a572_idx'),
        ),
        migrations.AddIndex(
            model_name='organization',
            index=models.Index(fields=['is_active'], name='organizatio_is_acti_ec5684_idx'),
        ),
        migrations.AddIndex(
            model_name='organizationadministrator',
            index=models.Index(fields=['organization'], name='organizatio_organiz_9ca8eb_idx'),
        ),
        migrations.AddIndex(
            model_name='healthcarenurse',
            index=models.Index(fields=['organization'], name='healthcare_n_organiz_88bf59_idx'),
        ),
    ]
