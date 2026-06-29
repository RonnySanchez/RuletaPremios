import json

from django.contrib import admin
from django import forms
from django.utils.html import format_html, mark_safe
from django.urls import reverse
from .models import Encuesta, TicketConsulta, Pregunta, Opcion, PreguntaOpcion, EncuestaPregunta, Respuesta, TicketVentasEnLinea, Tienda, Pais, Region, Premio, Tienda, TiendaPremio, FormularioEncFija, TemaRuleta, EncuestaFija, EncuestaFijaRespuesta, EncuestaFijaPremio
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from import_export.admin import ImportExportModelAdmin


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
    class Meta:
        model = TemaRuleta
        fields = '__all__'
        widgets = {
            field: ColorPickerTextWidget()
            for field in TEMA_RULETA_COLOR_FIELDS
        }


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
            'all': ('encuestas/admin/tema_ruleta_color_picker.css',)
        }
        js = ('encuestas/admin/tema_ruleta_color_picker.js',)



class PremioResources(resources.ModelResource):
    fields = ('nombre', 'id', 'es_premio')
    class Meta:
        model = Premio



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
        # Usamos el 'id' como llave maestra, aunque no venga en el Excel
        import_id_fields = ('id',) 
        # Incluimos todos tus campos personalizados
        fields = ('id', 'tienda', 'premio', 'cantidad', 'monto_minimo_premio', 'fecha_activacion', 'visible', 'orden')
        skip_unchanged = True

    # La función que intercepta los datos para inyectar el ID y actualizar el stock
    def before_import_row(self, row, **kwargs):
        # 1. Limpiar el campo booleano 'visible' por si acaso
        if 'visible' in row and row['visible'] is not None:
            val = str(row['visible']).strip().lower()
            row['visible'] = val in ['1', 'true', 'sí', 'si', 'yes', 'v']

        tienda_nombre = row.get('tienda__nombre')
        premio_nombre = row.get('premio__nombre')

        if tienda_nombre and premio_nombre:
            tienda_nombre = str(tienda_nombre).strip()
            premio_nombre = str(premio_nombre).strip()

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
        widget=ForeignKeyWidget(Pais, field='nombre')
    )
    region = fields.Field(
        column_name='region__nombre',
        attribute='region',
        widget=ForeignKeyWidget(Region, field='nombre')
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
            val = str(row['activa']).strip().lower()
            row['activa'] = val in ['1', 'true', 'sí', 'si', 'yes', 'v']

        # B. Limpiar y Auto-Crear Países faltantes para que no crashee
        pais_nombre = row.get('pais__nombre')
        if pais_nombre:
            # Si el país que viene en el Excel no existe en tu BD, lo crea en silencio
            Pais.objects.get_or_create(nombre=pais_nombre.strip())

        # C. Limpiar y Auto-Crear Regiones faltantes
        region_nombre = row.get('region__nombre')
        if region_nombre:
            Region.objects.get_or_create(nombre=region_nombre.strip())


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
class EncuestaFijaRespuestaAdmin(ImportExportModelAdmin):
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
class EncuestaFijaPremioAdmin(ImportExportModelAdmin):
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

