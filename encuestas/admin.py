import json
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.contrib import admin
from django import forms
from django.utils.html import format_html, mark_safe
from django.urls import reverse
from .models import Encuesta, TicketConsulta, Pregunta, Opcion, PreguntaOpcion, EncuestaPregunta, Respuesta, TicketVentasEnLinea, Tienda, Pais, Region, Premio, Tienda, TiendaPremio, FormularioEncFija, TemaRuleta, EncuestaFija, EncuestaFijaRespuesta, EncuestaFijaPremio
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from import_export.admin import ExportMixin, ImportExportModelAdmin


TEMA_RULETA_COLOR_FIELDS = (
    'fondo_ruleta',
    'fondo_premio',
    'fondo_sin_premio',
    'texto_principal',
    'texto_secundario',
    'segmento_1',
    'segmento_2',
    'segmento_3',
    'segmento_4',
    'segmento_5',
    'segmento_6',
    'puntero_inicio',
    'puntero_medio',
    'puntero_fin',
)


TEMA_RULETA_IMAGE_SELECTOR_FIELDS = {
    'imagen_encabezado_ruleta': 'imagen_encabezado_ruleta_existente',
    'imagen_encabezado_premio': 'imagen_encabezado_premio_existente',
    'imagen_fondo_ruleta': 'imagen_fondo_ruleta_existente',
    'imagen_aro_ruleta': 'imagen_aro_ruleta_existente',
}

TEMA_RULETA_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}


def _clean_import_text(value):
    return str(value).strip() if value is not None else ''


def _clean_import_bool(value):
    if value is None:
        return False
    return str(value).strip().lower() in {
        '1', 'true', 'si', 's', 'yes', 'y', 'v', 'verdadero'
    }


class AutoCreateForeignKeyWidget(ForeignKeyWidget):
    def clean(self, value, row=None, **kwargs):
        value = _clean_import_text(value)
        if not value:
            return None
        obj, _ = self.model.objects.get_or_create(**{self.field: value})
        return obj


class RegionByPaisWidget(ForeignKeyWidget):
    def clean(self, value, row=None, **kwargs):
        region_nombre = _clean_import_text(value)
        if not region_nombre:
            return None

        pais_nombre = _clean_import_text((row or {}).get('pais__nombre'))
        if pais_nombre:
            pais, _ = Pais.objects.get_or_create(nombre=pais_nombre)
            region, _ = Region.objects.get_or_create(nombre=region_nombre, pais=pais)
            return region

        return self.model.objects.get(nombre=region_nombre)


def _tema_ruleta_image_choices():
    choices = [('', 'Mantener imagen actual o subir nueva')]
    media_root = Path(settings.MEDIA_ROOT)
    theme_root = media_root / 'ruleta_temas'

    if theme_root.exists():
        for path in sorted(theme_root.rglob('*')):
            if path.is_file() and path.suffix.lower() in TEMA_RULETA_IMAGE_EXTENSIONS:
                relative_path = path.relative_to(media_root).as_posix()
                choices.append((relative_path, relative_path))

    for static_dir in getattr(settings, 'STATICFILES_DIRS', []):
        static_root = Path(static_dir)
        for subdir in ('images', 'img'):
            image_root = static_root / subdir
            if not image_root.exists():
                continue
            for path in sorted(image_root.rglob('*')):
                if path.is_file() and path.suffix.lower() in TEMA_RULETA_IMAGE_EXTENSIONS:
                    relative_path = path.relative_to(static_root).as_posix()
                    value = f'static/{relative_path}'
                    choices.append((value, value))

    return choices


def _build_static_or_media_url(base_url, relative_path):
    return f'{base_url.rstrip("/")}/{quote(relative_path.lstrip("/"), safe="/")}'


def _tema_ruleta_image_path(value):
    if not value:
        return None

    if value.startswith('static/'):
        relative_path = value.removeprefix('static/')
        for static_dir in getattr(settings, 'STATICFILES_DIRS', []):
            path = Path(static_dir) / relative_path
            if path.exists():
                return path
        return None

    if value.startswith('/static/'):
        return _tema_ruleta_image_path(f'static/{value.removeprefix("/static/")}')

    if value.startswith('/media/'):
        return Path(settings.MEDIA_ROOT) / value.removeprefix('/media/')

    return Path(settings.MEDIA_ROOT) / value


def _tema_ruleta_image_url(value):
    if not value:
        return ''

    if value.startswith('static/'):
        url = _build_static_or_media_url(settings.STATIC_URL, value.removeprefix('static/'))
    elif value.startswith('/static/'):
        url = _build_static_or_media_url(settings.STATIC_URL, value.removeprefix('/static/'))
    elif value.startswith('/media/'):
        url = _build_static_or_media_url(settings.MEDIA_URL, value.removeprefix('/media/'))
    else:
        url = _build_static_or_media_url(settings.MEDIA_URL, value)

    path = _tema_ruleta_image_path(value)
    if path and path.exists():
        return f'{url}?v={int(path.stat().st_mtime)}'

    return url


class ImageChoiceSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        option_value = str(value or '')
        if option_value:
            option['attrs']['data-image-url'] = _tema_ruleta_image_url(option_value)
        return option


class ColorPickerTextWidget(forms.TextInput):
    PRESET_COLORS = [
        '#003468', '#c54954', '#97222d', '#6b96b8',
        '#0d47a1', '#0a367a', '#1e88e5', '#1565c0',
        '#6c757d', '#198754', '#ffc107', '#dc3545',
        '#f4f6f9', '#ffffff', '#eeeeee', '#c9c9c9',
        '#333333', '#111827',
    ]

    def __init__(self, attrs=None, preset_colors=None):
        widget_attrs = {
            'class': 'ruleta-color-source',
            'pattern': r'^#[0-9A-Fa-f]{6}$',
            'placeholder': '#003468',
            'data-preset-colors': json.dumps(preset_colors or self.PRESET_COLORS),
        }
        if attrs:
            widget_attrs.update(attrs)
        super().__init__(attrs=widget_attrs)


class TemaRuletaAdminForm(forms.ModelForm):
    imagen_encabezado_ruleta_existente = forms.ChoiceField(
        label='Seleccionar encabezado de ruleta del servidor',
        required=False,
        choices=(),
        widget=ImageChoiceSelect
    )
    imagen_encabezado_premio_existente = forms.ChoiceField(
        label='Seleccionar encabezado de premio del servidor',
        required=False,
        choices=(),
        widget=ImageChoiceSelect
    )
    imagen_fondo_ruleta_existente = forms.ChoiceField(
        label='Seleccionar fondo de ruleta del servidor',
        required=False,
        choices=(),
        widget=ImageChoiceSelect
    )
    imagen_aro_ruleta_existente = forms.ChoiceField(
        label='Seleccionar aro de ruleta del servidor',
        required=False,
        choices=(),
        widget=ImageChoiceSelect
    )

    class Meta:
        model = TemaRuleta
        fields = '__all__'
        widgets = {
            field: ColorPickerTextWidget()
            for field in TEMA_RULETA_COLOR_FIELDS
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        base_choices = _tema_ruleta_image_choices()

        for image_field, selector_field in TEMA_RULETA_IMAGE_SELECTOR_FIELDS.items():
            choices = list(base_choices)
            current_image = getattr(self.instance, image_field, None)
            current_name = current_image.name if current_image and current_image.name else ''
            if current_name and current_name not in dict(choices):
                choices.insert(1, (current_name, current_name))
            self.fields[selector_field].choices = choices
            self.fields[selector_field].initial = current_name
            self.fields[selector_field].widget.attrs.update({
                'class': 'ruleta-image-source',
            })

    def save(self, commit=True):
        obj = super().save(commit=False)

        for image_field, selector_field in TEMA_RULETA_IMAGE_SELECTOR_FIELDS.items():
            clear_requested = f'{image_field}-clear' in self.data
            selected_image = self.cleaned_data.get(selector_field)
            uploaded_image = self.files.get(image_field)

            if selected_image and not uploaded_image and not clear_requested:
                setattr(obj, image_field, selected_image)

        if commit:
            obj.save()
            self.save_m2m()
        return obj


@admin.register(TemaRuleta)
class TemaRuletaAdmin(admin.ModelAdmin):
    form = TemaRuletaAdminForm
    list_display = (
        'nombre',
        'activo',
        'muestra_fondo_ruleta',
        'muestra_fondo_premio',
        'muestra_fondo_sin_premio',
    )
    list_filter = ('activo',)
    search_fields = ('nombre',)
    readonly_fields = (
        'vista_imagen_encabezado_ruleta',
        'vista_imagen_encabezado_premio',
        'vista_imagen_fondo_ruleta',
        'vista_imagen_aro_ruleta',
    )
    fieldsets = (
        (None, {
            'fields': ('nombre', 'activo')
        }),
        ('Fondos y textos', {
            'fields': (
                'fondo_ruleta',
                'fondo_premio',
                'fondo_sin_premio',
                'texto_principal',
                'texto_secundario',
            )
        }),
        ('Imagenes', {
            'fields': (
                'vista_imagen_encabezado_ruleta',
                'imagen_encabezado_ruleta',
                'imagen_encabezado_ruleta_existente',
                'vista_imagen_encabezado_premio',
                'imagen_encabezado_premio',
                'imagen_encabezado_premio_existente',
                'vista_imagen_fondo_ruleta',
                'imagen_fondo_ruleta',
                'imagen_fondo_ruleta_existente',
                'vista_imagen_aro_ruleta',
                'imagen_aro_ruleta',
                'imagen_aro_ruleta_existente',
            )
        }),
        ('Colores de la ruleta', {
            'fields': (
                'segmento_1',
                'segmento_2',
                'segmento_3',
                'segmento_4',
                'segmento_5',
                'segmento_6',
            )
        }),
        ('Puntero', {
            'fields': (
                'puntero_inicio',
                'puntero_medio',
                'puntero_fin',
            )
        }),
    )

    def _image_preview(self, obj, field_name):
        image_field = getattr(obj, field_name, None)
        if image_field and image_field.name:
            return format_html(
                '<div class="ruleta-theme-image-preview"><img src="{}" alt="" style="width:180px;max-width:180px;height:72px;max-height:72px;object-fit:contain;background:#f6f6f6;border:1px solid #c8c8c8;border-radius:4px;padding:4px;box-sizing:border-box;"><span>{}</span></div>',
                TemaRuleta.image_url(image_field),
                image_field.name
            )
        return "Sin imagen"

    def vista_imagen_encabezado_ruleta(self, obj):
        return self._image_preview(obj, 'imagen_encabezado_ruleta')
    vista_imagen_encabezado_ruleta.short_description = 'Vista encabezado ruleta'

    def vista_imagen_encabezado_premio(self, obj):
        return self._image_preview(obj, 'imagen_encabezado_premio')
    vista_imagen_encabezado_premio.short_description = 'Vista encabezado premio'

    def vista_imagen_fondo_ruleta(self, obj):
        return self._image_preview(obj, 'imagen_fondo_ruleta')
    vista_imagen_fondo_ruleta.short_description = 'Vista fondo ruleta'

    def vista_imagen_aro_ruleta(self, obj):
        return self._image_preview(obj, 'imagen_aro_ruleta')
    vista_imagen_aro_ruleta.short_description = 'Vista aro ruleta'

    def _color_preview(self, value):
        return format_html(
            '<span style="display:inline-block;width:18px;height:18px;border:1px solid #bbb;background:{};vertical-align:middle;margin-right:6px;"></span>{}',
            value,
            value
        )

    def muestra_fondo_ruleta(self, obj):
        return self._color_preview(obj.fondo_ruleta)
    muestra_fondo_ruleta.short_description = 'Fondo ruleta'

    def muestra_fondo_premio(self, obj):
        return self._color_preview(obj.fondo_premio)
    muestra_fondo_premio.short_description = 'Fondo premio'

    def muestra_fondo_sin_premio(self, obj):
        return self._color_preview(obj.fondo_sin_premio)
    muestra_fondo_sin_premio.short_description = 'Fondo sin premio'

    class Media:
        css = {
            'all': (
                f'{settings.STATIC_URL}encuestas/admin/tema_ruleta_color_picker.css?v=20260701-image-preview-fix',
            )
        }
        js = (
            f'{settings.STATIC_URL}encuestas/admin/tema_ruleta_color_picker.js?v=20260701-image-preview-fix',
        )



class PremioResources(resources.ModelResource):
    class Meta:
        model = Premio
        fields = ('id', 'nombre', 'descripcion', 'es_premio', 'imagen')
        export_order = fields
        import_id_fields = ('nombre',)



@admin.register(Premio)
class PremioAdmin(ImportExportModelAdmin):
    resource_class = PremioResources
    list_display = ('nombre', 'vista_previa_imagen', 'es_premio', 'descripcion')
    list_filter = ('es_premio',)
    readonly_fields = ('vista_previa_imagen',) # Muestra la imagen también en el formulario de edición
    search_fields = ('nombre',)

    def vista_previa_imagen(self, obj):
        if obj.imagen:
            return mark_safe(f'<img src="{obj.imagen.url}" width="100" height="100" style="object-fit: contain;" />')
        return "Sin imagen"
    
    vista_previa_imagen.short_description = 'Vista Previa'


class TiendaPremioInline(admin.TabularInline):
    model = TiendaPremio
    extra = 0  # Número de formularios vacíos que se mostrarán por defecto
    fields = ('premio', 'cantidad', 'monto_minimo_premio', 'fecha_activacion', 'visible', 'orden')  # Campos que se mostrarán en el inline
    # Puedes definir 'readonly_fields' si algunos campos no deben ser editables
    sortable_field_name = "orden"


class TiendaPremioResource(resources.ModelResource):
    # Traducimos el nombre de la tienda del Excel al objeto Tienda real
    tienda = fields.Field(
        column_name='tienda__nombre', 
        attribute='tienda',
        widget=ForeignKeyWidget(Tienda, field='nombre')
    )

    # Traducimos el nombre del premio del Excel al objeto Premio real
    premio = fields.Field(
        column_name='premio__nombre',
        attribute='premio',
        widget=ForeignKeyWidget(Premio, field='nombre')
    )

    class Meta:
        model = TiendaPremio
        import_id_fields = ('tienda', 'premio')
        # Incluimos todos tus campos personalizados
        fields = ('id', 'tienda', 'premio', 'cantidad', 'monto_minimo_premio', 'fecha_activacion', 'visible', 'orden')
        skip_unchanged = True

    # La función que intercepta los datos para inyectar el ID y actualizar el stock
    def before_import_row(self, row, **kwargs):
        # 1. Limpiar el campo booleano 'visible' por si acaso
        if 'visible' in row and row['visible'] is not None:
            row['visible'] = _clean_import_bool(row['visible'])

        tienda_nombre = row.get('tienda__nombre')
        premio_nombre = row.get('premio__nombre')

        if tienda_nombre and premio_nombre:
            tienda_nombre = _clean_import_text(tienda_nombre)
            premio_nombre = _clean_import_text(premio_nombre)
            row['tienda__nombre'] = tienda_nombre
            row['premio__nombre'] = premio_nombre

            try:
                # Buscamos la tienda por nombre
                tienda_obj = Tienda.objects.get(nombre=tienda_nombre)
                
                # Buscamos el premio (si no existe, lo crea vacío para no crashear)
                premio_obj, created = Premio.objects.get_or_create(nombre=premio_nombre)

                # Buscamos si ESTA tienda ya tiene asignado ESTE premio
                inventario = TiendaPremio.objects.filter(tienda=tienda_obj, premio=premio_obj).first()

                if inventario:
                    # ¡MAGIA! Inyectamos el ID interno. 
                    # Esto le dice a Django: "Actualiza esta fila, no crees una nueva".
                    row['id'] = inventario.id

            except Tienda.DoesNotExist:
                # Si la tienda no existe, el importador lo marcará como error en el panel
                # de forma amigable, sin tumbar el servidor (Error 500).
                pass

# ---------------------------------------------------------
# 2. EL REGISTRO EN EL ADMIN (Mantenemos el tuyo, solo añadí list_editable)
# ---------------------------------------------------------
@admin.register(TiendaPremio)
class TiendaPremioAdmin(ImportExportModelAdmin):
    resource_class = TiendaPremioResource
    list_display = ('tienda', 'premio', 'cantidad', 'monto_minimo_premio', 'fecha_activacion', 'visible')
    search_fields = ('tienda__nombre', 'premio__nombre')
    list_filter = ('tienda', 'premio', 'visible')
    list_editable = ('cantidad', 'visible') # Esto es muy útil para que cambies stock rápido sin entrar al detalle



@admin.register(Pais)
class PaisAdmin(admin.ModelAdmin):
    list_display = ('nombre',)
    search_fields = ('nombre',)

@admin.register(TicketConsulta)
class TicketConsultaAdmin(admin.ModelAdmin):
    list_display = ('tienda', 'codigo', 'monto')
    search_fields = ('codigo',)
    list_filter = ('tienda',)


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'pais')
    search_fields = ('nombre',)
    list_filter = ('pais',)


class TiendaResources(resources.ModelResource):
    # 1. MANEJO SEGURO DE LLAVES FORÁNEAS
    # Le decimos a Django que busque el objeto País usando el texto de la columna 'pais__nombre'
    pais = fields.Field(
        column_name='pais__nombre',
        attribute='pais',
        widget=AutoCreateForeignKeyWidget(Pais, field='nombre')
    )
    region = fields.Field(
        column_name='region__nombre',
        attribute='region',
        widget=RegionByPaisWidget(Region, field='nombre')
    )

    class Meta:
        model = Tienda
        
        # 2. LÓGICA DE ACTUALIZAR O CREAR (Update or Create)
        # Esto le dice a Django: "Si el id_efsystem ya existe, actualiza esa tienda. Si no, créala".
        import_id_fields = ('nombre',) 
        
        # Agregamos los campos nuevos que mencionaste en el admin para que también se puedan importar
        fields = ('id_efsystem', 'nombre', 'pais', 'region', 'activa', 'monto_minimo_promociones', 'requiere_validacion_ticket')
        
        # Configuraciones de optimización
        skip_unchanged = True  # Ignora las filas que no tienen cambios para ahorrar memoria
        report_skipped = False

    # 3. EL ESCUDO ANTI-ERRORES 500 (Interceptar y Limpiar)
    # Esta función se ejecuta por cada fila del Excel ANTES de que Django intente guardarla.
    def before_import_row(self, row, **kwargs):
        # A. Limpiar el campo booleano 'activa' (A veces el Excel trae 'Verdadero', '1', o 'TRUE')
        if 'activa' in row and row['activa'] is not None:
            row['activa'] = _clean_import_bool(row['activa'])

        if 'requiere_validacion_ticket' in row and row['requiere_validacion_ticket'] is not None:
            row['requiere_validacion_ticket'] = _clean_import_bool(row['requiere_validacion_ticket'])

        if 'nombre' in row:
            row['nombre'] = _clean_import_text(row['nombre'])

        # B. Limpiar y Auto-Crear Países faltantes para que no crashee
        pais_nombre = row.get('pais__nombre')
        if pais_nombre:
            pais_nombre = _clean_import_text(pais_nombre)
            row['pais__nombre'] = pais_nombre
            # Si el país que viene en el Excel no existe en tu BD, lo crea en silencio
            pais_obj, _ = Pais.objects.get_or_create(nombre=pais_nombre)
        else:
            pais_obj = None

        # C. Limpiar y Auto-Crear Regiones faltantes
        region_nombre = row.get('region__nombre')
        if region_nombre:
            region_nombre = _clean_import_text(region_nombre)
            row['region__nombre'] = region_nombre
            if pais_obj:
                Region.objects.get_or_create(nombre=region_nombre, pais=pais_obj)


@admin.register(Tienda)
class TiendaAdmin(ImportExportModelAdmin):
    resource_class = TiendaResources
    list_display = ('nombre', 'monto_minimo_promociones', 'id_efsystem', 'pais', 'region', 'activa', 'encuestasFijas_asignadas', 'encuestasFijas_asignadas_id','requiere_validacion_ticket')
    search_fields = ('nombre', 'pais__nombre', 'region__nombre')
    list_editable = ('activa', 'requiere_validacion_ticket')
    list_filter = ('activa', 'pais', 'region', 'requiere_validacion_ticket')
    inlines = [TiendaPremioInline]  
    readonly_fields = ('encuestasFijas_asignadas','encuestasFijas_asignadas_id',)  # Hace que el campo sea solo de lectura en el formulario de edición

    def encuestasFijas_asignadas(self, obj):
        return obj.encuestasFijas_asignadas()  # Usar el método del modelo para mostrar las encuestas
    encuestasFijas_asignadas.short_description = 'Encuestas Fijas Asignadas'  # Nombre del campo en el admin

    def encuestasFijas_asignadas_id(self, obj):
        return obj.encuestasFijas_asignadas_id()  # Usar el método del modelo para mostrar las encuestas
    encuestasFijas_asignadas_id.short_description = 'ID Encuestas Fijas Asignadas'  # Nombre del campo en el admin



class PreguntaOpcionInline(admin.TabularInline):
    model = PreguntaOpcion
    extra = 1
    fields = ('opcion', 'orden')
    sortable_field_name = 'orden'

    
 #   def get_extra(self, request, obj=None, **kwargs):
 #       # Configura el número de formularios en blanco para agregar nuevas opciones
 #       if obj and obj.tipo_de_pregunta == Pregunta.SELECCION_SIMPLE:
 #           return 1  # Una opción en blanco por defecto
 #       return 0


class EncuestaPreguntaInline(admin.TabularInline):
    model = EncuestaPregunta
    extra = 1
    fields = ('pregunta', 'orden')
    sortable_field_name = 'orden'


@admin.register(Encuesta)
class EncuestaAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'descripcion', 'activa',)
    search_fields = ('titulo',)
    list_filter = ('activa',)
    readonly_fields = ['tiendas_asignadas_enlaces',]

    inlines = [EncuestaPreguntaInline]  # Permite añadir preguntas a la encuesta

    def tiendas_asignadas_enlaces(self, obj):
        """
        Retorna una lista de enlaces a la encuesta para cada tienda asignada.
        """
        tiendas = obj.get_tiendas_asignadas()
        if not tiendas.exists():
            return "No hay tiendas asignadas."
        
        enlaces = ""
        for tienda in tiendas:
            url = reverse('polls', args=[tienda.id, obj.id])
            enlaces += format_html('<a href="{}">{}</a><br>', url, tienda.nombre)
        
        return mark_safe(enlaces)

    tiendas_asignadas_enlaces.short_description = "Enlaces a la encuesta para cada tienda"


@admin.register(Pregunta)
class PreguntaAdmin(admin.ModelAdmin):
    list_display = ('texto', 'tipo_de_pregunta', 'creado_en', 'actualizado_en')
    search_fields = ('texto',)
    list_filter = ('tipo_de_pregunta', 'creado_en', 'actualizado_en')

    inlines = [PreguntaOpcionInline]  # Agrega el inline para gestionar las opciones y su orden

@admin.register(Opcion)
class OpcionAdmin(admin.ModelAdmin):
    list_display = ('texto_de_opcion', 'valor_numerico', 'creado_en', 'actualizado_en')
    search_fields = ('texto_de_opcion',)
    list_filter = ('creado_en', 'actualizado_en')


@admin.register(Respuesta)
class RespuestaAdmin(admin.ModelAdmin):
    list_display = ('encuesta', 'pregunta', 'codigo_ticket', 'texto_de_respuesta', 'opcion', 'creado_en')
    search_fields = ('codigo_ticket', 'texto_de_respuesta')
    list_filter = ('creado_en', 'pregunta', 'opcion')



@admin.register(FormularioEncFija)
class FormularioEncFijaAdmin(admin.ModelAdmin):
    list_display = ('nombre',)
    search_fields = ('nombre',)


@admin.register(EncuestaFija)
class EncuestaFijaAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'descripcion', 'activa', 'tipo_juego', 'tema_ruleta')
    search_fields = ('titulo',)
    list_filter = ('activa', 'tipo_juego', 'tema_ruleta')
    readonly_fields = ['tiendas_asignadas_enlaces_fijas',]
    filter_horizontal = ('tiendas',)
    def tiendas_asignadas_enlaces_fijas(self, obj):
        """
        Retorna una lista de enlaces a la encuesta para cada tienda asignada.
        """
        tiendas = obj.get_tiendas_asignadas()
        if not tiendas.exists():
            return "No hay tiendas asignadas."
        
        enlaces = ""
        for tienda in tiendas:
            url = reverse('fija', args=[tienda.id, obj.id])
            enlaces += format_html('<a href="{}">{}</a><br>', url, tienda.nombre)
        
        return mark_safe(enlaces)
    # Método para mostrar las categorías en la lista de cupones
    def display_tiendas(self, obj):
        return ", ".join([cat.nombre for cat in obj.tiendas.all()])
    
    display_tiendas.short_description = 'Tiendas'

    tiendas_asignadas_enlaces_fijas.short_description = "Enlaces a la encuesta para cada tienda..."

class EncuestaFijaRespuestaResources(resources.ModelResource):

    def dehydrate_pregunta_1_1(self, obj):
        opciones_dict1 = { '1': 'Producto/pedido incompleto', '2': 'Calidad del producto', '3': 'El vendedor puede mejorar su actitud' }
        return opciones_dict1.get(obj.pregunta_1_1, "-") if obj.pregunta_1_1 else "-"

    def dehydrate_pregunta_2_1(self, obj):
        opciones_dict2 = { '1': 'Mejorar productos/ más fragancias', '2': 'Mejorar comunicación', '3': 'Mejorar calidad' }
        return opciones_dict2.get(obj.pregunta_2_1, '-') if obj.pregunta_2_1 else '-'

    def dehydrate_pregunta_3_1(self, obj):
        opciones_dict3 = { '1': 'Buena comunicación', '2': 'Excelente calidad', '3': 'Producto que necesitaba' }
        return opciones_dict3.get(obj.pregunta_3_1, '-') if obj.pregunta_3_1 else '-'


    class Meta:
        model = EncuestaFijaRespuesta
        # Actualizamos los campos a exportar
        fields = (
            'id', 'nombre', 'apellidos', 'telefono', 'codigo_ticket', 'fnac', 
            'correo', 'DNI', 'acepPolPriv', 'acepProm', 'fecha_respuesta', 
            'tienda__nombre', 
            'valoracion_producto', 'valoracion_atencion', 
            'probabilidad_recomendacion', 'comentarios_adicionales',
            'calificacion', 'pregunta_1_1', 'pregunta_1_2', 'pregunta_2_1', 
            'pregunta_2_2', 'pregunta_3_1',
        )
        export_order = fields # Mantenemos el orden




@admin.register(EncuestaFijaRespuesta)
class EncuestaFijaRespuestaAdmin(ExportMixin, admin.ModelAdmin):
    resource_class = EncuestaFijaRespuestaResources
    # Visualización con columnas individuales para cada valoración
    list_display = (
        'nombre', 
        'apellidos', 
        'tienda',
        'fecha_respuesta',
        'valoracion_producto',      # Columna para valoración de producto (nueva)
        'valoracion_atencion',      # Columna para valoración de atención (nueva)
        'probabilidad_recomendacion', # Columna para recomendación (nueva)
        'calificacion',             # Columna para calificación NPS (antigua)
    )
    search_fields = ('nombre', 'apellidos', 'codigo_ticket', 'DNI', 'correo')
    # Actualizamos los filtros
    # Añadimos las nuevas valoraciones a los filtros para más comodidad
    list_filter = (
        'fecha_respuesta', 
        'encuesta_fija', 
        'tienda',
        'valoracion_producto',
        'valoracion_atencion',
        'probabilidad_recomendacion',
        'calificacion',
    )

class EncuestaFijaPremioResources(resources.ModelResource):
    # fields = ('nombre', 'apellidos', 'codigo_ticket', 'DNI', 'premio', 'fecha_respuesta', 'tienda',)
    class Meta:
        fields = ('nombre', 'apellidos', 'codigo_ticket', 'DNI', 'premio__nombre', 'fecha_respuesta', 'tienda__nombre',)
        model = EncuestaFijaPremio

@admin.register(EncuestaFijaPremio)
class EncuestaFijaPremioAdmin(ExportMixin, admin.ModelAdmin):
    resource_class = EncuestaFijaPremioResources
    # Campos que se mostrarán en la lista del panel administrativo
    list_display = ('nombre', 'apellidos', 'codigo_ticket', 'DNI', 'premio', 'fecha_respuesta', 'tienda')
    # Añadir barra de búsqueda por los campos que desees
    search_fields = ('nombre', 'apellidos', 'codigo_ticket', 'DNI', 'premio__nombre')
    #list_editable = ('tienda',)



@admin.register(TicketVentasEnLinea)
class TicketVentasEnLineaAdmin(admin.ModelAdmin):
    list_display = (
        'nro_ticket',
        'tienda',
        'encuesta_fija',
        'utilizado',
        'vigencia',
        'enlace_encuesta' # Mostramos el método que creamos en el modelo
    )
    list_filter = (
        'utilizado',
        'vigencia',
        'tienda',
        'encuesta_fija'
    )
    search_fields = ('nro_ticket',)
    # Hacemos que la fecha sea más fácil de leer
    readonly_fields = ['enlace_encuesta', 'creado_en',]

