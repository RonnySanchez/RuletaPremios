import uuid
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from cupones.services import emitir_cupon_para_premio
from .models import EncuestaFija, EncuestaFijaPremio, EncuestaFijaRespuesta, ParticipacionCuponDirecto


def resolver_campana(tienda, instante=None):
    instante = instante or timezone.now()
    candidatas = EncuestaFija.objects.filter(activa=True).filter(
        Q(tiendas=tienda) | Q(region_id=tienda.region_id) | Q(pais_id=tienda.pais_id)
    ).select_related('encuestafija').distinct()
    vigentes = [
        campana for campana in candidatas
        if campana.vigente_en(instante) and campana.get_tiendas_asignadas().filter(pk=tienda.pk).exists()
    ]
    if len(vigentes) > 1:
        raise ValidationError('Hay varias campanas vigentes para esta tienda. Revisa sus fechas y asignaciones.')
    return vigentes[0] if vigentes else None


def validar_participacion(campana, tienda, ticket, instante=None):
    instante = instante or timezone.now()
    if not tienda.activa or not campana.vigente_en(instante):
        raise ValidationError('La campana no esta disponible para participar en este momento.')
    if not campana.get_tiendas_asignadas().filter(pk=tienda.pk).exists():
        raise ValidationError('La campana no esta asignada a esta tienda.')
    if ticket.tienda_id != tienda.pk or not ticket.codigo or ticket.status_respuesta != 200 or ticket.encuesta_id_resuelta != str(campana.pk):
        raise ValidationError('El ticket no esta habilitado para esta campana.')
    if not campana.vigente_en(ticket.creado_en):
        raise ValidationError('El ticket se registro fuera de la vigencia de participacion.')
    try:
        monto = Decimal(ticket.monto)
        if not monto.is_finite() or monto < tienda.monto_minimo_promociones:
            raise ValidationError('La compra no alcanza el monto minimo de promociones de la tienda.')
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError('El monto del ticket no es valido.')


@transaction.atomic
def entregar_premio_directo(campana, tienda, ticket, datos):
    # El bloqueo de campana serializa la primera entrega incluso antes de existir la respuesta.
    campana = EncuestaFija.objects.select_for_update().select_related('encuestafija', 'premio_directo').get(pk=campana.pk)
    participacion, _ = ParticipacionCuponDirecto.objects.get_or_create(
        encuesta_fija=campana, tienda=tienda, codigo_ticket=ticket.codigo,
    )
    existente = participacion.premio_entregado
    if existente:
        if not existente.token_resultado:
            existente.token_resultado = uuid.uuid4()
            existente.save(update_fields=['token_resultado'])
        return existente

    tienda.refresh_from_db()
    validar_participacion(campana, tienda, ticket)
    campana.full_clean()
    if campana.tipo_juego != EncuestaFija.TipoJuego.DIRECTO:
        raise ValidationError('Esta campana no entrega premios directos.')
    if not datos.get('acepPolPriv'):
        raise ValidationError('Debes aceptar los terminos y la politica de privacidad.')

    respuesta, _ = EncuestaFijaRespuesta.objects.get_or_create(
        encuesta_fija=campana, tienda=tienda, codigo_ticket=ticket.codigo,
        defaults={
            'nombre': datos['nombre'], 'apellidos': datos['apellidos'],
            'telefono': datos['telefono'], 'correo': datos['correo'],
            'acepPolPriv': True, 'acepProm': datos.get('acepProm', False),
            'fnac': datos.get('fnac'), 'DNI': datos.get('DNI', ''),
            'tipo_identificacion': datos.get('tipo_identificacion', ''),
            'valoracion_producto': datos.get('valoracion_producto'),
            'valoracion_atencion': datos.get('valoracion_atencion'),
            'probabilidad_recomendacion': datos.get('probabilidad_recomendacion'),
            'comentarios_adicionales': datos.get('comentarios_adicionales'),
            'calificacion': None,
        },
    )
    premio = EncuestaFijaPremio.objects.create(
        encuesta_fija=campana, tienda=tienda, codigo_ticket=ticket.codigo,
        respuesta=respuesta, premio=campana.premio_directo,
        nombre=respuesta.nombre, apellidos=respuesta.apellidos,
        DNI=respuesta.DNI, tipo_identificacion=respuesta.tipo_identificacion,
        token_resultado=uuid.uuid4(),
    )
    if emitir_cupon_para_premio(premio) is None:
        raise ValidationError('El premio no tiene plantilla de cupon.')
    participacion.premio_entregado = premio
    participacion.save(update_fields=['premio_entregado'])
    return premio
