from django.contrib import admin
from django.urls import path, include
from encuestas.views import IndexView, manejo_404, politicas
from django.conf.urls import include
from django.conf import settings               # Importar settings
from django.conf.urls.static import static     # Importar static


urlpatterns = [
    path('grappelli/', include('grappelli.urls')),
    path('admin/', admin.site.urls),
    path('',IndexView),
    path('politicas/', politicas, name='politicas'),
    path('polls/', include('encuestas.urls')),
    path('api/cupones/', include('cupones.urls')),
    path('api/v2/cupones/', include('cupones.urls_v2')),
    path('api/', include('encuestas.api.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = 'encuestas.views.manejo_404'

admin.site.site_title = 'Sorteos EF Perfumes'
admin.site.site_header = 'Administrador de Sorteos EF Perfumes'

