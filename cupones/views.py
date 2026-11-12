from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Cupon, UsoCupon
from .serializers import (
    ConsumirCuponSerializer,
    CuponSerializer,
    DatosValidacionCuponSerializer,
    UsoCuponRespuestaSerializer,
    UsoCuponSerializer,
)
from .services import validar_restricciones_cupon


def _mensaje_validacion(exc):
    if hasattr(exc, "messages"):
        return exc.messages[0]
    return str(exc)


class ConsultarCuponAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, codigo):
        cupon = get_object_or_404(Cupon, codigo__iexact=codigo)
        if not cupon.is_active:
            return Response(
                {"error": "El cupon no es valido, ha expirado o se ha agotado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(CuponSerializer(cupon).data)


class MarcarUsoCuponAPIView(APIView):
    """Endpoint heredado. La API v2 debe usarse para los cupones premio."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = UsoCuponSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        codigo = serializer.validated_data.pop("codigo")

        try:
            with transaction.atomic():
                cupon = Cupon.objects.select_for_update().get(codigo__iexact=codigo)
                if not cupon.is_active:
                    return Response(
                        {"error": "El cupon no esta activo, vencio o ya fue utilizado."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if not cupon.transferible:
                    return Response(
                        {"error": "Este cupon requiere validacion de identidad mediante la API v2."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if cupon.cantidad_maxima_productos is not None or cupon.presentaciones.exists():
                    return Response(
                        {'error': 'Este cupon requiere validar productos mediante la API v2.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                cupon.usos_actuales += 1
                if cupon.usos_actuales >= cupon.limite_usos:
                    cupon.estatus = Cupon.Estatus.AGOTADO
                cupon.save(update_fields=["usos_actuales", "estatus"])
                uso = serializer.save(cupon=cupon, usuario_api=request.user)
        except Cupon.DoesNotExist:
            return Response({"error": "El cupon no existe."}, status=status.HTTP_404_NOT_FOUND)

        return Response(
            {
                "mensaje": f"Cupon '{cupon.codigo}' marcado como usado.",
                "datos_registrados": UsoCuponRespuestaSerializer(uso).data,
            }
        )


class ValidarCuponAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DatosValidacionCuponSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data

        try:
            cupon = Cupon.objects.prefetch_related("categorias", "presentaciones").get(
                codigo__iexact=datos["codigo"]
            )
            descuento = validar_restricciones_cupon(
                cupon,
                monto_total=datos["monto_total"],
                categoria=datos.get("categoria"),
                presentacion_codigo=datos.get("presentacion_codigo"),
                cantidad_productos=datos.get('cantidad_productos'),
                monto_aplicable=datos.get('monto_aplicable'),
                tipo_identificacion=datos.get("tipo_identificacion"),
                numero_identificacion=datos.get("numero_identificacion"),
            )
        except Cupon.DoesNotExist:
            return Response({"valido": False, "error": "El cupon no existe."}, status=404)
        except ValidationError as exc:
            return Response(
                {"valido": False, "error": _mensaje_validacion(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "valido": True,
                "descuento_calculado": str(descuento),
                "cupon": CuponSerializer(cupon).data,
            }
        )


def _respuesta_canje(uso):
    return Response({
        "mensaje": "Cupon consumido correctamente.",
        "datos_registrados": UsoCuponRespuestaSerializer(uso).data,
    })


def _normalizar_dato_canje(campo, valor):
    if isinstance(valor, str):
        if campo in {"categoria", "presentacion_codigo", "numero_identificacion"}:
            valor = valor.strip().casefold()
        return valor or None
    return valor


def _respuesta_reintento(uso, codigo, datos_uso, descuento_confirmado):
    coincide = (
        uso.cupon.codigo.casefold() == codigo.casefold()
        and all(
            _normalizar_dato_canje(campo, getattr(uso, campo)) == _normalizar_dato_canje(campo, valor)
            for campo, valor in datos_uso.items()
        )
        and (descuento_confirmado is None or descuento_confirmado == uso.monto_descuento)
    )
    if not coincide:
        return Response(
            {"error": "La clave de idempotencia ya fue usada con otros datos de canje."},
            status=status.HTTP_409_CONFLICT,
        )
    return _respuesta_canje(uso)


class ConsumirCuponAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ConsumirCuponSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        idempotency_key = datos["idempotency_key"]
        codigo = datos["codigo"]
        descuento_confirmado = datos.get("monto_descuento")
        restricciones = {
            campo: datos.get(campo)
            for campo in (
                "monto_total", "categoria", "presentacion_codigo", "cantidad_productos",
                "monto_aplicable", "tipo_identificacion", "numero_identificacion",
            )
        }
        datos_uso = {
            **restricciones,
            "tienda_id": datos["tienda"].pk,
            "usuario_api_id": request.user.pk,
            "nro_referencia": datos.get("nro_referencia"),
        }

        usos = UsoCupon.objects.select_related("cupon", "tienda").filter(
            idempotency_key=idempotency_key
        )
        existente = usos.first()
        if existente:
            return _respuesta_reintento(existente, codigo, datos_uso, descuento_confirmado)

        try:
            with transaction.atomic():
                cupon = (
                    Cupon.objects.select_for_update()
                    .prefetch_related("categorias", "presentaciones")
                    .get(codigo__iexact=codigo)
                )
                existente = usos.first()
                if existente:
                    return _respuesta_reintento(existente, codigo, datos_uso, descuento_confirmado)

                descuento = validar_restricciones_cupon(cupon, **restricciones)
                if descuento_confirmado is not None and descuento_confirmado != descuento:
                    return Response(
                        {
                            "error": "El descuento confirmado no coincide con el calculado.",
                            "descuento_calculado": str(descuento),
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
                uso = UsoCupon.objects.create(
                    cupon=cupon,
                    idempotency_key=idempotency_key,
                    monto_descuento=descuento,
                    **datos_uso,
                )
                cupon.usos_actuales += 1
                if cupon.usos_actuales >= cupon.limite_usos:
                    cupon.estatus = Cupon.Estatus.AGOTADO
                cupon.save(update_fields=["usos_actuales", "estatus"])
        except Cupon.DoesNotExist:
            return Response({"error": "El cupon no existe."}, status=404)
        except ValidationError as exc:
            return Response(
                {"error": _mensaje_validacion(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except IntegrityError:
            existente = usos.first()
            if existente:
                return _respuesta_reintento(existente, codigo, datos_uso, descuento_confirmado)
            raise

        return _respuesta_canje(uso)
