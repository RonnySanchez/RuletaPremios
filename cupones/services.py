import re
import secrets
from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Cupon, PlantillaCuponPremio, TipoDescuento


TOKEN_PATTERN = re.compile(r"tt|hh|mm|n")
FORMATO_PATTERN = re.compile(r"(?:[A-Z0-9_-]|tt|hh|mm|n)+\Z")
MAX_INTENTOS_CODIGO = 20


def validar_formato_codigo(formato):
    if not formato or not FORMATO_PATTERN.fullmatch(formato):
        raise ValidationError(
            "Usa solo mayusculas, numeros, guion y los tokens tt, hh, mm o n."
        )
    if formato.count("n") < 4:
        raise ValidationError("El formato debe contener al menos cuatro digitos aleatorios (nnnn).")
    if len(formato) > Cupon._meta.get_field("codigo").max_length:
        raise ValidationError("El formato supera la longitud maxima del codigo de cupon.")


def renderizar_codigo(formato, tienda, fecha=None):
    validar_formato_codigo(formato)
    fecha = timezone.localtime(fecha or timezone.now())
    if "tt" in formato and tienda.id_efsystem is None:
        raise ValidationError("La tienda no tiene codigo de EFSystem configurado.")

    codigo_tienda = str(int(tienda.id_efsystem)).zfill(2) if tienda.id_efsystem is not None else ""
    valores = {
        "tt": codigo_tienda,
        "hh": fecha.strftime("%H"),
        "mm": fecha.strftime("%M"),
    }

    return TOKEN_PATTERN.sub(
        lambda match: secrets.choice("0123456789") if match.group(0) == "n" else valores[match.group(0)],
        formato,
    )


def calcular_vencimiento(plantilla, inicio=None):
    inicio = inicio or timezone.now()
    inicio_local = timezone.localtime(inicio)

    if plantilla.tipo_vigencia == PlantillaCuponPremio.TipoVigencia.DIAS:
        fecha_vencimiento = inicio_local.date() + timedelta(days=plantilla.dias_vigencia)
    else:
        fecha_vencimiento = plantilla.fecha_vencimiento_fija

    vencimiento_local = datetime.combine(fecha_vencimiento, time.max)
    vencimiento = timezone.make_aware(vencimiento_local, timezone.get_current_timezone())
    if vencimiento <= inicio:
        raise ValidationError("La vigencia calculada del cupon ya finalizo.")
    return vencimiento


def calcular_inicio(plantilla, emision=None):
    emision = emision or timezone.now()
    if plantilla.tipo_vigencia == PlantillaCuponPremio.TipoVigencia.FECHA_FIJA and plantilla.fecha_inicio_fija:
        return timezone.make_aware(datetime.combine(plantilla.fecha_inicio_fija, time.min))
    return emision


def calcular_descuento(cupon, monto_total, *, validar_minimo=True):
    monto_total = Decimal(monto_total)
    if validar_minimo and monto_total < cupon.minimo_compra:
        raise ValidationError("La compra no alcanza el monto minimo requerido.")

    if cupon.tipo == TipoDescuento.PORCENTAJE:
        descuento = monto_total * cupon.valor / Decimal("100")
        if cupon.maximo_descuento is not None:
            descuento = min(descuento, cupon.maximo_descuento)
    else:
        descuento = min(cupon.valor, monto_total)

    return descuento.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def validar_restricciones_cupon(
    cupon,
    *,
    monto_total,
    categoria=None,
    presentacion_codigo=None,
    cantidad_productos=None,
    monto_aplicable=None,
    tipo_identificacion=None,
    numero_identificacion=None,
):
    if not cupon.is_active:
        raise ValidationError("El cupon no esta activo, vencio o ya fue utilizado.")

    categorias = list(cupon.categorias.values_list("nombre", flat=True))
    if categorias and (not categoria or categoria.casefold() not in {item.casefold() for item in categorias}):
        raise ValidationError("El cupon no aplica a la categoria indicada.")

    presentaciones = list(cupon.presentaciones.values_list("codigo_efsystem", flat=True))
    if presentaciones and (
        not presentacion_codigo
        or presentacion_codigo.casefold() not in {item.casefold() for item in presentaciones}
    ):
        raise ValidationError("El cupon no aplica a la presentacion indicada.")

    if not cupon.transferible:
        if not numero_identificacion:
            raise ValidationError("El cupon requiere la identificacion del cliente.")
        if not tipo_identificacion:
            raise ValidationError("El cupon requiere el tipo de identificacion del cliente.")
        if numero_identificacion.strip().upper() != cupon.numero_identificacion.strip().upper():
            raise ValidationError("La identificacion no corresponde al titular del cupon.")
        if tipo_identificacion != cupon.tipo_identificacion:
            raise ValidationError("El tipo de identificacion no corresponde al titular del cupon.")

    monto_total = Decimal(monto_total)
    if monto_total < cupon.minimo_compra:
        raise ValidationError('La compra no alcanza el monto minimo requerido.')
    if cupon.cantidad_maxima_productos is not None:
        if cantidad_productos is None or cantidad_productos < 1 or cantidad_productos > cupon.cantidad_maxima_productos:
            raise ValidationError(f'El cupon aplica como maximo a {cupon.cantidad_maxima_productos} unidad(es). Indica la cantidad de productos beneficiados.')
        if monto_aplicable is None:
            raise ValidationError('Indica el importe de los productos beneficiados, separado del total de la compra.')
    base_descuento = monto_total if monto_aplicable is None else Decimal(monto_aplicable)
    if not base_descuento.is_finite() or base_descuento <= 0 or base_descuento > monto_total:
        raise ValidationError('El importe aplicable debe ser positivo y no superar el total de la compra.')
    return calcular_descuento(cupon, base_descuento, validar_minimo=False)


def emitir_cupon_para_premio(premio_ganado):
    existente = Cupon.objects.filter(premio_ganado=premio_ganado).first()
    if existente:
        return existente
    try:
        plantilla = premio_ganado.premio.plantilla_cupon
    except PlantillaCuponPremio.DoesNotExist:
        return None

    if not plantilla.activo:
        raise ValidationError("La plantilla de cupon del premio esta inactiva.")

    emision = timezone.now()
    inicio = calcular_inicio(plantilla, emision)
    vencimiento = calcular_vencimiento(plantilla, emision)
    if inicio >= vencimiento:
        raise ValidationError('El inicio del cupon debe ser anterior al vencimiento.')
    respuesta = premio_ganado.respuesta

    for _ in range(MAX_INTENTOS_CODIGO):
        codigo = renderizar_codigo(plantilla.formato_codigo, premio_ganado.tienda, emision)
        try:
            with transaction.atomic():
                cupon = Cupon.objects.create(
                    codigo=codigo,
                    tipo=plantilla.tipo,
                    valor=plantilla.valor,
                    cantidad_maxima_productos=plantilla.cantidad_maxima_productos,
                    inicio=inicio,
                    emitido_en=emision,
                    vencimiento=vencimiento,
                    minimo_compra=plantilla.minimo_compra,
                    maximo_descuento=plantilla.maximo_descuento,
                    limite_usos=1,
                    plantilla_origen=plantilla,
                    premio_ganado=premio_ganado,
                    transferible=plantilla.transferible,
                    tipo_identificacion=(
                        respuesta.tipo_identificacion if not plantilla.transferible else None
                    ),
                    numero_identificacion=(respuesta.DNI if not plantilla.transferible else None),
                )
                cupon.categorias.set(plantilla.categorias.all())
                cupon.presentaciones.set(plantilla.presentaciones.all())
                return cupon
        except IntegrityError:
            existente = Cupon.objects.filter(premio_ganado=premio_ganado).first()
            if existente:
                return existente
            if Cupon.objects.filter(codigo=codigo).exists():
                continue
            raise

    raise ValidationError("No se pudo generar un codigo de cupon unico.")
