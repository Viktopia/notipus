# Generated manually to allow NULL shop_domain values

from django.db import migrations, models


def convert_empty_to_null(apps, schema_editor):
    """Convert empty shop_domain strings to NULL.

    This allows the unique constraint to work properly, as PostgreSQL
    allows multiple NULL values but not multiple empty strings.
    """
    Organization = apps.get_model("core", "Organization")
    Organization.objects.filter(shop_domain="").update(shop_domain=None)


def convert_null_to_empty(apps, schema_editor):
    """Reverse migration: convert NULL back to empty string."""
    Organization = apps.get_model("core", "Organization")
    Organization.objects.filter(shop_domain__isnull=True).update(shop_domain="")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_add_free_plan"),
    ]

    operations = [
        # First, alter the field to allow NULL
        migrations.AlterField(
            model_name="organization",
            name="shop_domain",
            field=models.CharField(blank=True, max_length=255, null=True, unique=True),
        ),
        # Then convert existing empty strings to NULL
        migrations.RunPython(convert_empty_to_null, convert_null_to_empty),
    ]
