from django.db import migrations


def backfill_installation_history(apps, schema_editor):
    Printer = apps.get_model("printers", "Printer")
    PrinterInstallationHistory = apps.get_model("printers", "PrinterInstallationHistory")

    for printer in Printer.objects.filter(city__isnull=False, sector__isnull=False).iterator():
        has_open_history = PrinterInstallationHistory.objects.filter(
            printer=printer,
            removed_at__isnull=True,
        ).exists()
        if has_open_history:
            continue

        PrinterInstallationHistory.objects.create(
            printer=printer,
            city=printer.city,
            sector=printer.sector,
            location_name=printer.location or printer.sector.location.name,
            installed_at=printer.installed_at,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("printers", "0014_printermaintenance_solution_description_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_installation_history, migrations.RunPython.noop),
    ]
