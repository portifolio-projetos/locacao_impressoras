from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class City(models.Model):
    name = models.CharField(max_length=100, unique=True)
    state = models.CharField(max_length=2, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name}-{self.state}" if self.state else self.name


class Location(models.Model):
    name = models.CharField(max_length=120)
    city = models.ForeignKey(City, related_name="locations", on_delete=models.CASCADE)

    class Meta:
        ordering = ["city__name", "name"]
        unique_together = ("city", "name")

    def __str__(self) -> str:
        return f"{self.name} ({self.city})"


class SectorCatalog(models.Model):
    name = models.CharField(max_length=80, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Setor base"
        verbose_name_plural = "Setores base"

    def __str__(self) -> str:
        return self.name


class LocationCatalog(models.Model):
    name = models.CharField(max_length=120, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Local base"
        verbose_name_plural = "Locais base"

    def __str__(self) -> str:
        return self.name


class Sector(models.Model):
    name = models.CharField(max_length=80)
    city = models.ForeignKey(City, related_name="sectors", on_delete=models.CASCADE)
    location = models.ForeignKey(
        Location,
        related_name="sectors",
        on_delete=models.PROTECT,
    )

    class Meta:
        unique_together = ("city", "location", "name")
        ordering = ["city__name", "location__name", "name"]

    def clean(self) -> None:
        if self.location_id and self.city_id and self.location.city_id != self.city_id:
            raise ValidationError("O local selecionado precisa pertencer a cidade informada.")
        super().clean()

    def __str__(self) -> str:
        return f"{self.location.name} - {self.name} ({self.city})"


class PrinterModel(models.Model):
    name = models.CharField(max_length=120, unique=True)
    manufacturer = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name if not self.manufacturer else f"{self.manufacturer} {self.name}"


class MaintenanceStatus(models.Model):
    class Flow(models.TextChoices):
        IN_PROGRESS = "in_progress", "Em manutencao"
        COMPLETED = "completed", "Disponivel"

    name = models.CharField(max_length=80, unique=True)
    flow = models.CharField(max_length=20, choices=Flow.choices, default=Flow.IN_PROGRESS)

    class Meta:
        ordering = ["name"]
        verbose_name = "Status de manutencao"
        verbose_name_plural = "Status de manutencao"

    def __str__(self) -> str:
        return self.name


class MaintenanceProvider(models.Model):
    supplier_name = models.CharField(max_length=120, unique=True)
    address = models.CharField(max_length=180)
    phone = models.CharField(max_length=30, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    neighborhood = models.CharField(max_length=100, blank=True)
    contact_name = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["supplier_name"]
        verbose_name = "Local de manutencao"
        verbose_name_plural = "Locais de manutencao"

    def __str__(self) -> str:
        return self.supplier_name


class Printer(models.Model):
    serial_number = models.CharField(max_length=60, unique=True, blank=True, null=True)
    serial_number_scan_text = models.CharField(max_length=255, blank=True)
    patrimony_number = models.CharField(max_length=60, blank=True)
    barcode = models.CharField(max_length=80, blank=True)
    barcode_scan_text = models.CharField(max_length=255, blank=True)
    model = models.ForeignKey(PrinterModel, related_name="printers", on_delete=models.PROTECT)
    city = models.ForeignKey(
        City,
        related_name="printers",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
    )
    sector = models.ForeignKey(
        Sector,
        related_name="printers",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
    )
    location = models.CharField(max_length=120, blank=True)
    installed_at = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["serial_number"]

    def clean(self) -> None:
        if bool(self.city_id) ^ bool(self.sector_id):
            raise ValidationError("Cidade e setor devem ser informados juntos.")

        if self.installed_at and self.installed_at > timezone.localdate():
            raise ValidationError("A data de instalacao nao pode ser maior que a data de hoje.")

        if self.sector and self.city and self.sector.city_id != self.city_id:
            raise ValidationError("O setor selecionado nao pertence a cidade informada.")

        if self.sector:
            if self.sector.location.city_id != self.city_id:
                raise ValidationError("O local do setor selecionado nao pertence a cidade informada.")
            self.location = self.sector.location.name
        else:
            self.location = ""

        if not self.serial_number_scan_text and self.serial_number:
            self.serial_number_scan_text = self.serial_number

        if not self.barcode_scan_text and self.barcode:
            self.barcode_scan_text = self.barcode

    def __str__(self) -> str:
        return f"{self.serial_number} - {self.model}"


class PrinterInstallationHistory(models.Model):
    printer = models.ForeignKey(
        Printer,
        related_name="installation_history",
        on_delete=models.CASCADE,
    )
    city = models.ForeignKey(
        City,
        related_name="printer_installation_history",
        on_delete=models.PROTECT,
    )
    sector = models.ForeignKey(
        Sector,
        related_name="printer_installation_history",
        on_delete=models.PROTECT,
    )
    location_name = models.CharField(max_length=120)
    installed_at = models.DateField(blank=True, null=True)
    removed_at = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-installed_at", "-created_at"]
        verbose_name = "Historico de instalacao"
        verbose_name_plural = "Historicos de instalacao"

    def __str__(self) -> str:
        return f"{self.printer} - {self.city} / {self.location_name}"


class PrinterMaintenance(models.Model):
    class MaintenanceLocation(models.TextChoices):
        LESSOR = "lessor", "Loja responsavel"
        THIRD_PARTY = "third_party", "Terceirizado"

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "Em manutencao"
        COMPLETED = "completed", "Disponivel"

    printer = models.ForeignKey(
        Printer,
        related_name="maintenance_records",
        on_delete=models.PROTECT,
    )
    origin_city = models.ForeignKey(
        City,
        related_name="maintenance_origins",
        on_delete=models.PROTECT,
        editable=False,
    )
    origin_sector = models.ForeignKey(
        Sector,
        related_name="maintenance_origins",
        on_delete=models.PROTECT,
        editable=False,
    )
    defect_description = models.TextField()
    solution_description = models.TextField(blank=True)
    status_catalog = models.ForeignKey(
        MaintenanceStatus,
        related_name="maintenance_records",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
    )
    maintenance_provider = models.ForeignKey(
        MaintenanceProvider,
        related_name="maintenance_records",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
    )
    maintenance_location_type = models.CharField(
        max_length=20,
        choices=MaintenanceLocation.choices,
    )
    maintenance_location_details = models.CharField(max_length=120, blank=True)
    started_at = models.DateField()
    finished_at = models.DateField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
    )
    replacement_installed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-started_at", "-created_at"]
        verbose_name = "Manutencao de impressora"
        verbose_name_plural = "Manutencoes de impressoras"

    def clean(self) -> None:
        origin_city = self.origin_city or (self.printer.city if self.printer_id else None)
        origin_sector = self.origin_sector or (self.printer.sector if self.printer_id else None)

        if origin_sector and origin_city and origin_sector.city_id != origin_city.id:
            raise ValidationError("O setor de origem precisa pertencer a cidade de origem.")

        if self.finished_at and self.started_at and self.finished_at < self.started_at:
            raise ValidationError("A data de saida nao pode ser anterior a data de entrada.")

        if self.started_at and self.started_at > timezone.localdate():
            raise ValidationError("A data de entrada nao pode ser maior que a data de hoje.")

        if self.finished_at and self.finished_at > timezone.localdate():
            raise ValidationError("A data de saida nao pode ser maior que a data de hoje.")

        if self.current_status_flow == self.Status.COMPLETED and not self.finished_at:
            raise ValidationError("Informe a data de saida para marcar a manutencao como concluida.")

        if self.current_status_flow == self.Status.COMPLETED and not self.solution_description:
            raise ValidationError("Informe a solucao aplicada para finalizar a manutencao.")

        if self.current_status_flow == self.Status.IN_PROGRESS and self.finished_at:
            raise ValidationError(
                "Remova a data de saida ou altere o status para disponivel antes de salvar."
            )

        super().clean()

    def save(self, *args, **kwargs):
        if not self.origin_city_id and self.printer_id:
            self.origin_city = self.printer.city
        if not self.origin_sector_id and self.printer_id:
            self.origin_sector = self.printer.sector
        if self.status_catalog_id:
            self.status = self.status_catalog.flow
        super().save(*args, **kwargs)

    @property
    def current_status_flow(self) -> str:
        if self.status_catalog_id:
            return self.status_catalog.flow
        return self.status

    @property
    def status_display_name(self) -> str:
        if self.status_catalog_id:
            return self.status_catalog.name
        return self.get_status_display()

    def __str__(self) -> str:
        return f"{self.printer.serial_number} - {self.status_display_name}"


class Collaborator(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="collaborator_profile",
    )
    full_name = models.CharField(max_length=120)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=80, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self) -> str:
        return self.full_name
