# Notificaciones de cupones por WhatsApp

La emisión del cupón directo y su notificación se ejecutan por separado.
La emisión guarda un registro pendiente en la misma transacción, solo si
el cliente pidió recibir ese cupón por WhatsApp. El cupón sigue mostrándose
en pantalla aunque no se marque la casilla o falle el proveedor.

El proceso de envío toma solo los registros nuevos pendientes. No incluye
cupones históricos ni crea otro registro al volver a abrir el enlace del
cupón. Antes de enviar, verifica que el permiso y el número sigan
coincidiendo con los de la respuesta y que el cupón no esté vencido,
inactivo o agotado. Los cupones con fecha de inicio futura se pueden
notificar anticipadamente: el mensaje indica las fechas de uso.

## Configuración del servidor

Genera y aplica la migración de `cupones` en el entorno correspondiente.
La tabla nueva es `NotificacionCuponWhatsApp` y no requiere rellenar
registros existentes. El encabezado y la casilla de WhatsApp del cambio
anterior requieren que ya esté aplicada su migración de `encuestas`.
No se versionan las migraciones generadas.

```bash
python manage.py makemigrations cupones
python manage.py migrate --plan
python manage.py migrate
python manage.py check
```

Configura estas variables en el entorno privado del proceso. Usa credenciales
nuevas si los valores anteriores se compartieron en un chat o repositorio:

```dotenv
CUPON_WHATSAPP_HABILITADO=False
CUPON_WHATSAPP_CHATBOTS_CUSTOM=<valor_nuevo>
CUPON_WHATSAPP_AUTHORIZATION=<valor_nuevo>
CUPON_WHATSAPP_PLANTILLA_NOMBRE=<nombre_aprobado_del_cupon>
CUPON_WHATSAPP_PLANTILLA_ID=<id_numerico_del_cupon>
CUPON_WHATSAPP_IDIOMA=es
CUPON_WHATSAPP_COMPANY_PHONE_ID=<id_numerico_del_remitente>
```

El proceso usa `POST https://api.efperfumes.com/conversation`. Envía el
valor de `Authorization` tal como se configura, sin añadirle un prefijo.
Confirma el nombre, ID, idioma y remitente de la plantilla de cupón; los
del ejemplo `contacto_web` no corresponden a esta notificación.
No se envían la etiqueta comercial ni sus campos de captación; si la
API del proveedor exige una etiqueta, confirma la configuración del cupón
antes de habilitar el proceso.

El cuerpo usa `messageData.type = template` y cuatro parámetros de texto
en `messageData.template.components[0].parameters`, en este orden:

| Parámetro | Valor de ejemplo |
|---|---|
| Nombre | Ana |
| Descuento | 30% |
| Código | PRUEBA30-03-12345678 |
| Vigencia | del 01/01/2027 al 31/01/2027 |

El destino se envía como `51` seguido del celular peruano de nueve dígitos,
sin el signo `+`. El envío no incluye correo ni datos de publicidad.

## Primer envío y operación

1. En un entorno de prueba, emite un cupón con un número propio y marca
   la casilla de WhatsApp. En **Cupones → Notificaciones de cupones por
   WhatsApp** debe aparecer un único registro pendiente.
2. Comprueba que solo haya notificaciones de prueba pendientes en ese
   entorno y establece `CUPON_WHATSAPP_HABILITADO=True`.
3. Ejecuta:

```bash
python manage.py enviar_cupones_whatsapp --limite 1
```

El comando procesa pendientes del más antiguo al más reciente. Para
automatizarlo, programa ese comando con el usuario, directorio y Python
del entorno virtual de la aplicación; por defecto toma hasta 25
registros por ejecución. No se instala una tarea programada por defecto.
Mientras esté deshabilitado o no se ejecute, se acumularán las nuevas
notificaciones autorizadas.

El admin muestra, en solo lectura, cupón, destino enmascarado, estado,
fechas y código HTTP. No se guardan credenciales ni el cuerpo de respuesta
del proveedor. **Aceptado por HTTP** indica un `2xx`, no confirma que el
cliente recibió o leyó el mensaje. El contrato de seguimiento de entrega
del proveedor no forma parte de esta integración.

Un timeout, un `5xx` o una caída durante el proceso pueden dejar el
resultado **Incierto** o **Enviando**. El comando no vuelve a procesar
esos registros ni los rechazados: revisa primero el historial del
proveedor para evitar un doble envío. No hay reenvío automático.
