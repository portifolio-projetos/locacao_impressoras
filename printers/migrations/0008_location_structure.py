from django.db import migrations, models
import django.db.models.deletion


def forwards_create_locations(apps, schema_editor):
    City = apps.get_model("printers", "City")
    Location = apps.get_model("printers", "Location")
    Sector = apps.get_model("printers", "Sector")

    for sector in Sector.objects.select_related("city").all():
        city = sector.city
        if city is None:
            continue

        location_name = (sector.legacy_location or "").strip()
        if not location_name:
            location_name = "Local nao informado"

        location, _ = Location.objects.get_or_create(
            city=city,
            name=location_name,
        )
        sector.location = location
        sector.save(update_fields=["location"])


def backwards_restore_legacy_locations(apps, schema_editor):
    Sector = apps.get_model("printers", "Sector")

    for sector in Sector.objects.select_related("location").all():
        sector.legacy_location = sector.location.name if sector.location_id else ""
        sector.save(update_fields=["legacy_location"])


class Migration(migrations.Migration):

    dependencies = [
        ("printers", "0007_printermaintenance_replacement_installed_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="Location",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                (
                    "city",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="locations",
                        to="printers.city",
                    ),
                ),
            ],
            options={
                "ordering": ["city__name", "name"],
                "unique_together": {("city", "name")},
            },
        ),
        migrations.RenameField(
            model_name="sector",
            old_name="location",
            new_name="legacy_location",
        ),
        migrations.AlterUniqueTogether(
            name="sector",
            unique_together=set(),
        ),
        migrations.AddField(
            model_name="sector",
            name="location",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sectors",
                to="printers.location",
            ),
        ),
        migrations.RunPython(
            forwards_create_locations,
            backwards_restore_legacy_locations,
        ),
        migrations.AlterField(
            model_name="sector",
            name="location",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sectors",
                to="printers.location",
            ),
        ),
        migrations.RemoveField(
            model_name="sector",
            name="legacy_location",
        ),
        migrations.AlterModelOptions(
            name="sector",
            options={"ordering": ["city__name", "location__name", "name"]},
        ),
        migrations.AlterUniqueTogether(
            name="sector",
            unique_together={("city", "location", "name")},
        ),
    ]
