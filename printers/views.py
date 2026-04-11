from collections import defaultdict
from datetime import date

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from .forms import (
    CollaboratorForm,
    CityForm,
    LocationCatalogForm,
    MaintenanceProviderForm,
    MaintenanceStatusForm,
    PrinterForm,
    PrinterMaintenanceForm,
    PrinterModelForm,
    SectorForm,
    SectorCatalogForm,
    LoginForm,
)
from .models import (
    Collaborator,
    City,
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


def _build_sector_metadata():
    sector_locations = {}
    sector_choices = {}
    location_choices = {}
    sectors_by_location = {}
    sector_name_catalog = list(SectorCatalog.objects.order_by("name").values_list("name", flat=True))

    for location in Location.objects.select_related("city").order_by("city__name", "name"):
        location_choices.setdefault(str(location.city_id), []).append(
            {
                "id": str(location.id),
                "name": location.name,
            }
        )

    for sector in Sector.objects.select_related("city", "location").order_by(
        "city__name", "location__name", "name"
    ):
        sector_locations[str(sector.id)] = sector.location.name
        sector_choices.setdefault(str(sector.city_id), []).append(
            {
                "id": str(sector.id),
                "name": sector.name,
                "label": f"{sector.location.name} - {sector.name}",
                "location": sector.location.name,
            }
        )
        sectors_by_location.setdefault(str(sector.location_id), []).append(
            {
                "id": str(sector.id),
                "name": sector.name,
            }
        )
    return sector_locations, sector_choices, location_choices, sectors_by_location, sector_name_catalog


def _build_sector_binding_preview():
    bindings = {}
    for sector in Sector.objects.select_related("city", "location").order_by(
        "city__name", "location__name", "name"
    ):
        key = f"{sector.city_id}:{sector.location.name.lower()}"
        bindings.setdefault(key, []).append(sector.name)
    return bindings


@login_required
def dashboard(request):
    cities = (
        City.objects.prefetch_related("sectors")
        .annotate(printer_count=Count("printers"))
        .order_by("name")
    )
    models = PrinterModel.objects.annotate(
        printer_count=Count(
            "printers",
            filter=Q(printers__city__isnull=False, printers__sector__isnull=False),
        )
    ).order_by("name")
    maintenance_in_progress = PrinterMaintenance.objects.filter(
        status=PrinterMaintenance.Status.IN_PROGRESS
    ).count()
    maintenance_completed_this_month = PrinterMaintenance.objects.filter(
        status=PrinterMaintenance.Status.COMPLETED,
        finished_at__month=date.today().month,
        finished_at__year=date.today().year,
    ).count()
    return render(
        request,
        "printers/dashboard.html",
        {
            "cities": cities,
            "models": models,
            "total_printers": Printer.objects.filter(city__isnull=False, sector__isnull=False).count(),
            "maintenance_in_progress": maintenance_in_progress,
            "maintenance_completed_this_month": maintenance_completed_this_month,
        },
    )


@login_required
def printer_list(request):

    class AppLoginView(LoginView):
        template_name = "registration/login.html"
        authentication_form = LoginForm
    search_query = request.GET.get("q", "").strip()
    printers_qs = (
        Printer.objects.select_related("model", "city", "sector", "sector__location")
        .filter(city__isnull=False, sector__isnull=False)
    )

    if search_query:
        printers_qs = printers_qs.filter(
            Q(serial_number__icontains=search_query)
            | Q(serial_number_scan_text__icontains=search_query)
            | Q(patrimony_number__icontains=search_query)
            | Q(barcode__icontains=search_query)
            | Q(barcode_scan_text__icontains=search_query)
            | Q(city__name__icontains=search_query)
            | Q(model__name__icontains=search_query)
            | Q(model__manufacturer__icontains=search_query)
            | Q(sector__name__icontains=search_query)
            | Q(location__icontains=search_query)
        )

    printers_qs = printers_qs.order_by("city__name", "sector__name", "serial_number")

    city_blocks: list[dict] = []
    current_city_id = None
    current_block: dict | None = None

    for printer in printers_qs:
        city = printer.city
        if not city:
            continue
        if city.id != current_city_id:
            current_block = {
                "city": city,
                "printers": [],
                "sector_map": defaultdict(lambda: {"name": "", "label": "", "locations": set()}),
                "sector_options": [],
                "location_options": set(),
            }
            city_blocks.append(current_block)
            current_city_id = city.id

        current_block["printers"].append(printer)  # type: ignore[index]
        sector_entry = current_block["sector_map"][printer.sector.id]  # type: ignore[index]
        sector_entry["name"] = printer.sector.name
        sector_entry["label"] = f"{printer.sector.location.name} - {printer.sector.name}"
        if printer.location:
            sector_entry["locations"].add(printer.location)
            current_block["location_options"].add(printer.location)

    for block in city_blocks:
        block["sector_options"] = [
            {
                "id": sector_id,
                "name": entry["name"],
                "label": entry["label"],
                "locations": sorted(filter(None, entry["locations"]), key=lambda value: value.lower()),
            }
            for sector_id, entry in block["sector_map"].items()
        ]
        block["sector_options"].sort(key=lambda item: item["label"].lower())
        block["sector_locations_map"] = {
            str(option["id"]): option["locations"] for option in block["sector_options"]
        }
        block["location_options"] = sorted(
            filter(None, block["location_options"]), key=lambda value: value.lower()
        )
        block.pop("sector_map", None)

    return render(
        request,
        "printers/printer_list.html",
        {
            "city_blocks": city_blocks,
            "search_query": search_query,
        },
    )


@login_required
def printer_create(request):
    sector_locations, sector_choices, _, _, _ = _build_sector_metadata()
    initial: dict[str, object] = {}
    city_param = request.GET.get("city")
    sector_param = request.GET.get("sector")
    maintenance_param = request.GET.get("maintenance")
    maintenance_record = None

    if maintenance_param:
        maintenance_record = (
            PrinterMaintenance.objects.select_related("status_catalog", "printer", "printer__model")
            .filter(pk=maintenance_param)
            .first()
        )
        if not maintenance_record:
            messages.error(request, "Registro de manutencao nao encontrado para instalacao.")
            return redirect(reverse("printers:maintenance-list"))

        if maintenance_record.current_status_flow != PrinterMaintenance.Status.COMPLETED:
            messages.error(
                request,
                "A impressora so pode ser instalada quando a manutencao estiver com status Disponivel.",
            )
            return redirect(reverse("printers:maintenance-list"))

        if maintenance_record.replacement_installed_at is not None:
            messages.info(request, "A instalacao dessa manutencao ja foi registrada.")
            return redirect(reverse("printers:maintenance-list"))

        if maintenance_record.printer_id and maintenance_record.printer.model_id:
            initial["model"] = maintenance_record.printer.model

    if sector_param:
        selected_sector = (
            Sector.objects.select_related("city", "location")
            .filter(pk=sector_param)
            .first()
        )
        if selected_sector:
            initial["sector"] = selected_sector
            initial["city"] = selected_sector.city
            initial["location"] = selected_sector.location.name

    if city_param and "city" not in initial:
        selected_city = City.objects.filter(pk=city_param).first()
        if selected_city:
            initial["city"] = selected_city

    form_action_query = ""
    query_params: list[str] = []
    if city_param:
        query_params.append(f"city={city_param}")
    if sector_param:
        query_params.append(f"sector={sector_param}")
    if maintenance_param:
        query_params.append(f"maintenance={maintenance_param}")
    if query_params:
        form_action_query = "?" + "&".join(query_params)

    if request.method == "POST":
        form = PrinterForm(request.POST)
        if form.is_valid():
            printer = form.save()
            if maintenance_record and maintenance_record.replacement_installed_at is None:
                maintenance_record.replacement_installed_at = timezone.now()
                maintenance_record.save(update_fields=["replacement_installed_at", "updated_at"])
                messages.success(
                    request,
                    "Instalacao registrada para a manutencao disponibilizada.",
                )
            return redirect(reverse("printers:printer-detail", args=[printer.id]))
    else:
        form = PrinterForm(initial=initial)
    return render(
        request,
        "printers/printer_form.html",
        {
            "form": form,
            "sector_locations": sector_locations,
            "sector_choices": sector_choices,
            "form_action_query": form_action_query,
        },
    )


@login_required
def printer_update(request, pk):
    printer = get_object_or_404(Printer, pk=pk)
    sector_locations, sector_choices, _, _, _ = _build_sector_metadata()
    if request.method == "POST":
        form = PrinterForm(request.POST, instance=printer)
        if form.is_valid():
            printer = form.save()
            return redirect(reverse("printers:printer-detail", args=[printer.id]))
    else:
        form = PrinterForm(instance=printer)
    return render(
        request,
        "printers/printer_form.html",
        {
            "form": form,
            "printer": printer,
            "sector_locations": sector_locations,
            "sector_choices": sector_choices,
            "form_action_query": "",
        },
    )


@login_required
def printer_detail(request, pk):
    printer = get_object_or_404(
        Printer.objects.select_related("model", "city", "sector"), pk=pk
    )
    installation_history = (
        printer.installation_history.select_related("city", "sector", "sector__location")
        .order_by("-installed_at", "-created_at")
        .all()
    )
    maintenance_history = (
        printer.maintenance_records.select_related("origin_city", "origin_sector", "maintenance_provider", "status_catalog")
        .order_by("-started_at")
        .all()
    )
    return render(
        request,
        "printers/printer_detail.html",
        {
            "printer": printer,
            "installation_history": installation_history,
            "maintenance_history": maintenance_history,
        },
    )


@login_required
def printer_delete(request, pk):
    printer = get_object_or_404(Printer, pk=pk)
    if request.method == "POST":
        printer.delete()
        messages.success(request, "Impressora excluída com sucesso.")
        return redirect(reverse("printers:printer-list"))
    return render(request, "printers/printer_confirm_delete.html", {"printer": printer})


@login_required
def city_list(request):
    cities = (
        City.objects.annotate(
            printer_count=Count("printers", distinct=True),
            sector_count=Count("sectors", distinct=True),
        ).order_by("name")
    )
    return render(request, "printers/city_list.html", {"cities": cities})


@login_required
def city_create(request):
    if request.method == "POST":
        form = CityForm(request.POST)
        if form.is_valid():
            city = form.save()
            messages.success(request, f"Cidade '{city}' cadastrada.")
            return redirect(reverse("printers:city-list"))
    else:
        form = CityForm()
    return render(request, "printers/city_form.html", {"form": form})


@login_required
def city_update(request, pk):
    city = get_object_or_404(City, pk=pk)
    if request.method == "POST":
        form = CityForm(request.POST, instance=city)
        if form.is_valid():
            form.save()
            messages.success(request, f"Cidade '{city}' atualizada.")
            return redirect(reverse("printers:city-list"))
    else:
        form = CityForm(instance=city)
    return render(request, "printers/city_form.html", {"form": form, "city": city})


@login_required
def city_delete(request, pk):
    city = get_object_or_404(City, pk=pk)
    if request.method == "POST":
        city.delete()
        messages.success(request, "Cidade removida.")
        return redirect(reverse("printers:city-list"))
    return render(request, "printers/city_confirm_delete.html", {"city": city})


@login_required
def sector_catalog_list(request):
    sector_catalog = SectorCatalog.objects.order_by("name")
    return render(
        request,
        "printers/sector_catalog_list.html",
        {"sector_catalog": sector_catalog},
    )


@login_required
def sector_catalog_create(request):
    if request.method == "POST":
        form = SectorCatalogForm(request.POST)
        if form.is_valid():
            sector_catalog = form.save()
            messages.success(request, f"Setor base '{sector_catalog.name}' cadastrado.")
            return redirect(reverse("printers:sector-catalog-list"))
    else:
        form = SectorCatalogForm()
    return render(request, "printers/sector_catalog_form.html", {"form": form})


@login_required
def sector_catalog_update(request, pk):
    sector_catalog = get_object_or_404(SectorCatalog, pk=pk)
    if request.method == "POST":
        form = SectorCatalogForm(request.POST, instance=sector_catalog)
        if form.is_valid():
            form.save()
            messages.success(request, f"Setor base '{sector_catalog.name}' atualizado.")
            return redirect(reverse("printers:sector-catalog-list"))
    else:
        form = SectorCatalogForm(instance=sector_catalog)
    return render(
        request,
        "printers/sector_catalog_form.html",
        {"form": form, "sector_catalog_item": sector_catalog},
    )


@login_required
def sector_catalog_delete(request, pk):
    sector_catalog = get_object_or_404(SectorCatalog, pk=pk)
    if request.method == "POST":
        sector_catalog.delete()
        messages.success(request, "Setor base removido.")
        return redirect(reverse("printers:sector-catalog-list"))
    return render(
        request,
        "printers/sector_catalog_confirm_delete.html",
        {"sector_catalog_item": sector_catalog},
    )


@login_required
def location_catalog_list(request):
    location_catalog = LocationCatalog.objects.order_by("name")
    return render(
        request,
        "printers/location_catalog_list.html",
        {"location_catalog": location_catalog},
    )


@login_required
def location_catalog_create(request):
    if request.method == "POST":
        form = LocationCatalogForm(request.POST)
        if form.is_valid():
            location_catalog = form.save()
            messages.success(request, f"Local base '{location_catalog.name}' cadastrado.")
            return redirect(reverse("printers:location-catalog-list"))
    else:
        form = LocationCatalogForm()
    return render(request, "printers/location_catalog_form.html", {"form": form})


@login_required
def location_catalog_update(request, pk):
    location_catalog = get_object_or_404(LocationCatalog, pk=pk)
    if request.method == "POST":
        form = LocationCatalogForm(request.POST, instance=location_catalog)
        if form.is_valid():
            form.save()
            messages.success(request, f"Local base '{location_catalog.name}' atualizado.")
            return redirect(reverse("printers:location-catalog-list"))
    else:
        form = LocationCatalogForm(instance=location_catalog)
    return render(
        request,
        "printers/location_catalog_form.html",
        {"form": form, "location_catalog_item": location_catalog},
    )


@login_required
def location_catalog_delete(request, pk):
    location_catalog = get_object_or_404(LocationCatalog, pk=pk)
    if request.method == "POST":
        location_catalog.delete()
        messages.success(request, "Local base removido.")
        return redirect(reverse("printers:location-catalog-list"))
    return render(
        request,
        "printers/location_catalog_confirm_delete.html",
        {"location_catalog_item": location_catalog},
    )


@login_required
def sector_list(request):
    return render(
        request,
        "printers/sector_hub.html",
        {
            "sector_catalog_count": SectorCatalog.objects.count(),
            "location_catalog_count": LocationCatalog.objects.count(),
        },
    )


@login_required
def sector_binding_list(request):
    cities = City.objects.order_by("name")
    city_id = request.GET.get("city")
    selected_city = None
    sectors = []

    if city_id:
        selected_city = City.objects.filter(pk=city_id).first()
        if selected_city:
            sectors = (
                Sector.objects.select_related("city", "location")
                .filter(city=selected_city)
                .annotate(printer_count=Count("printers"))
                .order_by("location__name", "name")
            )

    return render(
        request,
        "printers/sector_list.html",
        {
            "cities": cities,
            "sectors": sectors,
            "selected_city": selected_city,
            "selected_city_id": city_id,
        },
    )


@login_required
def sector_create(request):
    existing_bindings = _build_sector_binding_preview()
    if request.method == "POST":
        form = SectorForm(request.POST)
        if form.is_valid():
            sector = form.save()
            messages.success(request, f"Setor '{sector}' cadastrado.")
            return redirect(reverse("printers:sector-binding-list"))
    else:
        form = SectorForm()
    return render(
        request,
        "printers/sector_form.html",
        {"form": form, "existing_bindings": existing_bindings},
    )


@login_required
def sector_update(request, pk):
    sector = get_object_or_404(Sector.objects.select_related("location"), pk=pk)
    existing_bindings = _build_sector_binding_preview()
    if request.method == "POST":
        form = SectorForm(request.POST, instance=sector)
        if form.is_valid():
            form.save()
            messages.success(request, f"Setor '{sector}' atualizado.")
            return redirect(reverse("printers:sector-binding-list"))
    else:
        form = SectorForm(instance=sector)
    return render(
        request,
        "printers/sector_form.html",
        {"form": form, "sector": sector, "existing_bindings": existing_bindings},
    )


@login_required
def sector_delete(request, pk):
    sector = get_object_or_404(Sector, pk=pk)
    if request.method == "POST":
        sector.delete()
        messages.success(request, "Setor removido.")
        return redirect(reverse("printers:sector-binding-list"))
    return render(request, "printers/sector_confirm_delete.html", {"sector": sector})


@login_required
def model_list(request):
    models = PrinterModel.objects.annotate(
        printer_count=Count(
            "printers",
            filter=Q(printers__city__isnull=False, printers__sector__isnull=False),
        )
    ).order_by("name")
    return render(request, "printers/model_list.html", {"models": models})


@login_required
def model_create(request):
    if request.method == "POST":
        form = PrinterModelForm(request.POST)
        if form.is_valid():
            model = form.save()
            messages.success(request, f"Modelo '{model}' cadastrado.")
            return redirect(reverse("printers:model-list"))
    else:
        form = PrinterModelForm()
    return render(request, "printers/model_form.html", {"form": form})


@login_required
def model_update(request, pk):
    printer_model = get_object_or_404(PrinterModel, pk=pk)
    if request.method == "POST":
        form = PrinterModelForm(request.POST, instance=printer_model)
        if form.is_valid():
            form.save()
            messages.success(request, f"Modelo '{printer_model}' atualizado.")
            return redirect(reverse("printers:model-list"))
    else:
        form = PrinterModelForm(instance=printer_model)
    return render(
        request,
        "printers/model_form.html",
        {"form": form, "printer_model": printer_model},
    )


@login_required
def model_delete(request, pk):
    printer_model = get_object_or_404(PrinterModel, pk=pk)
    if request.method == "POST":
        printer_model.delete()
        messages.success(request, "Modelo removido.")
        return redirect(reverse("printers:model-list"))
    return render(
        request,
        "printers/model_confirm_delete.html",
        {"printer_model": printer_model},
    )


@login_required
def maintenance_list(request):
    status_filter = request.GET.get("status", PrinterMaintenance.Status.IN_PROGRESS)
    valid_status = {
        PrinterMaintenance.Status.IN_PROGRESS,
        PrinterMaintenance.Status.COMPLETED,
    }
    if status_filter not in valid_status:
        status_filter = PrinterMaintenance.Status.IN_PROGRESS

    records = (
        PrinterMaintenance.objects.select_related(
            "printer",
            "printer__model",
            "origin_city",
            "origin_sector",
            "status_catalog",
            "maintenance_provider",
        )
        .filter(
            Q(status_catalog__flow=status_filter)
            | Q(status_catalog__isnull=True, status=status_filter)
        )
        .order_by("-started_at")
    )

    if status_filter == PrinterMaintenance.Status.COMPLETED:
        records = records.filter(replacement_installed_at__isnull=True)

    return render(
        request,
        "printers/maintenance_list.html",
        {
            "records": records,
            "status_filter": status_filter,
            "status_enum": PrinterMaintenance.Status,
            "status_count": MaintenanceStatus.objects.count(),
            "provider_count": MaintenanceProvider.objects.count(),
        },
    )


@login_required
def maintenance_create(request):
    initial: dict[str, object] = {}
    printer_id = request.GET.get("printer")
    city_id = request.GET.get("city")
    sector_id = request.GET.get("sector")

    cities = City.objects.order_by("name")
    selected_city = None
    selected_sector = None

    if city_id:
        selected_city = City.objects.filter(pk=city_id).first()

    if sector_id:
        candidate_sector = (
            Sector.objects.select_related("city", "location")
            .filter(pk=sector_id)
            .first()
        )
        if candidate_sector:
            if not selected_city or candidate_sector.city_id == selected_city.id:
                selected_sector = candidate_sector
                if not selected_city:
                    selected_city = candidate_sector.city
                    city_id = str(selected_city.id)
            else:
                sector_id = None

    sector_options = (
        Sector.objects.select_related("location").filter(city=selected_city).order_by(
            "location__name", "name"
        )
        if selected_city
        else []
    )

    base_printer_qs = (
        Printer.objects.select_related("city", "sector", "model")
        .filter(city__isnull=False, sector__isnull=False)
        .order_by("serial_number")
    )
    filtered_printers = base_printer_qs
    if selected_sector:
        filtered_printers = filtered_printers.filter(sector=selected_sector)
    elif selected_city:
        filtered_printers = filtered_printers.filter(city=selected_city)
    filtered_printers = filtered_printers.exclude(
        Q(maintenance_records__status_catalog__flow=PrinterMaintenance.Status.IN_PROGRESS)
        | Q(
            maintenance_records__status_catalog__isnull=True,
            maintenance_records__status=PrinterMaintenance.Status.IN_PROGRESS,
        )
    ).distinct()

    selected_printer = None
    if printer_id:
        selected_printer = (
            base_printer_qs.filter(pk=printer_id)
            .select_related("city", "sector")
            .first()
        )
        if selected_printer:
            initial["printer"] = selected_printer

    initial.setdefault("started_at", date.today())

    form_action_query = ""
    query_params = []
    if city_id:
        query_params.append(f"city={city_id}")
    if sector_id:
        query_params.append(f"sector={sector_id}")
    if query_params:
        form_action_query = "?" + "&".join(query_params)

    if request.method == "POST":
        form = PrinterMaintenanceForm(request.POST, printer_queryset=filtered_printers)
        if form.is_valid():
            record = form.save()
            messages.success(
                request,
                f"Manutenção registrada para a impressora {record.printer.serial_number}.",
            )
            return redirect(reverse("printers:maintenance-list"))
        if not selected_printer:
            printer_value = request.POST.get("printer")
            if printer_value:
                selected_printer = (
                    base_printer_qs.filter(pk=printer_value)
                    .select_related("city", "sector")
                    .first()
                )
    else:
        form = PrinterMaintenanceForm(initial=initial, printer_queryset=filtered_printers)
        if not selected_printer:
            selected_printer = initial.get("printer")  # type: ignore[assignment]

    return render(
        request,
        "printers/maintenance_form.html",
        {
            "form": form,
            "selected_printer": selected_printer,
            "cities": cities,
            "sector_options": sector_options,
            "selected_city": selected_city,
            "selected_sector": selected_sector,
            "selected_city_id": city_id,
            "selected_sector_id": sector_id,
            "form_action_query": form_action_query,
            "maintenance_providers": list(
                MaintenanceProvider.objects.order_by("supplier_name").values(
                    "id",
                    "supplier_name",
                    "address",
                    "phone",
                    "city",
                    "state",
                    "neighborhood",
                    "contact_name",
                )
            ),
            "maintenance_statuses": list(
                MaintenanceStatus.objects.order_by("name").values("id", "name", "flow")
            ),
        },
    )


@login_required
def maintenance_update(request, pk):
    record = get_object_or_404(
        PrinterMaintenance.objects.select_related(
            "printer",
            "printer__model",
            "status_catalog",
            "maintenance_provider",
        ),
        pk=pk,
    )
    previous_status = record.current_status_flow

    if request.method == "POST":
        form = PrinterMaintenanceForm(request.POST, instance=record)
        if form.is_valid():
            record = form.save()
            messages.success(
                request,
                f"Manutenção da impressora {record.printer.serial_number} atualizada.",
            )
            if (
                record.current_status_flow == PrinterMaintenance.Status.COMPLETED
                and previous_status != record.current_status_flow
                and record.origin_city_id
                and record.origin_sector_id
                and record.replacement_installed_at is None
            ):
                replacement_url = (
                    reverse("printers:printer-create")
                    + f"?city={record.origin_city_id}&sector={record.origin_sector_id}&maintenance={record.id}"
                )
                messages.info(
                    request,
                    format_html(
                        "Manutencao disponibilizada para {city}/{sector}. <a class=\"alert-link\" href=\"{url}\">Registrar instalacao</a>.",
                        city=record.origin_city,
                        sector=record.origin_sector,
                        url=replacement_url,
                    ),
                )
            return redirect(reverse("printers:maintenance-list"))
    else:
        form = PrinterMaintenanceForm(instance=record)

    return render(
        request,
        "printers/maintenance_form.html",
        {
            "form": form,
            "record": record,
            "selected_printer": record.printer,
            "maintenance_providers": list(
                MaintenanceProvider.objects.order_by("supplier_name").values(
                    "id",
                    "supplier_name",
                    "address",
                    "phone",
                    "city",
                    "state",
                    "neighborhood",
                    "contact_name",
                )
            ),
            "maintenance_statuses": list(
                MaintenanceStatus.objects.order_by("name").values("id", "name", "flow")
            ),
        },
    )


@login_required
def maintenance_status_list(request):
    statuses = MaintenanceStatus.objects.order_by("name")
    return render(request, "printers/maintenance_status_list.html", {"statuses": statuses})


@login_required
def maintenance_status_create(request):
    if request.method == "POST":
        form = MaintenanceStatusForm(request.POST)
        if form.is_valid():
            status_item = form.save()
            messages.success(request, f"Status '{status_item.name}' cadastrado.")
            return redirect(reverse("printers:maintenance-status-list"))
    else:
        form = MaintenanceStatusForm()
    return render(request, "printers/maintenance_status_form.html", {"form": form})


@login_required
def maintenance_status_update(request, pk):
    status_item = get_object_or_404(MaintenanceStatus, pk=pk)
    if request.method == "POST":
        form = MaintenanceStatusForm(request.POST, instance=status_item)
        if form.is_valid():
            form.save()
            messages.success(request, f"Status '{status_item.name}' atualizado.")
            return redirect(reverse("printers:maintenance-status-list"))
    else:
        form = MaintenanceStatusForm(instance=status_item)
    return render(
        request,
        "printers/maintenance_status_form.html",
        {"form": form, "status_item": status_item},
    )


@login_required
def maintenance_status_delete(request, pk):
    status_item = get_object_or_404(MaintenanceStatus, pk=pk)
    if request.method == "POST":
        status_item.delete()
        messages.success(request, "Status removido.")
        return redirect(reverse("printers:maintenance-status-list"))
    return render(
        request,
        "printers/maintenance_status_confirm_delete.html",
        {"status_item": status_item},
    )


@login_required
def maintenance_provider_list(request):
    providers = MaintenanceProvider.objects.order_by("supplier_name")
    return render(
        request,
        "printers/maintenance_provider_list.html",
        {"providers": providers},
    )


@login_required
def maintenance_provider_create(request):
    if request.method == "POST":
        form = MaintenanceProviderForm(request.POST)
        if form.is_valid():
            provider = form.save()
            messages.success(request, f"Local de manutencao '{provider.supplier_name}' cadastrado.")
            return redirect(reverse("printers:maintenance-provider-list"))
    else:
        form = MaintenanceProviderForm()
    return render(request, "printers/maintenance_provider_form.html", {"form": form})


@login_required
def maintenance_provider_update(request, pk):
    provider = get_object_or_404(MaintenanceProvider, pk=pk)
    if request.method == "POST":
        form = MaintenanceProviderForm(request.POST, instance=provider)
        if form.is_valid():
            form.save()
            messages.success(request, f"Local de manutencao '{provider.supplier_name}' atualizado.")
            return redirect(reverse("printers:maintenance-provider-list"))
    else:
        form = MaintenanceProviderForm(instance=provider)
    return render(
        request,
        "printers/maintenance_provider_form.html",
        {"form": form, "provider": provider},
    )


@login_required
def maintenance_provider_delete(request, pk):
    provider = get_object_or_404(MaintenanceProvider, pk=pk)
    if request.method == "POST":
        provider.delete()
        messages.success(request, "Local de manutencao removido.")
        return redirect(reverse("printers:maintenance-provider-list"))
    return render(
        request,
        "printers/maintenance_provider_confirm_delete.html",
        {"provider": provider},
    )


@login_required
def collaborator_list(request):
    collaborators = Collaborator.objects.select_related("user").order_by("full_name")
    return render(
        request,
        "printers/collaborator_list.html",
        {"collaborators": collaborators},
    )


@login_required
def collaborator_create(request):
    if request.method == "POST":
        form = CollaboratorForm(request.POST)
        if form.is_valid():
            collaborator = form.save()
            messages.success(request, f"Colaborador '{collaborator.full_name}' cadastrado.")
            return redirect(reverse("printers:collaborator-list"))
    else:
        form = CollaboratorForm()
    return render(
        request,
        "printers/collaborator_form.html",
        {"form": form},
    )


class AppLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = LoginForm


@login_required
def app_logout(request):
    logout(request)
    messages.info(request, "Sessão encerrada com sucesso.")
    return redirect(reverse("printers:login"))
