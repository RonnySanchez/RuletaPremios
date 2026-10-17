# cupones/urls.py

from django.urls import path
from .views import ConsultarCuponAPIView, MarcarUsoCuponAPIView

urlpatterns = [
    path('consultar/<str:codigo>/', ConsultarCuponAPIView.as_view(), name='api_consultar_cupon'),
    path('usar/', MarcarUsoCuponAPIView.as_view(), name='api_usar_cupon'),
]
