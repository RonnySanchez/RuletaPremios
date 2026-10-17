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


class ConsumirCuponAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ConsumirCuponSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        idempotency_key = datos["idempotency_key"]
        codigo = datos["codigo"]

        existente = UsoCupon.objects.select_related("cupon", "tienda").filter(
            idempotency_key=idempotency_key
        ).first()
        if existente:
            if existente.cupon.codigo.casefold() != codigo.casefold():
                return Response(
                    {"error": "La clave de idempotencia ya fue usada para otro cupon."},
                    status=status.HTTP_409_CONFLICT,
                )
            return Response(
                {"mensaje": "Operacion ya procesada.", "uso": UsoCuponRespuestaSerializer(existente).data}
            )

        try:
            with transaction.atomic():
                cupon = (
                    Cupon.objects.select_for_update()
                    .prefetch_related("categorias", "presentaciones")
                    .get(codigo__iexact=codigo)
                )
                existente = UsoCupon.objects.filter(idempotency_key=idempotency_key).first()
                if existente:
                    if existente.cupon.codigo.casefold() != codigo.casefold():
                        return Response(
                            {"error": "La clave de idempotencia ya fue usada para otro cupon."},
                            status=status.HTTP_409_CONFLICT,
                        )
                    return Response(
                        {"mensaje": "Operacion ya procesada.", "uso": UsoCuponRespuestaSerializer(existente).data}
                    )

                descuento = validar_restricciones_cupon(
                    cupon,
                    monto_total=datos["monto_total"],
                    categoria=datos.get("categoria"),
                    presentacion_codigo=datos.get("presentacion_codigo"),
                    tipo_identificacion=datos.get("tipo_identificacion"),
                    numero_identificacion=datos.get("numero_identificacion"),
                )
                uso = UsoCupon.objects.create(
                    cupon=cupon,
                    usuario_api=request.user,
                    tienda=datos["tienda"],
                    idempotency_key=idempotency_key,
                    nro_referencia=datos.get("nro_referencia"),
                    monto_total=datos["monto_total"],
                    monto_descuento=descuento,
                    categoria=datos.get("categoria"),
                    presentacion_codigo=datos.get("presentacion_codigo"),
                    tipo_identificacion=datos.get("tipo_identificacion"),
                    numero_identificacion=datos.get("numero_identificacion"),
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
            existente = UsoCupon.objects.select_related("cupon", "tienda").filter(
                idempotency_key=idempotency_key
            ).first()
            if existente:
                if existente.cupon.codigo.casefold() != codigo.casefold():
                    return Response(
                        {"error": "La clave de idempotencia ya fue usada para otro cupon."},
                        status=status.HTTP_409_CONFLICT,
                    )
                return Response(
                    {"mensaje": "Operacion ya procesada.", "uso": UsoCuponRespuestaSerializer(existente).data}
                )
            raise

        return Response(
            {"mensaje": "Cupon consumido correctamente.", "uso": UsoCuponRespuestaSerializer(uso).data}
        )
