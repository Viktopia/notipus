# Generated by Django 5.1.6 on 2025-04-15 16:26

import datetime
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_usagelimit_organization_billing_cycle_anchor_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="shop_domain",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AlterField(
            model_name="organization",
            name="trial_end_date",
            field=models.DateTimeField(
                default=datetime.datetime(
                    2025, 4, 29, 16, 26, 57, 492214, tzinfo=datetime.timezone.utc
                )
            ),
        ),
        migrations.CreateModel(
            name="Integration",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "integration_type",
                    models.CharField(
                        choices=[
                            ("stripe", "Stripe Payments"),
                            ("shopify", "Shopify Store"),
                        ],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                ("auth_data", models.JSONField(default=dict)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="integrations",
                        to="core.organization",
                    ),
                ),
            ],
        ),
    ]
