from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("printers", "0003_printermaintenance"),
    ]

    operations = [
        migrations.AlterField(
            model_name="printer",
            name="city",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="printers",
                to="printers.city",
            ),
        ),
        migrations.AlterField(
            model_name="printer",
            name="location",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AlterField(
            model_name="printer",
            name="sector",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="printers",
                to="printers.sector",
            ),
        ),
    ]
