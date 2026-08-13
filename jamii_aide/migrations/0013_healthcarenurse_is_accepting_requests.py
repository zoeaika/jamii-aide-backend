from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jamii_aide', '0012_organization_admin_contract'),
    ]

    operations = [
        migrations.AddField(
            model_name='healthcarenurse',
            name='is_accepting_requests',
            field=models.BooleanField(default=True),
        ),
    ]
