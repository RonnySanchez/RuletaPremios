import random
from datetime import date
from django.conf import settings
from django.utils import timezone
from django.urls import reverse
from decimal import Decimal
from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils.html import format_html
from django.utils.text import slugify


class Pais(models.Model):
    nombre = models.CharField(max_length=100)

    class Meta:
        verbose_name = "País"
        verbose_name_plural = "Paises"

    def __str__(self):
        return self.nombre

class Region(models.Model):
    nombre = models.CharField(max_length=100)
    pais = models.ForeignKey(Pais, on_delete=models.CASCADE, related_name='regiones')

    class Meta:
        verbose_name = "Región"
        verbose_name_plural = "Regiones"
        
    def __str__(self):
        return f'{self.nombre} - {self.pais.nombre}'
    
class Tienda(models.Model):
    nombre = models.CharField(max_length=255)
    pais = models.ForeignKey(Pais, on_delete=models.CASCADE, related_name='tiendas')
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name='tiendas', null=True, blank=True)
    activa = models.BooleanField(default=True)
    id_efsystem = models.DecimalField(null=True, blank=True, max_digits=3, decimal_places=0)
    """  Campo para validar premio para ruleta
    """
    monto_minimo_promociones = models.DecimalField(
        "Monto mínimo para habilitar promociones",
        max_digits=10,
        decimal_places=2,
        default=0
    )

    requiere_validacion_ticket = models.BooleanField(
        "¿Requiere validación de ticket online?",
        default=False,
        help_text="Marcar si esta tienda (ej. Tienda Online) debe validar el ticket contra la tabla de Ventas en Línea."
    )

    def __str__(self):
        return self.nombre


    def __str__(self):
        return self.nombre

    def encuestasFijas_asignadas(self):
        return ', '.join([encuesta_fija.titulo for encuesta_fija in self.encuestasfijas.all()])

    def encuestasFijas_asignadas_id(self):
        return ', '.join([f'{encuesta_fija.id}' for encuesta_fija in self.encuestasfijas.all()])
    
    def premios_stock(self):
        """
        Retorna la cantidad total de premios en stock para esta tienda.
        Suma el campo 'cantidad' de todos los objetos relacionados en TiendaPremio.
        """
        return sum(tp.cantidad for tp in self.tienda_premios.all())
    
    def permite_premios_para(self, monto: Decimal) -> bool:
        """
        Devuelve True si el monto cumple el mínimo para esta tienda.
        """
        return monto >= self.monto_minimo_promociones


class TicketConsulta(models.Model):
    tienda    = models.ForeignKey(Tienda, on_delete=models.CASCADE)
    codigo    = models.CharField(max_length=255)
    monto     = models.DecimalField(max_digits=10, decimal_places=2)
    creado_en = models.DateTimeField(auto_now_add=True)



class Pregunta(models.Model):
    TIPO_PREGUNTA = (
        ('texto', 'Texto'),
        ('numerico', 'Numérico'),
        ('seleccion_simple', 'Selección Simple'),
    )
    
    texto = models.CharField(max_length=255)
    tipo_de_pregunta = models.CharField(max_length=20, choices=TIPO_PREGUNTA)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.texto

class Opcion(models.Model):
    texto_de_opcion = models.CharField(max_length=255)
    valor_numerico = models.DecimalField(max_digits=10, decimal_places=0, default=1)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Opción"
        verbose_name_plural = "Opciones"

    def __str__(self):
        return f'{self.texto_de_opcion} (Valor: {self.valor_numerico})'

class PreguntaOpcion(models.Model):
    pregunta = models.ForeignKey(Pregunta, on_delete=models.CASCADE, related_name='pregunta_opciones')
    opcion = models.ForeignKey(Opcion, on_delete=models.CASCADE, related_name='pregunta_opciones')
    orden = models.PositiveIntegerField()

    class Meta:
        verbose_name = "Opción de Pregunta"
        verbose_name_plural = "Opciones de Preguntas"
        unique_together = ('pregunta', 'opcion')
        ordering = ['orden']

    def __str__(self):
        return f'Opción {self.opcion.texto_de_opcion} en Pregunta {self.pregunta.texto}'

class Encuesta(models.Model):
    titulo = models.CharField(max_length=255)
    descripcion = models.TextField()
    activa = models.BooleanField(default=True)
    tiendas = models.ManyToManyField(Tienda, related_name='encuestas', blank=True)
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name='encuestas', null=True, blank=True)
    pais = models.ForeignKey(Pais, on_delete=models.CASCADE, related_name='encuestas', null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.titulo
    
    def save(self, *args, **kwargs):
        # Lógica de prioridad
        if self.tiendas.exists():
            self.region = None
            self.pais = None
        elif self.region:
            self.pais = None
        super().save(*args, **kwargs)

    def get_tiendas_asignadas(self):
        """
        Devuelve un queryset con las tiendas a las que se aplica la encuesta.
        Prioridad:
        1. Si tiene tiendas asignadas, devolver esas tiendas.
        2. Si tiene una región asignada, devolver las tiendas de esa región.
        3. Si tiene un país asignado, devolver las tiendas de ese país.
        """
        if self.tiendas.exists():
            return self.tiendas.all()  # Tiendas asignadas directamente
        elif self.region:
            return Tienda.objects.filter(region=self.region)  # Tiendas de la región asignada
        elif self.pais:
            return Tienda.objects.filter(pais=self.pais)  # Tiendas del país asignado
        else:
            return Tienda.objects.none()  # No hay tiendas asignadas


class EncuestaPregunta(models.Model):
    encuesta = models.ForeignKey(Encuesta, on_delete=models.CASCADE, related_name='encuesta_preguntas')
    pregunta = models.ForeignKey(Pregunta, on_delete=models.CASCADE, related_name='encuestas')
    orden = models.PositiveIntegerField()

    class Meta:
        unique_together = ('encuesta', 'pregunta')
        ordering = ['orden']

    def __str__(self):
        return f'Pregunta {self.pregunta.texto} en Encuesta {self.encuesta.titulo}'

class Respuesta(models.Model):
    encuesta = models.ForeignKey(Encuesta, on_delete=models.CASCADE, related_name='respuestas')
    pregunta = models.ForeignKey(Pregunta, on_delete=models.CASCADE, related_name='respuestas')
    codigo_ticket = models.CharField(max_length=255)
    texto_de_respuesta = models.TextField(null=True, blank=True)
    opcion = models.ForeignKey(Opcion, on_delete=models.CASCADE, related_name='respuestas', null=True, blank=True)
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='respuestas')
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Respuesta {self.codigo_ticket} - Pregunta: {self.pregunta.texto}'

class Premio(models.Model):
    nombre = models.CharField(max_length=255, unique=True)
    descripcion = models.TextField(null=True, blank=True)
    es_premio = models.BooleanField(default=True, verbose_name="¿Es un premio real?")

    # --- CAMBIO AQUÍ: AÑADIR EL CAMPO DE IMAGEN ---
    imagen = models.ImageField(
        upload_to='premios/',  # Guarda las imágenes en la carpeta 'media/premios/'
        null=True,
        blank=True,
        verbose_name="Imagen del Producto"
    )

    class Meta:
        verbose_name = "Premio"
        verbose_name_plural = "Premios"

    def __str__(self):
        return self.nombre


class TiendaPremio(models.Model):
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='tienda_premios')
    premio = models.ForeignKey(Premio, on_delete=models.CASCADE, related_name='premios_tienda')
    cantidad = models.PositiveIntegerField()
    monto_minimo_premio = models.DecimalField(
        "Monto mínimo para premio",
        max_digits=10,
        decimal_places=2,
        default=0
    )
    visible = models.BooleanField(default=False, verbose_name="Visible en lista de premios")
    orden = models.PositiveIntegerField(
        default=0,
        blank=False,
        null=False,
        db_index=True  # Indexar para mejorar el rendimiento de la ordenación
    )

    fecha_activacion = models.DateField(
        null=True, 
        blank=True, 
        verbose_name="Activo desde",
        help_text="El premio no saldrá sorteado antes de esta fecha."
    )


    class Meta:
        ordering = ['orden']
        verbose_name = "Premio de tienda"
        verbose_name_plural = "Premios de tienda"
        unique_together = ('tienda', 'premio')

    def __str__(self):
        return f'{self.tienda.nombre} - {self.premio.nombre} (Cantidad: {self.cantidad})'

    def clean(self):
        if self.premio_id and not self.premio.es_premio and self.monto_minimo_premio != Decimal('0'):
            raise ValidationError({
                'monto_minimo_premio': 'Los premios no reales deben tener monto mínimo igual a 0.'
            })

    def save(self, *args, **kwargs):
        if self.premio_id and not self.premio.es_premio:
            self.monto_minimo_premio = Decimal('0')
        super().save(*args, **kwargs)


    def obtener_premios_y_probabilidades(self, monto: Decimal):
        """
        Obtiene los premios disponibles y sus probabilidades basadas en el stock.
        """
        premios_qs = self.tienda_premios.all()
        cantidades = [
            tp.stock_disponible(monto)
            for tp in premios_qs
        ]
        """ total_stock = sum(premio.cantidad for premio in premios) """
        total_stock = sum(cantidades)

        if total_stock <= 0:
            return []
        
        
        # 4) construimos la lista de (Premio, probabilidad)
        resultados = []
        for tp, c in zip(premios_qs, cantidades):
            prob = (c / total_stock) if c > 0 else 0
            resultados.append((tp.premio, prob))        
        
        return resultados
        
        """
        premios_y_probabilidades = [
            (premio.premio, premio.cantidad / total_stock) for premio in premios 
        ]
        return premios_y_probabilidades """

    def sortear_premio(self, monto: Decimal):
        """
        Realiza un sorteo basado en las probabilidades y reduce el stock del premio seleccionado.
        """
        premios_y_probabilidades = self.obtener_premios_y_probabilidades(monto)
        if not premios_y_probabilidades:
            raise ValueError("No hay premios disponibles para sortear.")

        premios, probabilidades = zip(*premios_y_probabilidades)
        premio_seleccionado = random.choices(premios, weights=probabilidades, k=1)[0]
        
        # Reducir el stock del premio seleccionado
        tienda_premio = self.tienda_premios.get(premio=premio_seleccionado)
        if tienda_premio.cantidad > 0:
            tienda_premio.cantidad -= 1
            tienda_premio.save()
        else:
            raise ValueError("El premio seleccionado está agotado.")
        
        return premio_seleccionado

    def stock_disponible(self, monto: Decimal) -> int:
        """
        Calcula el stock real considerando monto y fecha de activación.
        """
        # 1. Validar monto mínimo
        if monto < self.monto_minimo_premio:
            return 0
        
        # 2. Validar fecha de activación
        if self.fecha_activacion and self.fecha_activacion > timezone.now().date():
            return 0
            
        return self.cantidad
    
    @transaction.atomic
    def sortear_premio_seguro(self, monto: Decimal):
        """
        Lógica de sorteo con bloqueo de base de datos para evitar sobre-entrega.
        """
        # Obtenemos todos los premios de la tienda bloqueando las filas para esta transacción
        premios_qs = TiendaPremio.objects.select_for_update().filter(tienda=self.tienda)
        
        candidatos = []
        pesos = []
        
        for tp in premios_qs:
            stock = tp.stock_disponible(monto)
            if stock > 0:
                candidatos.append(tp)
                pesos.append(stock)
        
        if not candidatos:
            return None # O manejar un "No ganó" por defecto de emergencia

        # Sorteo ponderado
        seleccionado = random.choices(candidatos, weights=pesos, k=1)[0]
        
        # Descontar stock (sea premio o no, el stock de 'No ganó' también se consume para la probabilidad)
        if seleccionado.cantidad > 0:
            seleccionado.cantidad -= 1
            seleccionado.save()
            
        return seleccionado.premio

class FormularioEncFija(models.Model):
    nombre = models.CharField(max_length=100)

    class Meta:
        verbose_name = "Form Encuesta Fija"
        verbose_name_plural = "Form Encuestas Fijas"

    def __str__(self):
        return self.nombre


hex_color_validator = RegexValidator(
    regex=r'^#[0-9A-Fa-f]{6}$',
    message='Ingrese un color hexadecimal valido, por ejemplo #003468.'
)


def color_field(verbose_name, default):
    return models.CharField(
        verbose_name,
        max_length=7,
        default=default,
        validators=[hex_color_validator],
        help_text='Formato #RRGGBB'
    )


def tema_ruleta_upload_to(instance, filename):
    tema = slugify(instance.nombre) or "tema"
    return f'ruleta_temas/{tema}/{filename}'


class TemaRuleta(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    fondo_ruleta = color_field("Fondo de ruleta", "#003468")
    fondo_premio = color_field("Fondo con premio", "#003468")
    fondo_sin_premio = color_field("Fondo sin premio", "#003468")
    texto_principal = color_field("Texto principal", "#eeeeee")
    texto_secundario = color_field("Texto secundario", "#c9c9c9")
    segmento_1 = color_field("Segmento 1", "#c54954")
    segmento_2 = color_field("Segmento 2", "#003468")
    segmento_3 = color_field("Segmento 3", "#97222d")
    segmento_4 = color_field("Segmento 4", "#6b96b8")
    segmento_5 = color_field("Segmento 5", "#e1253c")
    segmento_6 = color_field("Segmento 6", "#97a1a7")
    puntero_inicio = color_field("Puntero inicio", "#e1253c")
    puntero_medio = color_field("Puntero medio", "#c54954")
    puntero_fin = color_field("Puntero fin", "#97222d")
    imagen_encabezado_ruleta = models.ImageField(
        "Imagen de encabezado de ruleta",
        upload_to=tema_ruleta_upload_to,
        max_length=255,
        null=True,
        blank=True,
        help_text="Banner superior usado en la pantalla de la ruleta."
    )
    imagen_encabezado_premio = models.ImageField(
        "Imagen de encabezado de premio ganado",
        upload_to=tema_ruleta_upload_to,
        max_length=255,
        null=True,
        blank=True,
        help_text="Banner superior usado en la pantalla de premio ganado."
    )
    imagen_fondo_ruleta = models.ImageField(
        "Imagen de fondo de ruleta",
        upload_to=tema_ruleta_upload_to,
        max_length=255,
        null=True,
        blank=True,
        help_text="Imagen de fondo para la ruleta y su simulador. Si queda vacia se usa el color de fondo."
    )
    imagen_aro_ruleta = models.ImageField(
        "Imagen de aro de ruleta",
        upload_to=tema_ruleta_upload_to,
        max_length=255,
        null=True,
        blank=True,
        help_text="Imagen superpuesta que forma el aro exterior de la ruleta."
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Tema de Ruleta"
        verbose_name_plural = "Temas de Ruleta"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    @classmethod
    def default_css_variables(cls):
        return {
            '--ruleta-bg-color': '#003468',
            '--premio-bg-color': '#003468',
            '--sin-premio-bg-color': '#003468',
            '--simulador-bg-color': '#003468',
            '--ef-text': '#eeeeee',
            '--ef-muted-text': '#c9c9c9',
            '--wheel-color-1': '#c54954',
            '--wheel-color-2': '#003468',
            '--wheel-color-3': '#97222d',
            '--wheel-color-4': '#6b96b8',
            '--wheel-color-5': '#e1253c',
            '--wheel-color-6': '#97a1a7',
            '--pointer-color-1': '#e1253c',
            '--pointer-color-2': '#c54954',
            '--pointer-color-3': '#97222d',
            '--ruleta-header-image': 'var(--ruleta-header-image-default)',
            '--premio-header-image': 'var(--premio-header-image-default)',
            '--ruleta-bg-image': 'none',
            '--ruleta-aro-image': 'var(--ruleta-aro-image-default)',
        }

    @staticmethod
    def image_url(image_field):
        if image_field and image_field.name:
            if image_field.name.startswith('static/'):
                return f'{settings.STATIC_URL}{image_field.name.removeprefix("static/")}'
            if image_field.name.startswith('/static/') or image_field.name.startswith('/media/'):
                return image_field.name
            return image_field.url
        return ''

    @classmethod
    def _image_css_value(cls, image_field, fallback):
        image_url = cls.image_url(image_field)
        if image_url:
            return f'url("{image_url}")'
        return fallback

    def css_variables(self):
        variables = self.default_css_variables()
        variables.update({
            '--ruleta-bg-color': self.fondo_ruleta,
            '--premio-bg-color': self.fondo_premio,
            '--sin-premio-bg-color': self.fondo_sin_premio,
            '--simulador-bg-color': self.fondo_ruleta,
            '--ef-text': self.texto_principal,
            '--ef-muted-text': self.texto_secundario,
            '--wheel-color-1': self.segmento_1,
            '--wheel-color-2': self.segmento_2,
            '--wheel-color-3': self.segmento_3,
            '--wheel-color-4': self.segmento_4,
            '--wheel-color-5': self.segmento_5,
            '--wheel-color-6': self.segmento_6,
            '--pointer-color-1': self.puntero_inicio,
            '--pointer-color-2': self.puntero_medio,
            '--pointer-color-3': self.puntero_fin,
            '--ruleta-header-image': self._image_css_value(
                self.imagen_encabezado_ruleta,
                'var(--ruleta-header-image-default)'
            ),
            '--premio-header-image': self._image_css_value(
                self.imagen_encabezado_premio,
                'var(--premio-header-image-default)'
            ),
            '--ruleta-bg-image': self._image_css_value(self.imagen_fondo_ruleta, 'none'),
            '--ruleta-aro-image': self._image_css_value(
                self.imagen_aro_ruleta,
                'var(--ruleta-aro-image-default)'
            ),
        })
        return variables


class EncuestaFija(models.Model):
    class TipoJuego(models.TextChoices):
        RULETA = 'RULETA', 'Ruleta de Premios'
        CAJAS = 'CAJAS', 'Cajas de Regalos'

    titulo = models.CharField(max_length=255)
    descripcion = models.TextField()
    activa = models.BooleanField(default=True)
    encuestafija = models.ForeignKey(FormularioEncFija, on_delete=models.CASCADE, related_name='encuestasfijas', null=True, blank=True, verbose_name='Encuesta Fija' )
    tipo_juego = models.CharField(
        max_length=10,
        choices=TipoJuego.choices,
        default=TipoJuego.RULETA, # Se asignará 'Ruleta' por defecto
        verbose_name="Tipo de Juego Post-Encuesta"
    )
    tema_ruleta = models.ForeignKey(
        TemaRuleta,
        on_delete=models.SET_NULL,
        related_name='encuestas_fijas',
        null=True,
        blank=True,
        verbose_name="Tema visual de ruleta",
        help_text="Define los colores usados por la ruleta y sus pantallas de resultado."
    )
    tiendas = models.ManyToManyField(Tienda, related_name='encuestasfijas', blank=True)
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name='encuestasfijas', null=True, blank=True)
    pais = models.ForeignKey(Pais, on_delete=models.CASCADE, related_name='encuestasfijas', null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    encabezado = models.TextField(verbose_name="Text de encabezado de ticket", blank=True)
    texto = models.TextField(verbose_name="Text de pie de página de ticket", blank=True)
    
    def __str__(self):
        return self.titulo

    def obtener_tema_ruleta_vars(self):
        if self.tema_ruleta_id and self.tema_ruleta:
            return self.tema_ruleta.css_variables()
        return TemaRuleta.default_css_variables()
    
    class Meta:
        verbose_name = "Encuesta Fija"
        verbose_name_plural = "Encuestas Fijas"

    
 #   def save(self, *args, **kwargs):
 #       super().save(*args, **kwargs)

        # Lógica de prioridad
 #       if self.tiendas.exists():
 #           self.region = None
 #           self.pais = None
 #       elif self.region:
 #           self.pais = None
 #       super().save(*args, **kwargs)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Lógica de prioridad se ejecuta primero
        if self.tiendas.exists():
            self.region = None
            self.pais = None
        elif self.region:
            self.pais = None
        
        # Se guarda una sola vez con los datos ya corregidos
        super().save(*args, **kwargs)


    def get_tiendas_asignadas(self):
        """
        Devuelve un queryset con las tiendas a las que se aplica la encuesta.
        Prioridad:
        1. Si tiene tiendas asignadas, devolver esas tiendas.
        2. Si tiene una región asignada, devolver las tiendas de esa región.
        3. Si tiene un país asignado, devolver las tiendas de ese país.
        """
        if self.tiendas.exists():
            return self.tiendas.all()  # Tiendas asignadas directamente
        elif self.region:
            return Tienda.objects.filter(region=self.region)  # Tiendas de la región asignada
        elif self.pais:
            return Tienda.objects.filter(pais=self.pais)  # Tiendas del país asignado
        else:
            return Tienda.objects.none()  # No hay tiendas asignadas

class EncuestaFijaRespuesta(models.Model):
    encuesta_fija = models.ForeignKey(EncuestaFija, on_delete=models.CASCADE, related_name='respuestas')
    
    # Datos personales del usuario
    nombre = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    telefono = models.CharField(max_length=9)
    codigo_ticket = models.CharField(max_length=255, null=True)
    fnac = models.DateField()
    correo = models.EmailField()
    DNI = models.CharField(max_length=9)
    acepPolPriv = models.BooleanField()
    acepProm = models.BooleanField(null=True, blank=True)  # Este campo es opcional
    fecha_respuesta = models.DateField(default=date.today)
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='respuestas_encuesta', null=True, blank=True)
    
    # --- CAMPOS NUEVOS ---
    # Las 3 preguntas de valoración con estrellas (1 a 5)
    valoracion_producto = models.IntegerField(default=0, verbose_name="Valoración del producto")
    valoracion_atencion = models.IntegerField(default=0, verbose_name="Valoración de la atención")
    probabilidad_recomendacion = models.IntegerField(default=0, verbose_name="Probabilidad de recomendación")
    
    # Campo de texto para comentarios
    comentarios_adicionales = models.TextField(null=True, blank=True, verbose_name="Comentarios adicionales")

    # --- CAMPOS ANTIGUOS (OBSOLETOS) ---
    # Los hacemos 'nullables' para no afectar a los registros existentes.
    calificacion = models.IntegerField(default=0, null=True, blank=True)
    pregunta_1_1 = models.CharField(max_length=255, null=True, blank=True)
    pregunta_1_2 = models.TextField(null=True, blank=True)
    pregunta_2_1 = models.CharField(max_length=255, null=True, blank=True)
    pregunta_2_2 = models.TextField(null=True, blank=True)
    pregunta_3_1 = models.CharField(max_length=255, null=True, blank=True)
        
    def __str__(self):
        return f"{self.nombre} {self.apellidos} - Encuesta: {self.encuesta_fija.titulo}"

    class Meta:
        verbose_name = "Respuesta de Encuesta Fija"
        verbose_name_plural = "Respuestas de Encuesta Fija"



class EncuestaFijaPremio(models.Model):
    encuesta_fija = models.ForeignKey(EncuestaFija, on_delete=models.CASCADE, related_name='premios_entregados')
    respuesta = models.ForeignKey(EncuestaFijaRespuesta, on_delete=models.CASCADE, related_name='premios', null=True)
    # Datos personales del usuario
    nombre = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    codigo_ticket = models.CharField(max_length=255, null=True)
    DNI = models.CharField(max_length=9)
    premio = models.ForeignKey(Premio, on_delete=models.CASCADE, related_name='premios_entregados')
    fecha_respuesta = models.DateField(default=date.today)
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name='premios_entregados', null=True, blank=True)
    
    def __str__(self):
        return f"{self.nombre} {self.apellidos} - Premio: {self.premio}"
    class Meta:
        verbose_name = "Premio de Encuesta Fija"
        verbose_name_plural = "Premios de Encuesta Fija"





class TicketVentasEnLinea(models.Model):
    nro_ticket = models.CharField(
        "Número de Ticket",
        max_length=50,
        unique=True, # Asegura que no haya tickets duplicados
        help_text="El código único que se le da al cliente."
    )
    tienda = models.ForeignKey(
        Tienda,
        on_delete=models.CASCADE,
        help_text="La tienda online a la que pertenece este ticket."
    )

    # Añadimos la relación con la encuesta
    encuesta_fija = models.ForeignKey(
        EncuestaFija,
        on_delete=models.PROTECT, # Evita borrar una encuesta si tiene tickets asociados
        related_name='tickets_online',
        verbose_name="Encuesta a aplicar"
    )

    utilizado = models.BooleanField(
        "¿Ya fue utilizado?",
        default=False,
        help_text="Se marca automáticamente cuando el cliente completa la encuesta."
    )
    vigencia = models.DateTimeField(
        "Válido hasta",
        help_text="Fecha y hora en que el ticket expira."
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nro_ticket

    def esta_vencido(self):
        """
        Devuelve True si la fecha de vigencia ya pasó.
        Realiza una comparación consciente de la zona horaria.
        """
        # Si por alguna razón la vigencia ya es consciente, la usamos directamente
        if timezone.is_aware(self.vigencia):
            vigencia_consciente = self.vigencia
        else:
            # Si es ingenua, le asignamos la zona horaria de Perú (America/Lima)
            # Esto asume que tu TIME_ZONE en settings.py es 'America/Lima'
            vigencia_consciente = timezone.make_aware(self.vigencia)
        
        # Ahora comparamos dos fechas del mismo tipo (ambas conscientes)
        return timezone.now() > vigencia_consciente

    def vig_consciente(self):
        if timezone.is_aware(self.vigencia):
            vigencia_consciente = self.vigencia
        else:
            # Si es ingenua, le asignamos la zona horaria de Perú (America/Lima)
            # Esto asume que tu TIME_ZONE en settings.py es 'America/Lima'
            vigencia_consciente = timezone.make_aware(self.vigencia)
        return vigencia_consciente


    def enlace_encuesta(self):
        """
        Genera el enlace a la encuesta para este ticket.
        """
        # Generamos la URL usando el 'name' de tu urls.py
        url = reverse('fijaConTicket', args=[self.tienda.id, self.encuesta_fija.id, self.nro_ticket])
        return format_html('<a href="{}" target="_blank">{}</a>', url, self.nro_ticket)
    
    enlace_encuesta.short_description = "Enlace para el Cliente"

    class Meta:
        verbose_name = "Ticket de Venta en Línea"
        verbose_name_plural = "Tickets de Venta en Línea"

