from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("printers", "0002_sector_location"),
    ]

    operations = [
        migrations.CreateModel(
            name="PrinterMaintenance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("defect_description", models.TextField()),
                (
                    "maintenance_location_type",
                    models.CharField(
                        choices=[
                            ("lessor", "Loja responsável"),
                            ("third_party", "Terceirizado"),
                        ],
                        max_length=20,
                    ),
                ),
                ("maintenance_location_details", models.CharField(blank=True, max_length=120)),
                ("started_at", models.DateField()),
                ("finished_at", models.DateField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("in_progress", "Em manutenção"),
                            ("completed", "Disponível"),
                        ],
                        default="in_progress",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "origin_city",
                    models.ForeignKey(
                        editable=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="maintenance_origins",
                        to="printers.city",
                    ),
                ),
                (
                    "origin_sector",
                    models.ForeignKey(
                        editable=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="maintenance_origins",
                        to="printers.sector",
                    ),
                ),
                (
                    "printer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="maintenance_records",
                        to="printers.printer",
                    ),
                ),
            ],
            options={
                "verbose_name": "Manutenção de impressora",
                "verbose_name_plural": "Manutenções de impressoras",
                "ordering": ["-started_at", "-created_at"],
            },
        ),
    ]
