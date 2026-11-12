from .settings import *

# Las tablas de negocio se crean solo en la base de pruebas, desde los modelos actuales.
MIGRATION_MODULES = {
    'admin': None, 'auth': None, 'contenttypes': None, 'sessions': None,
    'encuestas': None, 'cupones': None,
}
DATABASES['default']['TEST'] = {'NAME': 'test_ruleta_cupon_directo'}
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
