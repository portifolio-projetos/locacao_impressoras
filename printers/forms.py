from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Q
from django.db import transaction
from django.utils import timezone
from urllib.parse import quote
import re

from .models import (
    City,
    Collaborator,
    Location,
    LocationCatalog,
    MaintenanceProvider,
    MaintenanceStatus,
    Printer,
    PrinterInstallationHistory,
    PrinterMaintenance,
    PrinterModel,
    Sector,
    SectorCatalog,
)


class BootstrapFormMixin:
    """Aplica classes Bootstrap padrão às entradas de formulário."""

    bootstrap_input_class = "form-control"
    bootstrap_select_class = "form-select"

    def _apply_bootstrap_styles(self):
        for field in self.fields.values():
            widget = field.widget
            existing = widget.attrs.get("class", "").strip()
            if isinstance(widget, forms.Select):
                classes = f"{existing} {self.bootstrap_select_class}".strip()
            elif isinstance(widget, (forms.CheckboxInput,)):
                classes = f"{existing} form-check-input".strip()
            else:
                classes = f"{existing} {self.bootstrap_input_class}".strip()
            widget.attrs["class"] = classes


def _normalize_state(value: str) -> str:
    letters = re.sub(r"[^A-Za-z]", "", (value or "").strip()).upper()
    return letters[:2]


def _normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", (value or "").strip())
    if not digits:
        return ""
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    return digits


class CityForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = City
        fields = ["name", "state"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["state"].widget.attrs["maxlength"] = 2
        self.fields["state"].widget.attrs["placeholder"] = "UF"
        self.fields["state"].widget.attrs["style"] = "text-transform:uppercase"
        self._apply_bootstrap_styles()

    def clean_state(self):
        value = self.cleaned_data.get("state", "")
        normalized = _normalize_state(value)
        if value and len(normalized) != 2:
            raise forms.ValidationError("Informe uma UF válida com 2 letras.")
        return normalized


class SectorCatalogForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = SectorCatalog
        fields = ["name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs["placeholder"] = "Ex.: Recepcao, Enfermagem, RH"
        self._apply_bootstrap_styles()


class LocationCatalogForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = LocationCatalog
        fields = ["name", "city", "address", "phone", "neighborhood", "zip_code", "location_url"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs["placeholder"] = "Ex.: Prefeitura Municipal, Secretaria de Saúde"
        self.fields["city"].required = True
        self.fields["city"].queryset = City.objects.order_by("name")
        self.fields["address"].required = False
        self.fields["phone"].required = False
        self.fields["neighborhood"].required = False
        self.fields["zip_code"].required = False
        self.fields["location_url"].required = False
        self.fields["address"].widget.attrs["placeholder"] = "Rua/Av, número"
        self.fields["phone"].widget.attrs["placeholder"] = "(99) 99999-9999"
        self.fields["phone"].widget.attrs["maxlength"] = 15
        self.fields["phone"].widget.attrs["inputmode"] = "numeric"
        self.fields["neighborhood"].widget.attrs["placeholder"] = "Bairro"
        self.fields["zip_code"].widget.attrs["placeholder"] = "CEP"
        self.fields["zip_code"].widget.attrs["maxlength"] = 9
        self.fields["zip_code"].widget.attrs["inputmode"] = "numeric"
        self.fields["zip_code"].widget.attrs["pattern"] = r"\d{5}-\d{3}"
        self.fields["location_url"].widget.attrs["placeholder"] = "Link de localização (Waze, Google Maps...)"
        self._apply_bootstrap_styles()

    def clean_zip_code(self):
        value = (self.cleaned_data.get("zip_code") or "").strip()
        if not value:
            return ""
        digits = re.sub(r"\D", "", value)
        if len(digits) != 8:
            raise forms.ValidationError("Informe um CEP válido no formato 99999-999.")
        return f"{digits[:5]}-{digits[5:]}"

    def clean_location_url(self):
        value = (self.cleaned_data.get("location_url") or "").strip()
        if not value:
            return ""
        if value.lower().startswith(("http://", "https://")):
            return value
        return f"https://www.google.com/maps/search/?api=1&query={quote(value)}"

    def clean_phone(self):
        value = self.cleaned_data.get("phone", "")
        normalized = _normalize_phone(value)
        if normalized:
            digits = re.sub(r"\D", "", normalized)
            if len(digits) not in (10, 11):
                raise forms.ValidationError("Informe um telefone válido com DDD.")
        return normalized


class SectorForm(BootstrapFormMixin, forms.ModelForm):
    sector_base = forms.ModelChoiceField(
        label="Setor",
        queryset=SectorCatalog.objects.order_by("name"),
        empty_label="Selecione um setor base",
    )
    location_base = forms.ModelChoiceField(
        label="Local",
        queryset=LocationCatalog.objects.none(),
        empty_label="Selecione um local de base",
    )

    class Meta:
        model = Sector
        fields = ["city"]

    def clean(self):
        cleaned_data = super().clean()
        city = cleaned_data.get("city")
        sector_base = cleaned_data.get("sector_base")
        location_base = cleaned_data.get("location_base")

        if not city or not sector_base or not location_base:
            return cleaned_data

        if location_base.city_id and location_base.city_id != city.id:
            self.add_error("location_base", "Este local base pertence a outra cidade.")
            return cleaned_data

        existing_sector = (
            Sector.objects.filter(
                city=city,
                location__name__iexact=location_base.name,
                name__iexact=sector_base.name,
            )
            .exclude(pk=self.instance.pk)
            .first()
        )
        if existing_sector:
            self.add_error("sector_base", "Este setor ja esta vinculado a este local nesta cidade.")

        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["city"].required = True
        self.fields["location_base"].required = True

        selected_city_id = None
        if self.is_bound:
            city_value = self.data.get(self.add_prefix("city"))
            if city_value:
                selected_city_id = city_value
        elif self.instance and self.instance.pk and self.instance.city_id:
            selected_city_id = self.instance.city_id

        if self.instance and self.instance.pk:
            sector_base = SectorCatalog.objects.filter(name__iexact=self.instance.name).first()
            location_base = LocationCatalog.objects.filter(
                city_id=self.instance.city_id,
                name__iexact=self.instance.location.name
            ).first()
            if sector_base:
                self.initial["sector_base"] = sector_base
            if location_base:
                self.initial["location_base"] = location_base

        location_queryset = LocationCatalog.objects.select_related("city")
        if selected_city_id:
            location_queryset = location_queryset.filter(city_id=selected_city_id)
        self.fields["location_base"].queryset = location_queryset.order_by("name")
        self.fields["location_base"].label_from_instance = self._location_base_label

        self._apply_bootstrap_styles()

    def save(self, commit=True):
        instance = super().save(commit=False)
        sector_base = self.cleaned_data["sector_base"]
        location_base = self.cleaned_data["location_base"]
        city = self.cleaned_data["city"]

        location, _ = Location.objects.get_or_create(city=city, name=location_base.name)
        instance.location = location
        instance.name = sector_base.name

        if commit:
            instance.save()
            self.save_m2m()
        return instance

    @staticmethod
    def _location_base_label(location_base: LocationCatalog) -> str:
        if location_base.address and location_base.neighborhood:
            return f"{location_base.name} - {location_base.address} - {location_base.neighborhood}"
        if location_base.address:
            return f"{location_base.name} - {location_base.address}"
        return location_base.name


class PrinterModelForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = PrinterModel
        fields = ["name", "manufacturer"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap_styles()


class MaintenanceStatusForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = MaintenanceStatus
        fields = ["name", "flow"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs["placeholder"] = "Ex.: Em manutencao, Aguardando peca, Disponivel"
        self._apply_bootstrap_styles()


class MaintenanceProviderForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = MaintenanceProvider
        fields = [
            "supplier_name",
            "address",
            "phone",
            "city",
            "state",
            "neighborhood",
            "contact_name",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["supplier_name"].widget.attrs["placeholder"] = "Nome do fornecedor"
        self.fields["address"].widget.attrs["placeholder"] = "Endereco"
        self.fields["phone"].widget.attrs["placeholder"] = "(99) 99999-9999"
        self.fields["phone"].widget.attrs["maxlength"] = 15
        self.fields["phone"].widget.attrs["inputmode"] = "numeric"
        self.fields["city"].widget.attrs["placeholder"] = "Cidade"
        self.fields["state"].widget.attrs["placeholder"] = "UF"
        self.fields["state"].widget.attrs["maxlength"] = 2
        self.fields["state"].widget.attrs["style"] = "text-transform:uppercase"
        self.fields["neighborhood"].widget.attrs["placeholder"] = "Bairro"
        self.fields["contact_name"].widget.attrs["placeholder"] = "Nome do responsavel"
        self._apply_bootstrap_styles()

    def clean_state(self):
        value = self.cleaned_data.get("state", "")
        normalized = _normalize_state(value)
        if len(normalized) != 2:
            raise forms.ValidationError("Informe uma UF válida com 2 letras.")
        return normalized

    def clean_phone(self):
        value = self.cleaned_data.get("phone", "")
        normalized = _normalize_phone(value)
        if normalized:
            digits = re.sub(r"\D", "", normalized)
            if len(digits) not in (10, 11):
                raise forms.ValidationError("Informe um telefone válido com DDD.")
        return normalized


class PrinterForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Printer
        fields = [
            "serial_number",
            "serial_number_scan_text",
            "patrimony_number",
            "barcode",
            "barcode_scan_text",
            "model",
            "city",
            "sector",
            "location",
            "installed_at",
            "notes",
        ]
        widgets = {
            "installed_at": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "serial_number_scan_text": forms.HiddenInput(),
            "barcode_scan_text": forms.HiddenInput(),
        }

    def clean_serial_number(self):
        serial = self.cleaned_data.get("serial_number")
        if not serial:
            return serial

        existing = (
            Printer.objects.filter(serial_number__iexact=serial)
            .exclude(pk=self.instance.pk)
            .first()
        )
        if existing:
            if existing.maintenance_records.filter(
                status=PrinterMaintenance.Status.IN_PROGRESS
            ).exists():
                raise forms.ValidationError(
                    "Este numero de serie esta vinculado a uma impressora em manutencao. Finalize o processo antes de realocar.",
                )
            if existing.city_id or existing.sector_id:
                raise forms.ValidationError(
                    "Ja existe uma impressora instalada com este numero de serie. Libere-a antes de reutilizar o codigo.",
                )
            raise forms.ValidationError(
                "Ja existe uma impressora cadastrada com este numero de serie.",
            )
        return serial

    def clean_sector(self):
        sector = self.cleaned_data.get("sector")
        city = self.cleaned_data.get("city")
        if sector and city and sector.city_id != city.id:
            raise forms.ValidationError("Escolha um setor da mesma cidade.")
        return sector

    def clean(self):
        cleaned_data = super().clean()
        sector = cleaned_data.get("sector")
        city = cleaned_data.get("city")
        installed_at = cleaned_data.get("installed_at")
        serial_number = cleaned_data.get("serial_number")
        barcode = cleaned_data.get("barcode")
        serial_number_scan_text = cleaned_data.get("serial_number_scan_text")
        barcode_scan_text = cleaned_data.get("barcode_scan_text")

        if installed_at and installed_at > timezone.now():
            self.add_error("installed_at", "A data de instalacao nao pode ser maior que a data atual.")

        if bool(city) ^ bool(sector):
            if not city:
                self.add_error("city", "Informe a cidade para o setor selecionado.")
            if not sector:
                self.add_error("sector", "Selecione o setor correspondente a cidade.")

        if sector:
            cleaned_data["location"] = sector.location.name
        else:
            cleaned_data["location"] = ""

        if not serial_number_scan_text and serial_number:
            cleaned_data["serial_number_scan_text"] = serial_number

        if not barcode_scan_text and barcode:
            cleaned_data["barcode_scan_text"] = barcode

        instance = self.instance if self.instance and self.instance.pk else None
        if instance:
            has_in_progress = instance.maintenance_records.filter(
                status=PrinterMaintenance.Status.IN_PROGRESS
            ).exists()
            if has_in_progress and cleaned_data.get("city") and cleaned_data.get("sector"):
                raise forms.ValidationError(
                    "Esta impressora esta em manutencao. Finalize ou libere o equipamento antes de instalar em outro local.",
                )
        if not cleaned_data.get("serial_number"):
            cleaned_data["serial_number"] = None
        return cleaned_data

    def __init__(self, *args, **kwargs):
        self._previous_assignment = None
        if "instance" in kwargs and kwargs["instance"] and kwargs["instance"].pk:
            instance = kwargs["instance"]
            self._previous_assignment = {
                "city_id": instance.city_id,
                "sector_id": instance.sector_id,
                "location": instance.location,
            }
        super().__init__(*args, **kwargs)

        initial_city = None
        initial_sector = None

        if self.is_bound:
            city_value = self.data.get(self.add_prefix("city"))
            sector_value = self.data.get(self.add_prefix("sector"))
            if city_value:
                initial_city = city_value
            if sector_value:
                initial_sector = sector_value
        else:
            initial_city = self.initial.get("city") or getattr(self.instance, "city_id", None)
            initial_sector = self.initial.get("sector") or getattr(self.instance, "sector_id", None)
            if hasattr(initial_city, "id"):
                initial_city = initial_city.id
            if hasattr(initial_sector, "id"):
                initial_sector = initial_sector.id

        sector_queryset = Sector.objects.none()
        if initial_city:
            sector_queryset = Sector.objects.filter(city_id=initial_city).select_related("location").order_by(
                "location__name", "name"
            )
        elif initial_sector:
            sector_queryset = Sector.objects.filter(pk=initial_sector).select_related("location")

        self.fields["sector"].queryset = sector_queryset
        self.fields["location"].required = False
        self.fields["location"].widget.attrs.update(
            {"readonly": True, "placeholder": "Selecione um setor"}
        )
        self.fields["city"].required = True
        self.fields["sector"].required = True
        self.fields["sector"].label_from_instance = self._sector_label
        self.fields["installed_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M"]
        if self.instance and self.instance.pk and self.instance.installed_at:
            self.initial["installed_at"] = timezone.localtime(self.instance.installed_at).strftime("%Y-%m-%dT%H:%M")
        self._apply_bootstrap_styles()
        self.fields["location"].widget.attrs["class"] += " bg-light"

    @staticmethod
    def _sector_label(sector: Sector) -> str:
        return f"{sector.location.name} - {sector.name}"

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if commit:
            self._sync_installation_history(instance)
        return instance

    def _sync_installation_history(self, instance: Printer) -> None:
        previous = self._previous_assignment or {}
        previous_city_id = previous.get("city_id")
        previous_sector_id = previous.get("sector_id")
        previous_location = previous.get("location") or ""

        current_city_id = instance.city_id
        current_sector_id = instance.sector_id
        current_location = instance.location or ""

        assignment_changed = (
            previous_city_id != current_city_id
            or previous_sector_id != current_sector_id
            or previous_location != current_location
        )

        open_history = (
            PrinterInstallationHistory.objects.filter(printer=instance, removed_at__isnull=True)
            .order_by("-installed_at", "-created_at")
            .first()
        )

        if open_history and (assignment_changed or not current_city_id or not current_sector_id):
            removal_date = instance.installed_at or timezone.now()
            if open_history.installed_at and removal_date and removal_date < open_history.installed_at:
                removal_date = open_history.installed_at
            open_history.removed_at = removal_date
            open_history.save(update_fields=["removed_at", "updated_at"])
            open_history = None

        if current_city_id and current_sector_id:
            if open_history:
                same_assignment = (
                    open_history.city_id == current_city_id
                    and open_history.sector_id == current_sector_id
                    and open_history.location_name == current_location
                )
                if same_assignment:
                    if instance.installed_at and open_history.installed_at != instance.installed_at:
                        open_history.installed_at = instance.installed_at
                        open_history.save(update_fields=["installed_at", "updated_at"])
                    return

            PrinterInstallationHistory.objects.create(
                printer=instance,
                city=instance.city,
                sector=instance.sector,
                location_name=current_location,
                installed_at=instance.installed_at or timezone.now(),
            )


class PrinterMaintenanceForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = PrinterMaintenance
        fields = [
            "printer",
            "defect_description",
            "solution_description",
            "status_catalog",
            "maintenance_provider",
            "started_at",
            "finished_at",
        ]
        widgets = {
            "defect_description": forms.Textarea(attrs={"rows": 3}),
            "solution_description": forms.Textarea(attrs={"rows": 3}),
            "started_at": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
            "finished_at": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        printer_queryset = kwargs.pop("printer_queryset", None)
        super().__init__(*args, **kwargs)
        instance = getattr(self, "instance", None)

        base_queryset = printer_queryset or Printer.objects.select_related(
            "city", "sector", "model"
        ).order_by("serial_number")
        if instance and instance.pk:
            self.fields["printer"].disabled = True
            self.fields["printer"].queryset = base_queryset
        else:
            self.fields["printer"].queryset = base_queryset.exclude(
                Q(maintenance_records__status_catalog__flow=PrinterMaintenance.Status.IN_PROGRESS)
                | Q(
                    maintenance_records__status_catalog__isnull=True,
                    maintenance_records__status=PrinterMaintenance.Status.IN_PROGRESS,
                )
            )
        self.fields["printer"].label_from_instance = self._printer_label
        self.fields["status_catalog"].queryset = MaintenanceStatus.objects.order_by("name")
        self.fields["maintenance_provider"].queryset = MaintenanceProvider.objects.order_by("supplier_name")
        self.fields["status_catalog"].required = True
        self.fields["maintenance_provider"].required = True
        self.fields["solution_description"].required = False
        self.fields["started_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M"]
        self.fields["finished_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M"]

        if instance and instance.pk:
            if instance.started_at:
                self.initial["started_at"] = timezone.localtime(instance.started_at).strftime("%Y-%m-%dT%H:%M")
            if instance.finished_at:
                self.initial["finished_at"] = timezone.localtime(instance.finished_at).strftime("%Y-%m-%dT%H:%M")

        self._apply_bootstrap_styles()

        if instance and instance.pk:
            self.fields["printer"].widget.attrs["class"] += " bg-light"

    def clean(self):
        cleaned_data = super().clean()
        printer = cleaned_data.get("printer")

        if not self.instance.pk and printer:
            in_progress = printer.maintenance_records.filter(
                Q(status_catalog__flow=PrinterMaintenance.Status.IN_PROGRESS)
                | Q(status_catalog__isnull=True, status=PrinterMaintenance.Status.IN_PROGRESS)
            ).exists()
            if in_progress:
                raise forms.ValidationError("Esta impressora ja esta em manutencao.")

        started_at = cleaned_data.get("started_at")
        finished_at = cleaned_data.get("finished_at")
        status_catalog = cleaned_data.get("status_catalog")

        if started_at and finished_at and finished_at < started_at:
            self.add_error("finished_at", "A data de saida nao pode ser anterior a data de entrada.")

        if started_at and started_at > timezone.now():
            self.add_error("started_at", "A data de entrada nao pode ser maior que a data atual.")

        if finished_at and finished_at > timezone.now():
            self.add_error("finished_at", "A data de saida nao pode ser maior que a data atual.")

        if status_catalog and status_catalog.flow == PrinterMaintenance.Status.COMPLETED and not finished_at:
            self.add_error("finished_at", "Informe a data de saida para liberar a impressora.")

        if status_catalog and status_catalog.flow == PrinterMaintenance.Status.COMPLETED and not cleaned_data.get("solution_description"):
            self.add_error("solution_description", "Informe a solucao aplicada para finalizar a manutencao.")

        if status_catalog and status_catalog.flow == PrinterMaintenance.Status.IN_PROGRESS and finished_at:
            self.add_error(
                "status_catalog",
                "Altere o status para disponivel ou remova a data de saida antes de salvar.",
            )

        return cleaned_data

    def _post_clean(self):
        printer = self.cleaned_data.get("printer")
        if not printer and getattr(self.instance, "printer_id", None):
            printer = self.instance.printer
        if printer:
            if printer.city_id and not self.instance.origin_city_id:
                self.instance.origin_city = printer.city
            if printer.sector_id and not self.instance.origin_sector_id:
                self.instance.origin_sector = printer.sector
        super()._post_clean()

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.printer_id:
            if instance.printer.city_id and not instance.origin_city_id:
                instance.origin_city = instance.printer.city
            if instance.printer.sector_id and not instance.origin_sector_id:
                instance.origin_sector = instance.printer.sector
            if instance.status_catalog_id:
                instance.status = instance.status_catalog.flow
        if commit:
            instance.save()
            self.save_m2m()
            self._sync_printer_assignment(instance)
        return instance

    def _sync_printer_assignment(self, instance: PrinterMaintenance) -> None:
        printer = instance.printer
        printer_id = getattr(printer, "id", None)
        if not printer_id:
            return
        if instance.current_status_flow == PrinterMaintenance.Status.IN_PROGRESS:
            open_history = (
                PrinterInstallationHistory.objects.filter(printer=printer, removed_at__isnull=True)
                .order_by("-installed_at", "-created_at")
                .first()
            )
            if open_history:
                removal_date = instance.started_at or timezone.now()
                if open_history.installed_at and removal_date < open_history.installed_at:
                    removal_date = open_history.installed_at
                open_history.removed_at = removal_date
                open_history.save(update_fields=["removed_at", "updated_at"])

            updates = {}
            if printer.city_id is not None:
                updates["city"] = None
            if printer.sector_id is not None:
                updates["sector"] = None
            if printer.location:
                updates["location"] = ""
            if printer.installed_at is not None:
                updates["installed_at"] = None
            if updates:
                for field, value in updates.items():
                    setattr(printer, field, value)
                printer.save(update_fields=list(updates.keys()))

    @staticmethod
    def _printer_label(printer: Printer) -> str:
        city = printer.city.name if printer.city_id else "Sem cidade"
        sector = printer.sector.name if printer.sector_id else "Sem setor"
        location = printer.location or "Sem local"
        return f"{printer.serial_number} - {printer.model} - {city} / {sector} - {location}"


class CollaboratorForm(BootstrapFormMixin, forms.ModelForm):
    login = forms.CharField(max_length=150, label="Login")
    password = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(render_value=False),
        strip=False,
    )

    class Meta:
        model = Collaborator
        fields = ["full_name", "email", "role", "phone", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = getattr(self.instance, "user", None)
        self.fields["login"].initial = ""
        self.fields["password"].initial = ""
        self.fields["login"].widget.attrs.update(
            {
                "autocomplete": "off",
                "autocapitalize": "none",
                "autocorrect": "off",
                "spellcheck": "false",
            }
        )
        self.fields["password"].widget.attrs.update(
            {
                "autocomplete": "new-password",
            }
        )
        self.fields["phone"].widget.attrs["placeholder"] = "(99) 99999-9999"
        self.fields["phone"].widget.attrs["maxlength"] = 15
        self.fields["phone"].widget.attrs["inputmode"] = "numeric"
        if user_id := getattr(user, "id", None):
            self.fields["login"].initial = user.username
            self.fields["password"].required = False
            self.fields["password"].help_text = "Preencha apenas se quiser definir uma nova senha."
        self._apply_bootstrap_styles()

    def clean_login(self):
        login = self.cleaned_data["login"].strip()
        User = get_user_model()
        queryset = User.objects.filter(username__iexact=login)
        if getattr(self.instance, "user_id", None):
            queryset = queryset.exclude(pk=self.instance.user_id)
        if queryset.exists():
            raise forms.ValidationError("Este login ja esta em uso.")
        return login

    def clean_password(self):
        password = self.cleaned_data.get("password", "")
        if not password and not getattr(self.instance, "user_id", None):
            raise forms.ValidationError("Informe uma senha para o acesso do colaborador.")
        return password

    def clean_phone(self):
        value = self.cleaned_data.get("phone", "")
        normalized = _normalize_phone(value)
        if normalized:
            digits = re.sub(r"\D", "", normalized)
            if len(digits) not in (10, 11):
                raise forms.ValidationError("Informe um telefone válido com DDD.")
        return normalized

    @transaction.atomic
    def save(self, commit=True):
        collaborator = super().save(commit=False)
        User = get_user_model()
        login = self.cleaned_data["login"]
        password = self.cleaned_data.get("password")

        user = collaborator.user if collaborator.user_id else User()
        user.username = login
        user.email = collaborator.email
        user.first_name = collaborator.full_name
        user.is_active = True

        if password:
            user.set_password(password)

        if commit:
            user.save()
            collaborator.user = user
            collaborator.save()
            self.save_m2m()

        return collaborator


class LoginForm(BootstrapFormMixin, AuthenticationForm):
    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request=request, *args, **kwargs)
        self._apply_bootstrap_styles()
