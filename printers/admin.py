from django.contrib import admin

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


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ("name", "state")
    search_fields = ("name", "state")


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "city")
    list_filter = ("city",)
    search_fields = ("name", "city__name")


@admin.register(LocationCatalog)
class LocationCatalogAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(SectorCatalog)
class SectorCatalogAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Sector)
class SectorAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "location")
    list_filter = ("city",)
    search_fields = ("name", "city__name", "location__name")


@admin.register(PrinterModel)
class PrinterModelAdmin(admin.ModelAdmin):
    list_display = ("name", "manufacturer")
    search_fields = ("name", "manufacturer")


@admin.register(Printer)
class PrinterAdmin(admin.ModelAdmin):
    list_display = ("serial_number", "patrimony_number", "barcode", "model", "city", "sector", "location", "installed_at")
    list_filter = ("city", "sector", "model")
    search_fields = (
        "serial_number",
        "serial_number_scan_text",
        "patrimony_number",
        "barcode",
        "barcode_scan_text",
        "model__name",
        "model__manufacturer",
        "city__name",
        "sector__name",
    )
    autocomplete_fields = ("model", "city", "sector")


@admin.register(MaintenanceStatus)
class MaintenanceStatusAdmin(admin.ModelAdmin):
    list_display = ("name", "flow")
    list_filter = ("flow",)
    search_fields = ("name",)


@admin.register(MaintenanceProvider)
class MaintenanceProviderAdmin(admin.ModelAdmin):
    list_display = ("supplier_name", "city", "state", "phone", "contact_name")
    list_filter = ("state", "city")
    search_fields = ("supplier_name", "city", "state", "phone", "contact_name", "address", "neighborhood")


@admin.register(PrinterInstallationHistory)
class PrinterInstallationHistoryAdmin(admin.ModelAdmin):
    list_display = ("printer", "city", "location_name", "sector", "installed_at", "removed_at")
    list_filter = ("city", "sector")
    search_fields = ("printer__serial_number", "city__name", "location_name", "sector__name")
    autocomplete_fields = ("printer", "city", "sector")


@admin.register(PrinterMaintenance)
class PrinterMaintenanceAdmin(admin.ModelAdmin):
    list_display = (
        "printer",
        "status_catalog",
        "origin_city",
        "origin_sector",
        "maintenance_provider",
        "solution_description",
        "started_at",
        "finished_at",
    )
    list_filter = ("status_catalog", "origin_city", "maintenance_provider")
    search_fields = (
        "printer__serial_number",
        "origin_city__name",
        "origin_sector__name",
        "defect_description",
        "maintenance_provider__supplier_name",
    )
    autocomplete_fields = ("printer", "status_catalog", "maintenance_provider")


@admin.register(Collaborator)
class CollaboratorAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "email", "role", "phone", "created_at")
    search_fields = ("full_name", "email", "role", "user__username")
    list_filter = ("role",)
