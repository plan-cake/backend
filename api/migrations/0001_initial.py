# Generated by Django 5.2 on 2025-06-05 01:10

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="UserAccount",
            fields=[
                (
                    "user_account_id",
                    models.AutoField(primary_key=True, serialize=False),
                ),
                ("email", models.EmailField(max_length=254, null=True, unique=True)),
                ("password_hash", models.CharField(max_length=255, null=True)),
                ("display_name", models.CharField(max_length=25, null=True)),
                ("is_internal", models.BooleanField(default=False)),
                ("is_guest", models.BooleanField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["email"], name="api_useracc_email_77cb26_idx")
                ],
            },
        ),
        migrations.CreateModel(
            name="UserLogin",
            fields=[
                (
                    "pk",
                    models.CompositePrimaryKey(
                        "user_account",
                        "login_time",
                        blank=True,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("login_time", models.DateTimeField(auto_now_add=True)),
                (
                    "user_account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="logins",
                        to="api.useraccount",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="UserSession",
            fields=[
                (
                    "session_token",
                    models.CharField(max_length=255, primary_key=True, serialize=False),
                ),
                ("last_used", models.DateTimeField(auto_now=True)),
                (
                    "user_account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="session_tokens",
                        to="api.useraccount",
                    ),
                ),
            ],
        ),
    ]
