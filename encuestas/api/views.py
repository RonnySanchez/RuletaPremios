from django.http import JsonResponse
from django.urls import reverse
from rest_framework.views import APIView
from rest_framework import status
from encuestas.models import TicketConsulta, Tienda, EncuestaFija
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework.permissions import IsAuthenticated


class MyTokenObtainPairView(TokenObtainPairView):
    pass


class MyTokenRefreshView(TokenRefreshView):
    pass


class EncuestaTiendaAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def _registrar_ticket_consulta(self, tienda, codigo, monto, payload, encuesta_id_resuelta=""):
        TicketConsulta.objects.create(
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
        monto = request.data.get("monto")

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

        e_asignada = tienda_enc.encuestasFijas_asignadas_id()
        if e_asignada == "":
            payload = {
                "Resp": "",
                "status": 1,
                "encabezado": "",
                "texto": "No tiene encuesta asignada",
                "codigo": ""
            }
            self._registrar_ticket_consulta(tienda_enc, codigo, monto, payload)
            return JsonResponse(payload, status=status.HTTP_200_OK)

        encuesta_asignada = EncuestaFija.objects.get(id=e_asignada)
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

            url = "https://rueda.efperfumes.com" + reverse(
                'fijaConTicket',
                args=[tienda_enc.id, e_asignada, codigo]
            )
            payload = {
                "Resp": url,
                "status": 200,
                "encabezado": encuesta_asignada.encabezado,
                "texto": encuesta_asignada.texto,
                "codigo": codigo
            }
            self._registrar_ticket_consulta(tienda_enc, codigo, monto, payload, e_asignada)
            return JsonResponse(payload, status=status.HTTP_200_OK)

