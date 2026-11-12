from django.urls import path

from .views import ConsultarCuponAPIView, ConsumirCuponAPIView, ValidarCuponAPIView


urlpatterns = [
    path("consultar/<str:codigo>/", ConsultarCuponAPIView.as_view(), name="api_v2_consultar_cupon"),
    path("validar/", ValidarCuponAPIView.as_view(), name="api_v2_validar_cupon"),
    path("usar/", ConsumirCuponAPIView.as_view(), name="api_v2_usar_cupon"),
]
