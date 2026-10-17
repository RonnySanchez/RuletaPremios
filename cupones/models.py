from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class TipoDescuento(models.TextChoices):
    PORCENTAJE = "PORCENTAJE", "Porcentaje"
    MONTO = "MONTO", "Monto fijo"


class TipoIdentificacion(models.TextChoices):
    DNI = "DNI", "DNI"
    CE = "CE", "CE"
    PASAPORTE = "PASAPORTE", "Pasaporte"


class CategoriaCupon(models.Model):
    nombre = models.CharField(
        max_length=100,
        unique=True,
        help_text="Ej.: Botellas, Fragancias, Esencias",
    )

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = "Categoria de cupon"
        verbose_name_plural = "Categorias de cupones"


class PresentacionCupon(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    codigo_efsystem = models.CharField(max_length=50, unique=True)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nombre} ({self.codigo_efsystem})"

    class Meta:
        ordering = ["nombre"]
        verbose_name = "Presentacion de cupon"
        verbose_name_plural = "Presentaciones de cupones"


class PlantillaCuponPremio(models.Model):
    class TipoVigencia(models.TextChoices):
        DIAS = "DIAS", "Dias desde la entrega"
        FECHA_FIJA = "FECHA_FIJA", "Fecha fija"

    premio = models.OneToOneField(
        "encuestas.Premio",
        on_delete=models.CASCADE,
        related_name="plantilla_cupon",
    )
    activo = models.BooleanField(default=True)
    tipo = models.CharField(
        max_length=10,
        choices=TipoDescuento.choices,
        default=TipoDescuento.PORCENTAJE,
    )
    valor = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    formato_codigo = models.CharField(
        max_length=100,
        default="CUPON-tt-hhmm-nnnn",
        help_text="Mayusculas literales. Tokens: tt, hh, mm y n para digitos aleatorios.",
    )
    categorias = models.ManyToManyField(
        CategoriaCupon,
        related_name="plantillas",
        blank=True,
        verbose_name="Categorias aplicables",
    )
    presentaciones = models.ManyToManyField(
        PresentacionCupon,
        related_name="plantillas",
        blank=True,
        verbose_name="Presentaciones aplicables",
    )
    tipo_vigencia = models.CharField(
        max_length=10,
        choices=TipoVigencia.choices,
        default=TipoVigencia.DIAS,
    )
    dias_vigencia = models.PositiveIntegerField(null=True, blank=True)
    fecha_vencimiento_fija = models.DateField(null=True, blank=True)
    transferible = models.BooleanField(default=True)
    minimo_compra = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    maximo_descuento = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0.01)],
    )

    def __str__(self):
        return f"Cupon para {self.premio}"

    def clean(self):
        super().clean()
        from .services import validar_formato_codigo

        errors = {}
        try:
            validar_formato_codigo(self.formato_codigo)
        except ValidationError as exc:
            errors["formato_codigo"] = exc.messages

        if self.tipo == TipoDescuento.PORCENTAJE and not (0 < self.valor <= 100):
            errors["valor"] = "Para porcentaje, el valor debe estar entre 0 y 100."
        if self.tipo == TipoDescuento.MONTO and self.maximo_descuento is not None:
            errors["maximo_descuento"] = "El descuento maximo solo aplica a porcentajes."
        if self.tipo_vigencia == self.TipoVigencia.DIAS:
            if not self.dias_vigencia:
                errors["dias_vigencia"] = "Indica una cantidad de dias mayor que cero."
            if self.fecha_vencimiento_fija:
                errors["fecha_vencimiento_fija"] = "No aplica para vigencia por dias."
        elif self.tipo_vigencia == self.TipoVigencia.FECHA_FIJA:
            if not self.fecha_vencimiento_fija:
                errors["fecha_vencimiento_fija"] = "Indica la fecha de vencimiento."
            elif self.fecha_vencimiento_fija < timezone.localdate():
                errors["fecha_vencimiento_fija"] = "La fecha fija no puede estar vencida."
            if self.dias_vigencia:
                errors["dias_vigencia"] = "No aplica para una fecha fija."

        if errors:
            raise ValidationError(errors)

    class Meta:
        verbose_name = "Plantilla de cupon premio"
        verbose_name_plural = "Plantillas de cupones premio"


class Cupon(models.Model):
    Tipo = TipoDescuento

    class Estatus(models.TextChoices):
        ACTIVO = "ACTIVO", "Activo"
        INACTIVO = "INACTIVO", "Inactivo"
        VENCIDO = "VENCIDO", "Vencido"
        AGOTADO = "AGOTADO", "Agotado"

    codigo = models.CharField(max_length=100, unique=True)
    estatus = models.CharField(
        max_length=10,
        choices=Estatus.choices,
        default=Estatus.ACTIVO,
    )
    tipo = models.CharField(
        max_length=10,
        choices=TipoDescuento.choices,
        default=TipoDescuento.PORCENTAJE,
    )
    valor = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    categorias = models.ManyToManyField(
        CategoriaCupon,
        related_name="cupones",
        blank=True,
        verbose_name="Categorias aplicables",
    )
    presentaciones = models.ManyToManyField(
        PresentacionCupon,
        related_name="cupones",
        blank=True,
        verbose_name="Presentaciones aplicables",
    )
    plantilla_origen = models.ForeignKey(
        PlantillaCuponPremio,
        on_delete=models.SET_NULL,
        related_name="cupones_emitidos",
        null=True,
        blank=True,
    )
    premio_ganado = models.OneToOneField(
        "encuestas.EncuestaFijaPremio",
        on_delete=models.PROTECT,
        related_name="cupon",
        null=True,
        blank=True,
    )
    transferible = models.BooleanField(default=True)
    tipo_identificacion = models.CharField(
        max_length=10,
        choices=TipoIdentificacion.choices,
        null=True,
        blank=True,
    )
    numero_identificacion = models.CharField(max_length=20, null=True, blank=True)
    inicio = models.DateTimeField(default=timezone.now)
    vencimiento = models.DateTimeField()
    minimo_compra = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    maximo_descuento = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    limite_usos = models.PositiveIntegerField(default=1)
    usos_actuales = models.PositiveIntegerField(default=0, editable=False)

    def __str__(self):
        return self.codigo

    @property
    def is_active(self):
        now = timezone.now()
        return (
            self.estatus == self.Estatus.ACTIVO
            and self.inicio <= now <= self.vencimiento
            and self.usos_actuales < self.limite_usos
        )

    def clean(self):
        super().clean()
        errors = {}
        if self.inicio and self.vencimiento and self.inicio >= self.vencimiento:
            errors["vencimiento"] = "Debe ser posterior al inicio."
        if self.tipo == TipoDescuento.PORCENTAJE and not (0 < self.valor <= 100):
            errors["valor"] = "Para porcentaje, el valor debe estar entre 0 y 100."
        if not self.transferible and not self.numero_identificacion:
            errors["numero_identificacion"] = "Es obligatorio para cupones no transferibles."
        if not self.transferible and not self.tipo_identificacion:
            errors["tipo_identificacion"] = "Es obligatorio para cupones no transferibles."
        if errors:
            raise ValidationError(errors)

    class Meta:
        verbose_name = "Cupon"
        verbose_name_plural = "Cupones"
        ordering = ["-inicio"]


class UsoCupon(models.Model):
    cupon = models.ForeignKey(Cupon, on_delete=models.CASCADE, related_name="usos")
    usuario_api = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
    )
    fecha_uso = models.DateTimeField(auto_now_add=True)
    tienda = models.ForeignKey(
        "encuestas.Tienda",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usos_cupones",
    )
    idempotency_key = models.CharField(max_length=100, unique=True, null=True, blank=True)
    nro_referencia = models.CharField(max_length=255, null=True, blank=True)
    monto_total = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    monto_descuento = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    categoria = models.CharField(max_length=100, null=True, blank=True)
    presentacion_codigo = models.CharField(max_length=50, null=True, blank=True)
    tipo_identificacion = models.CharField(max_length=10, null=True, blank=True)
    numero_identificacion = models.CharField(max_length=20, null=True, blank=True)

    def __str__(self):
        return f"Cupon {self.cupon.codigo} usado el {self.fecha_uso:%Y-%m-%d %H:%M}"

    class Meta:
        verbose_name = "Registro de uso de cupon"
        verbose_name_plural = "Registros de uso de cupones"
        ordering = ["-fecha_uso"]
