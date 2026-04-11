from django.db import migrations, models


def populate_base_catalogs(apps, schema_editor):
    Sector = apps.get_model("printers", "Sector")
    Location = apps.get_model("printers", "Location")
    SectorCatalog = apps.get_model("printers", "SectorCatalog")
    LocationCatalog = apps.get_model("printers", "LocationCatalog")

    seen_sectors = set()
    for sector in Sector.objects.order_by("name").values_list("name", flat=True):
        normalized = sector.strip().lower()
        if normalized and normalized not in seen_sectors:
            SectorCatalog.objects.get_or_create(name=sector.strip())
            seen_sectors.add(normalized)

    seen_locations = set()
    for location in Location.objects.order_by("name").values_list("name", flat=True):
        normalized = location.strip().lower()
        if normalized and normalized not in seen_locations:
            LocationCatalog.objects.get_or_create(name=location.strip())
            seen_locations.add(normalized)


class Migration(migrations.Migration):

    dependencies = [
        ("printers", "0008_location_structure"),
    ]

    operations = [
        migrations.CreateModel(
            name="LocationCatalog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
            ],
            options={
                "verbose_name": "Local base",
                "verbose_name_plural": "Locais base",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="SectorCatalog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80, unique=True)),
            ],
            options={
                "verbose_name": "Setor base",
                "verbose_name_plural": "Setores base",
                "ordering": ["name"],
            },
        ),
        migrations.RunPython(populate_base_catalogs, migrations.RunPython.noop),
    ]
