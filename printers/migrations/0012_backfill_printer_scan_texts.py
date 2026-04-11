from django.db import migrations


def backfill_printer_scan_texts(apps, schema_editor):
    Printer = apps.get_model("printers", "Printer")

    for printer in Printer.objects.all().iterator():
        updated_fields = []

        if printer.serial_number and not printer.serial_number_scan_text:
            printer.serial_number_scan_text = printer.serial_number
            updated_fields.append("serial_number_scan_text")

        if printer.barcode and not printer.barcode_scan_text:
            printer.barcode_scan_text = printer.barcode
            updated_fields.append("barcode_scan_text")

        if updated_fields:
            printer.save(update_fields=updated_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("printers", "0011_alter_printermaintenance_options_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_printer_scan_texts, migrations.RunPython.noop),
    ]
