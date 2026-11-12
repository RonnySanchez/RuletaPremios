import secrets
from datetime import datetime

from django.contrib import admin

from .models import (
    CategoriaCupon,
    Cupon,
    PlantillaCuponPremio,
    PresentacionCupon,
    UsoCupon,
)


def generar_codigo_manual(longitud=6, prefijo="CUPON"):
    aleatorio = "".join(secrets.choice("0123456789") for _ in range(longitud))
    return f"{prefijo}-{aleatorio}-{datetime.now():%Y}"


@admin.register(CategoriaCupon)
class CategoriaCuponAdmin(admin.ModelAdmin):
    list_display = ("nombre",)
    search_fields = ("nombre",)


@admin.register(PresentacionCupon)
class PresentacionCuponAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo_efsystem", "activo")
    list_filter = ("activo",)
    search_fields = ("nombre", "codigo_efsystem")


@admin.register(PlantillaCuponPremio)
class PlantillaCuponPremioAdmin(admin.ModelAdmin):
    list_display = (
        "premio",
        "activo",
        "tipo",
        "valor",
        "tipo_vigencia",
        "transferible",
        "formato_codigo",
    )
    list_filter = ("activo", "tipo", "tipo_vigencia", "transferible")
    search_fields = ("premio__nombre", "formato_codigo")
    filter_horizontal = ("categorias", "presentaciones")
    fieldsets = (
        ("Premio", {"fields": ("premio", "activo")}),
        ("Beneficio", {"fields": ("tipo", "valor", "minimo_compra", "maximo_descuento")}),
        ("Aplicabilidad", {"fields": ("categorias", "presentaciones", "cantidad_maxima_productos", "transferible")}),
        (
            "Vigencia",
            {"fields": ("tipo_vigencia", "dias_vigencia", "fecha_inicio_fija", "fecha_vencimiento_fija")},
        ),
        ("Codigo", {"fields": ("formato_codigo",)}),
    )


class UsoCuponInline(admin.TabularInline):
    model = UsoCupon
    fields = (
        "fecha_uso",
        "usuario_api",
        "tienda",
        "idempotency_key",
        "nro_referencia",
        "monto_total",
        "monto_descuento",
        "cantidad_productos",
        "monto_aplicable",
        "presentacion_codigo",
    )
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Cupon)
class CuponAdmin(admin.ModelAdmin):
    list_display = (
        "codigo",
        "estatus",
        "tipo",
        "valor",
        "vencimiento",
        "transferible",
        "limite_usos",
        "usos_actuales",
    )
    list_filter = ("estatus", "tipo", "transferible", "categorias", "presentaciones")
    search_fields = (
        "codigo",
        "numero_identificacion",
        "premio_ganado__codigo_ticket",
        "categorias__nombre",
        "presentaciones__codigo_efsystem",
    )
    filter_horizontal = ("categorias", "presentaciones")
    readonly_fields = ("usos_actuales", "plantilla_origen", "premio_ganado", "emitido_en")
    inlines = [UsoCuponInline]
    fieldsets = (
        ("Origen", {"fields": ("plantilla_origen", "premio_ganado")}),
        ("Cupon", {"fields": ("codigo", "estatus", "categorias", "presentaciones", "cantidad_maxima_productos")}),
        ("Beneficio", {"fields": ("tipo", "valor", "minimo_compra", "maximo_descuento")}),
        (
            "Titular",
            {"fields": ("transferible", "tipo_identificacion", "numero_identificacion")},
        ),
        ("Validez", {"fields": ("emitido_en", "inicio", "vencimiento", "limite_usos", "usos_actuales")}),
    )

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        initial["codigo"] = generar_codigo_manual()
        return initial

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj:
            fields.append("codigo")
        return tuple(fields)


@admin.register(UsoCupon)
class UsoCuponAdmin(admin.ModelAdmin):
    list_display = (
        "cupon",
        "fecha_uso",
        "tienda",
        "idempotency_key",
        "nro_referencia",
        "monto_total",
        "monto_descuento",
    )
    list_filter = ("fecha_uso", "tienda")
    search_fields = ("cupon__codigo", "idempotency_key", "nro_referencia")
    readonly_fields = [field.name for field in UsoCupon._meta.fields]

    def has_add_permission(self, request):
        return False
