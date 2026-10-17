from django.urls import path

from .views import ConsumirCuponAPIView, ValidarCuponAPIView


urlpatterns = [
    path("validar/", ValidarCuponAPIView.as_view(), name="api_v2_validar_cupon"),
    path("usar/", ConsumirCuponAPIView.as_view(), name="api_v2_usar_cupon"),
]
