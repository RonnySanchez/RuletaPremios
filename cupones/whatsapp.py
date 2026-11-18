import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings
from django.utils import timezone

from .models import Cupon, NotificacionCuponWhatsApp


ENDPOINT = "https://api.efperfumes.com/conversation"
LOGIN_ENDPOINT = "https://api.efperfumes.com/user/login"
PLANTILLA_CUPON_EF = {"name": "cupon_ef", "id": 661, "language": {"code": "es"}}
COMPANY_PHONE_ID_CUPONES = 1
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
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if not all((encabezados["x-chatbots-custom"], settings.CUPON_USUARIO_WEB, settings.CUPON_CLAVE)):
        raise ValueError("Configura CUPON_USUARIO_WEB, CUPON_CLAVE y CUPON_WHATSAPP_CHATBOTS_CUSTOM.")
    if not all(valor.isascii() and valor.isprintable() for valor in encabezados.values()):
        raise ValueError("Las cabeceras de WhatsApp contienen caracteres no válidos.")

    solicitud = Request(LOGIN_ENDPOINT, method="POST", headers=encabezados, data=json.dumps({
        "username": settings.CUPON_USUARIO_WEB,
        "password": settings.CUPON_CLAVE,
    }).encode("utf-8"))
    try:
        with build_opener(_SinRedirecciones()).open(solicitud, timeout=20) as respuesta:
            if not 200 <= respuesta.status < 300:
                raise ValueError(f"El login de WhatsApp devolvió HTTP {respuesta.status}.")
            datos = json.loads(respuesta.read(131072))
    except HTTPError as exc:
        codigo = exc.code
        exc.close()
        raise ValueError(f"El login de WhatsApp devolvió HTTP {codigo}.") from None
    except (URLError, OSError):
        raise ValueError("No se pudo conectar al login de WhatsApp.") from None
    except (json.JSONDecodeError, UnicodeError):
        raise ValueError("El login de WhatsApp no devolvió un JSON válido.") from None

    token = datos.get("token") if isinstance(datos, dict) else None
    if not isinstance(token, str) or not token.strip():
        raise ValueError("El login de WhatsApp no devolvió un token.")
    token = token.strip()
    if not token.isascii() or not token.isprintable():
        raise ValueError("El token de WhatsApp contiene caracteres no válidos.")
    telefonos = datos.get("company_phones")
    if not isinstance(telefonos, list) or not any(
        isinstance(item, dict) and str(item.get("company_phone_id")) == str(COMPANY_PHONE_ID_CUPONES)
        for item in telefonos
    ):
        raise ValueError("El usuario del login no tiene autorizado el remitente de cupones.")
    encabezados["Authorization"] = token
    return encabezados


def _fecha_lima(instantanea):
    return timezone.localtime(instantanea, timezone.get_default_timezone()).date()


def _cuerpo_envio(notificacion, nombre):
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
                **PLANTILLA_CUPON_EF,
                "components": [{
                    "type": "body",
                    "parameters": [{"type": "text", "text": valor} for valor in valores],
                }],
            },
        },
        "company_phone_id": COMPANY_PHONE_ID_CUPONES,
    }


def _detalle_rechazo(cabeceras):
    detalle = "Solicitud no aceptada por el proveedor."
    if not cabeceras:
        return detalle

    # Conserva solo identificadores con formato reconocido, sin copiar el cuerpo del error.
    for nombre in ("x-request-id", "x-correlation-id", "request-id"):
        referencia = cabeceras.get(nombre, "")
        if re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", referencia, re.I):
            return f"{detalle} {nombre}={referencia}"
    ray = cabeceras.get("cf-ray", "")
    if re.fullmatch(r"[0-9a-f]{16}-[A-Z]{3}", ray, re.ASCII):
        return f"{detalle} cf-ray={ray}"
    return detalle


def _enviar_al_proveedor(encabezados, cuerpo):
    solicitud = Request(ENDPOINT, data=json.dumps(cuerpo).encode("utf-8"), headers=encabezados, method="POST")
    cabeceras_respuesta = None
    try:
        with build_opener(_SinRedirecciones()).open(solicitud, timeout=10) as respuesta:
            codigo = respuesta.status
    except HTTPError as exc:
        codigo = exc.code
        cabeceras_respuesta = exc.headers
        exc.close()
    except (URLError, OSError):
        return Estado.INCIERTO, None, "Sin respuesta HTTP concluyente."

    if 200 <= codigo < 300:
        return Estado.ACEPTADO, codigo, "Aceptado por HTTP; entrega no confirmada."
    if 300 <= codigo < 500 and codigo != 408:
        return Estado.RECHAZADO, codigo, _detalle_rechazo(cabeceras_respuesta)
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
        encabezados = configuracion
        cuerpo = _cuerpo_envio(notificacion, respuesta.nombre)
        registros.filter(pk=pk).update(intento_en=ahora)
        estado, codigo, detalle = _enviar_al_proveedor(encabezados, cuerpo)
    registros.filter(pk=pk).update(
        estado=estado, estado_http=codigo, finalizado_en=timezone.now(), detalle=detalle,
    )
    return estado
