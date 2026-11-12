from django.http import JsonResponse
from django.urls import reverse
from django.core.exceptions import ValidationError
from decimal import Decimal, InvalidOperation
import uuid
from rest_framework.views import APIView
from rest_framework import status
from encuestas.models import TicketConsulta, Tienda, EncuestaFija
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework.permissions import IsAuthenticated
from encuestas.services import resolver_campana


class MyTokenObtainPairView(TokenObtainPairView):
    pass


class MyTokenRefreshView(TokenRefreshView):
    pass


class EncuestaTiendaAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def _registrar_ticket_consulta(self, tienda, codigo, monto, payload, encuesta_id_resuelta=""):
        return TicketConsulta.objects.create(
            tienda=tienda,
            codigo=codigo or "",
            monto=monto or 0,
            encuesta_id_resuelta=str(encuesta_id_resuelta or ""),
            url_respuesta=payload.get("Resp", ""),
            status_respuesta=payload.get("status"),
            encabezado_respuesta=payload.get("encabezado", ""),
            texto_respuesta=payload.get("texto", ""),
        )

    def post(self, request, *args, **kwargs):
        tienda_id = request.data.get("tienda_id")
        codigo = request.data.get("codigo")
        try:
            monto = Decimal(str(request.data.get('monto')))
            if not monto.is_finite() or monto < 0 or monto > Decimal('99999999.99') or monto != monto.quantize(Decimal('0.01')):
                raise ValueError
        except (InvalidOperation, ValueError, TypeError):
            return JsonResponse({'error': 'El monto debe ser un numero no negativo con hasta dos decimales.'}, status=400)
        if not isinstance(codigo, str) or not codigo.strip() or len(codigo) > 255:
            return JsonResponse({'error': 'Indica un codigo de ticket valido.'}, status=400)

        try:
            tienda_enc = Tienda.objects.get(id_efsystem=tienda_id, activa=True)
        except Tienda.DoesNotExist:
            payload = {
                "Resp": "",
                "status": 0,
                "encabezado": "",
                "texto": "No existe tienda",
                "codigo": ""
            }
            return JsonResponse(payload, status=status.HTTP_200_OK)

        try:
            encuesta_asignada = resolver_campana(tienda_enc)
        except ValidationError as exc:
            return JsonResponse({'Resp': '', 'status': 3, 'encabezado': '', 'texto': exc.messages[0], 'codigo': ''})
        if encuesta_asignada is None:
            payload = {
                "Resp": "",
                "status": 1,
                "encabezado": "",
                "texto": "No tiene encuesta asignada",
                "codigo": ""
            }
            self._registrar_ticket_consulta(tienda_enc, codigo, monto, payload)
            return JsonResponse(payload, status=status.HTTP_200_OK)

        e_asignada = encuesta_asignada.pk
        if encuesta_asignada:
            resp = tienda_enc.permite_premios_para(monto)
            if resp == 0:
                payload = {
                    "Resp": "",
                    "status": 2,
                    "encabezado": "",
                    "texto": "No cumple con monto mínimo para premios",
                    "codigo": ""
                }
                self._registrar_ticket_consulta(tienda_enc, codigo, monto, payload, e_asignada)
                return JsonResponse(payload, status=status.HTTP_200_OK)

            token = uuid.uuid4() if encuesta_asignada.tipo_juego == EncuestaFija.TipoJuego.DIRECTO else None
            ruta = reverse('contacto_cupon', args=[token]) if token else reverse(
                'fijaConTicket', args=[tienda_enc.id, e_asignada, codigo],
            )
            url = request.build_absolute_uri(ruta)
            payload = {
                "Resp": url,
                "status": 200,
                "encabezado": encuesta_asignada.encabezado,
                "texto": encuesta_asignada.texto,
                "codigo": codigo
            }
            ticket = self._registrar_ticket_consulta(tienda_enc, codigo, monto, payload, e_asignada)
            if token:
                ticket.token_participacion = token
                ticket.save(update_fields=['token_participacion'])
            return JsonResponse(payload, status=status.HTTP_200_OK)

