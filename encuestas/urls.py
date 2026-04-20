from django.urls import path, include

from . import views

urlpatterns = [
    path("", views.IndexView, name="index"),
    path("mensaje/",views.mensajeCorreo, name='mensaje'),
    path('<int:tienda_id>/<int:encuesta_id>/', views.polls, name='polls'),
    path('<int:tienda_id>/<int:encuesta_id>/<str:codigo_ticket>/', views.polls, name='pollsConTicket'),
    path('fija/<int:tienda_id>/<int:encuesta_id>/', views.pideticket, name='fija'),
    path('fija/<int:tienda_id>/<int:encuesta_id>/<str:codigo_ticket>/', views.encuestafijaticket, name='fijaConTicket'),
    path('ruleta/<int:encuesta_id>/<int:tienda_id>/<str:codigo_ticket>/', views.ruleta, name='ruleta'),
    path('guardar-premio/', views.guardar_premio, name='guardar_premio'),
    path('guardar-premio1/', views.guardar_premio, name='guardar_premio1'),
    path('juego-regalos/<int:encuesta_id>/<int:tienda_id>/<str:codigo_ticket>', views.vista_juego_regalos, name='juego_regalos'),
    path('simulador/', views.simulador_pantallas, name='simulador_pantallas'),
    path('ejecutar-sorteo-ajax/', views.ejecutar_sorteo_ajax, name='ejecutar_sorteo_ajax'),
#    path('api/<int:tienda_id>/', views.consultaEncuestaFijaTiendaApi, name='consultaApi'),
#    path('encuesta-completada/', views.encuesta_completada, name='encuesta_completada'),
]

