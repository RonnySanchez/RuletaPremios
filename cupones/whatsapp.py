import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings
from django.utils import timezone

from .models import Cupon, NotificacionCuponWhatsApp


ENDPOINT = "https://api.efperfumes.com/conversation"
Estado = NotificacionCuponWhatsApp.Estado


class _SinRedirecciones(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def encolar_cupon_whatsapp(cupon, telefono):
    telefono = telefono.strip()
    if re.fullmatch(r"9[0-9]{8}", telefono):
        datos = {"destino": f"51{telefono}"}
    else:
        datos = {
            "destino": "", "estado": Estado.OMITIDO, "finalizado_en": timezone.now(),
            "detalle": "El número no tiene un formato celular peruano válido.",
        }
    NotificacionCuponWhatsApp.objects.get_or_create(cupon=cupon, defaults=datos)


def configuracion_whatsapp():
    encabezados = {
        "x-chatbots-custom": settings.CUPON_WHATSAPP_CHATBOTS_CUSTOM.strip(),
        "Authorization": settings.CUPON_WHATSAPP_AUTHORIZATION.strip(),
        "Content-Type": "application/json",
    }
    nombre = settings.CUPON_WHATSAPP_PLANTILLA_NOMBRE.strip()
    idioma = settings.CUPON_WHATSAPP_IDIOMA.strip()
    plantilla_id = settings.CUPON_WHATSAPP_PLANTILLA_ID.strip()
    telefono_id = settings.CUPON_WHATSAPP_COMPANY_PHONE_ID.strip()
    if not all((encabezados["x-chatbots-custom"], encabezados["Authorization"], nombre, idioma)):
        raise ValueError("Faltan credenciales, nombre o idioma de la plantilla de WhatsApp.")
    if not all(valor.isascii() and valor.isprintable() for valor in encabezados.values()):
        raise ValueError("Las cabeceras de WhatsApp contienen caracteres no válidos.")
    if not all(re.fullmatch(r"[1-9][0-9]*", valor) for valor in (plantilla_id, telefono_id)):
        raise ValueError("Configura el ID de la plantilla de cupón y el company_phone_id.")
    return encabezados, nombre, idioma, int(plantilla_id), int(telefono_id)


def _fecha_lima(instantanea):
    return timezone.localtime(instantanea, timezone.get_default_timezone()).date()


def _cuerpo_envio(notificacion, nombre, plantilla, idioma, plantilla_id, telefono_id):
    cupon = notificacion.cupon
    if cupon.tipo == Cupon.Tipo.PORCENTAJE:
        porcentaje = format(cupon.valor.normalize(), "f")
        descuento = f"{porcentaje}%"
    else:
        descuento = f"S/ {cupon.valor:.2f}"
    inicio, fin = _fecha_lima(cupon.inicio), _fecha_lima(cupon.vencimiento)
    vigencia = f"el {fin:%d/%m/%Y}" if inicio == fin else f"del {inicio:%d/%m/%Y} al {fin:%d/%m/%Y}"
    valores = (" ".join(nombre.split()), descuento, cupon.codigo, vigencia)
    return {
        "to": notificacion.destino,
        "messageData": {
            "type": "template",
            "template": {
                "name": plantilla,
                "language": {"code": idioma},
                "id": plantilla_id,
                "components": [{
                    "type": "body",
                    "parameters": [{"type": "text", "text": valor} for valor in valores],
                }],
            },
        },
        "company_phone_id": telefono_id,
    }


def _enviar_al_proveedor(encabezados, cuerpo):
    solicitud = Request(ENDPOINT, data=json.dumps(cuerpo).encode("utf-8"), headers=encabezados, method="POST")
    try:
        with build_opener(_SinRedirecciones()).open(solicitud, timeout=10) as respuesta:
            codigo = respuesta.status
    except HTTPError as exc:
        codigo = exc.code
        exc.close()
    except (URLError, OSError):
        return Estado.INCIERTO, None, "Sin respuesta HTTP concluyente."

    if 200 <= codigo < 300:
        return Estado.ACEPTADO, codigo, "Aceptado por HTTP; entrega no confirmada."
    if 300 <= codigo < 500 and codigo != 408:
        return Estado.RECHAZADO, codigo, "Solicitud no aceptada por el proveedor."
    return Estado.INCIERTO, codigo, "Respuesta del proveedor no concluyente."


def procesar_notificacion_whatsapp(pk, configuracion):
    registros = NotificacionCuponWhatsApp.objects
    # La toma condicional impide que dos procesos envíen el mismo cupón.
    if not registros.filter(pk=pk, estado=Estado.PENDIENTE).update(estado=Estado.ENVIANDO):
        return None
    notificacion = registros.select_related("cupon__premio_ganado__respuesta").get(pk=pk)
    cupon = notificacion.cupon
    respuesta = cupon.premio_ganado.respuesta if cupon.premio_ganado else None
    ahora = timezone.now()
    if not respuesta or not respuesta.acepWhatsApp or notificacion.destino != f"51{respuesta.telefono}":
        estado, codigo, detalle = Estado.OMITIDO, None, "Sin permiso vigente para el número registrado."
    elif cupon.estatus != Cupon.Estatus.ACTIVO or cupon.usos_actuales >= cupon.limite_usos or cupon.vencimiento < ahora:
        estado, codigo, detalle = Estado.OMITIDO, None, "Cupón vencido, inactivo o agotado."
    else:
        encabezados, *plantilla = configuracion
        cuerpo = _cuerpo_envio(notificacion, respuesta.nombre, *plantilla)
        registros.filter(pk=pk).update(intento_en=ahora)
        estado, codigo, detalle = _enviar_al_proveedor(encabezados, cuerpo)
    registros.filter(pk=pk).update(
        estado=estado, estado_http=codigo, finalizado_en=timezone.now(), detalle=detalle,
    )
    return estado
