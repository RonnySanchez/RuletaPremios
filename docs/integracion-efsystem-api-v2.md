# Integración de EFSystem con RuletaPremios: API v2 de cupones

Guía para implementar el flujo de caja con el contrato de la rama de trabajo
`codex/campana-cupon-directo`. No certifica que v2 esté desplegada ni que la
integración ya exista en EFSystem. Las rutas anteriores de cupones siguen
disponibles, pero no deben usarse como alternativa para canjear cupones
que requieren validar presentación, cantidad o identidad.

## Conexión y autenticación

- URL base: configurar la del ambiente habilitado. Para una prueba local con Django en el puerto 8000: `http://127.0.0.1:8000`. Usar HTTPS fuera del entorno local.
- Conservar la barra final de las rutas. Enviar `Content-Type: application/json` en los POST.
- Para las operaciones de negocio, enviar `Authorization: Bearer <access>`. No escribir credenciales, tokens JWT, enlaces privados de participación ni documentos personales en los logs.
- Obtener tokens con `POST /api/token/`. El entorno del proyecto configura 5 minutos para el token de acceso y 1 día para el token de refresco. Renovar con `POST /api/token/refresh/`; si el refresco ya no es válido, volver a autenticar la misma cuenta de integración.

Solicitud de acceso:

```json
{"username": "usuario_de_integracion", "password": "<secreto>"}
```

Respuesta `200`:

```json
{"refresh": "<jwt_refresh>", "access": "<jwt_access>"}
```

Solicitud de refresco:

```json
{"refresh": "<jwt_refresh>"}
```

Respuesta `200`:

```json
{"access": "<nuevo_jwt_access>"}
```

## Compra que genera el cupón

Al registrar la compra inicial, llamar a `POST /api/enc_t/` con el código
EFSystem de la tienda, el código del ticket y su importe. Este endpoint no es
parte de v2 y no consume un cupón.

```json
{"tienda_id": 3, "codigo": "B003-000184", "monto": "150.00"}
```

Ejemplo de respuesta HTTP `200` para una campaña de premio directo:

```json
{
  "Resp": "http://127.0.0.1:8000/polls/contacto/f31a8408-17aa-4319-b35d-93310b8ff221/",
  "status": 200,
  "encabezado": "Participa en la campaña",
  "texto": "Completa el formulario para recibir tu cupón",
  "codigo": "B003-000184"
}
```

- Solo presentar o imprimir el enlace si `status == 200` y `Resp` no está vacío. Los textos de impresión dependen de la campaña.
- Con HTTP `200`, los estados de negocio `0`, `1`, `2` y `3` indican, respectivamente: tienda no encontrada, sin campaña elegible, importe inferior al mínimo y conflicto de campañas vigentes. No abrir un enlace en estos casos. Un importe o código de ticket mal formado devuelve HTTP `400`.
- La tienda se busca por `id_efsystem`, no por el ID interno de Django. Para esta campaña se prevé configurar el mínimo de emisión de la tienda en S/150, incluido ese importe. No confundirlo con `minimo_compra`, que es una restricción independiente del canje.
- El cliente abre `Resp`, completa el formulario y ve el código emitido en RuletaPremios. EFSystem no genera el código ni llama a `usar/` en esta etapa.
- `enc_t/` no ofrece la garantía de reintento de `usar/`: una nueva llamada puede registrar otra consulta y devolver otro enlace. Conservar el enlace recibido para el ticket; no tratar las repeticiones como una recuperación idempotente de la misma respuesta.

## Venta en la que se canjea

1. Leer el código y, opcionalmente, consultar los datos del cupón.
2. Identificar la unidad elegible en el ticket y verificar la política de no acumulación en EFSystem.
3. Enviar la compra a `validar/`. Mostrar el descuento devuelto. Si cambia el ticket, la unidad elegida o su importe, volver a validar antes del canje.
4. Con la venta lista para confirmar, guardar de forma persistente la referencia, la clave y el cuerpo del canje. Enviar ese cuerpo a `usar/`.
5. Solo con HTTP `200`, cerrar la venta con `datos_registrados.monto_descuento` y asociar el registro de canje a la venta. Si no hay un resultado concluyente, dejar el canje pendiente de resolución; no finalizar la venta suponiendo que el cupón está disponible.

Para la campaña del ejemplo, el cupón es transferible, de un solo uso, del
30 % sobre **una unidad de perfume de 100 ml**. Su vigencia configurada va
del 1 al 31 de enero de 2027, inclusive, en hora de Lima. No enviar datos de
identificación para este cupón. En una prueba antes de enero, usar un cupón
de pruebas con vigencia actual.

**No acumulación.** La API recibe datos de la unidad beneficiada, no las
promociones ni las líneas completas del ticket. EFSystem debe impedir que
el cupón se sume a otro descuento sobre la misma unidad; esto incluye
descuentos globales que reduzcan el precio de esa unidad. Para descuentos
limitados a otros artículos, aplicar la regla comercial definida para la
campaña: v2 no impone ni verifica esa decisión. Si se permiten, esos
descuentos pueden estar reflejados en el total previo al cupón;
`monto_descuento` nunca debe incluirlos.

### 1. Consultar el cupón

`GET /api/v2/cupones/consultar/NAV30-PRUEBA/` sin cuerpo.

Ejemplo de respuesta `200`:

```json
{
  "codigo": "NAV30-PRUEBA",
  "tipo": "PORCENTAJE",
  "valor": "30.00",
  "categorias": [],
  "presentaciones": [{"nombre": "Perfume 100 ml", "codigo_efsystem": "0100"}],
  "cantidad_maxima_productos": 1,
  "minimo_compra": "0.00",
  "maximo_descuento": null,
  "inicio": "2027-01-01T00:00:00-05:00",
  "vencimiento": "2027-01-31T23:59:59.999999-05:00",
  "transferible": true,
  "requiere_identificacion": false,
  "is_active": true,
  "limite_usos": 1,
  "usos_actuales": 0
}
```

La búsqueda de códigos no distingue mayúsculas de minúsculas. Codificar el
código como segmento de URL. Un resultado `200` indica que el cupón está
activo en ese momento, no que aplica al ticket ni que su uso está reservado.
La ruta devuelve `404` si el cupón no existe o no está activo.

### 2. Validar la compra sin consumir

`POST /api/v2/cupones/validar/`. Ejemplo: el total antes del cupón es S/220 y
la unidad elegida cuesta S/160. `0100` es el código de presentación de ejemplo,
no un valor que deba fijarse en EFSystem.

```json
{
  "codigo": "NAV30-PRUEBA",
  "tienda": "3",
  "monto_total": "220.00",
  "presentacion_codigo": "0100",
  "cantidad_productos": 1,
  "monto_aplicable": "160.00"
}
```

| Campo | Contrato |
|---|---|
| `codigo` | Obligatorio. Código del cupón, no el código del ticket de origen. |
| `tienda` | Obligatorio. Código `id_efsystem` de la tienda donde se canjea. En `enc_t/` el nombre del campo es `tienda_id`. |
| `monto_total` | Obligatorio. Total previo a aplicar este cupón. Se usa para evaluar el mínimo del cupón, si corresponde. |
| `presentacion_codigo` | Obligatorio si el cupón restringe presentaciones. Enviar como cadena para conservar los ceros iniciales y usar `presentaciones[].codigo_efsystem` como referencia. |
| `cantidad_productos` | Obligatorio si hay cantidad máxima. Es la cantidad **beneficiada** y no la cantidad total del ticket. Para esta campaña: `1`. |
| `monto_aplicable` | Obligatorio si hay cantidad máxima. Base del descuento de las unidades beneficiadas, mayor que cero y no superior al total. Para cupones sin límite de unidades, si se omite, la base es el total. |
| `categoria` | Obligatorio si `categorias` contiene restricciones. Enviar uno de los **nombres** devueltos en `categorias`, no un ID. |
| `tipo_identificacion`, `numero_identificacion` | Obligatorios si el cupón no es transferible. Tipos admitidos: `DNI`, `CE` y `PASAPORTE`. El número se envía como texto, hasta 20 caracteres. |

Usar cadenas decimales con punto y dos posiciones para los importes (hasta
10 dígitos en total, sin separadores de miles). En porcentajes, el servidor
aplica el porcentaje a la base, respeta el tope configurado si existe y
redondea a dos decimales con `ROUND_HALF_UP`. En cupones de monto fijo no
descuenta más que la base aplicable.

Respuesta `200` (extracto; `cupon` incluye los mismos campos que en la consulta):

```json
{
  "valido": true,
  "descuento_calculado": "48.00",
  "cupon": {"codigo": "NAV30-PRUEBA", "tipo": "PORCENTAJE", "valor": "30.00"}
}
```

EFSystem muestra **S/172.00** a pagar: S/220.00 menos S/48.00. La validación
no incrementa el contador ni garantiza que otro cajero no canjee el cupón
antes de confirmar.

### 3. Confirmar el uso

`POST /api/v2/cupones/usar/`. Repetir los campos de compra de `validar/` y
añadir los campos de canje:

```json
{
  "codigo": "NAV30-PRUEBA",
  "tienda": "3",
  "monto_total": "220.00",
  "presentacion_codigo": "0100",
  "cantidad_productos": 1,
  "monto_aplicable": "160.00",
  "nro_referencia": "B003-000521",
  "idempotency_key": "1ecbcdfa-3f87-41ee-a637-7d76622e38a3",
  "monto_descuento": "48.00"
}
```

- `idempotency_key`: obligatoria, hasta 100 caracteres. Generar un UUID único por operación lógica de canje y conservarlo para los reintentos. No reutilizarlo para otra venta.
- `nro_referencia`: opcional en la API, recomendado en EFSystem. Usar una referencia estable de la venta de canje (hasta 255 caracteres), no la del ticket de emisión. La referencia no sustituye a la clave de idempotencia.
- `monto_descuento`: opcional. Enviar el importe del **cupón** mostrado en caja. Si se envía, el servidor exige que coincida con su propio cálculo; no usa ese valor para fijar el descuento. Si se omite, el servidor calcula y registra el importe.

Respuesta `200` del canje inicial y de un reintento equivalente:

```json
{
  "mensaje": "Cupon consumido correctamente.",
  "datos_registrados": {
    "codigo": "NAV30-PRUEBA",
    "tienda": "3",
    "idempotency_key": "1ecbcdfa-3f87-41ee-a637-7d76622e38a3",
    "nro_referencia": "B003-000521",
    "monto_total": "220.00",
    "monto_descuento": "48.00",
    "cantidad_productos": 1,
    "monto_aplicable": "160.00",
    "presentacion_codigo": "0100",
    "fecha_uso": "2027-01-10T15:20:30-05:00"
  }
}
```

El servidor revalida y registra el uso junto con el contador en una
transacción. Si el cupón es de uso único, dos cajas con claves distintas
no pueden obtener dos canjes exitosos. Un reintento válido devuelve
`datos_registrados` del canje ya registrado, incluso si el cupón ahora
está agotado o vencido.

## Manejo de errores

| Situación | Respuesta | Acción de EFSystem |
|---|---|---|
| Token vencido o inválido | `401`, normalmente con `detail`. | Renovar el JWT o autenticar de nuevo la misma cuenta. Si se reintenta un canje, conservar su clave y datos. |
| Cupón inexistente o inactivo en consulta | `404`, con `detail` o `error`. | Informar que no está disponible. No cambiar a la API anterior. Si ya hay un canje incierto, recuperar su resultado por `usar/` con la clave original, no por consulta. |
| Cupón inexistente en validación o canje | `404`. | Revisar el código. `validar/` devuelve también `valido: false`. |
| Campos faltantes, formatos incorrectos o tienda desconocida | `400`, con un objeto de errores por campo. | Corregir la solicitud. No esperar que todos los errores incluyan `error` o `valido`. |
| Restricción incumplida: vigencia, uso agotado, presentación, mínimo, identidad o cantidad | `400`, con `error`; en `validar/`, también `valido: false`. | Mostrar el motivo y no aplicar el cupón a esa compra. |
| Importe confirmado diferente del cálculo | `409`, con `error` y `descuento_calculado`. | Este intento no consume ni reserva la clave. Revisar el ticket, volver a validar y confirmar el importe corregido antes de reintentar. |
| Clave usada con datos de canje distintos | `409`, con `error`, sin `descuento_calculado`. | No generar otra clave para forzar el canje. Conciliar la venta con el cuerpo original que se guardó. |
| Sin respuesta, timeout, desconexión, `5xx` o respuesta ilegible de `usar/` | Resultado desconocido. | No asumir éxito ni fracaso. Reintentar con la misma cuenta, clave y datos; aplicar una espera creciente y limitar los reintentos automáticos. Si no se resuelve, dejarlo pendiente para revisión. |

Ejemplo de restricción en `validar/`, HTTP `400`:

```json
{"valido": false, "error": "El cupon no aplica a la presentacion indicada."}
```

Ejemplo de diferencia de importe en `usar/`, HTTP `409`:

```json
{
  "error": "El descuento confirmado no coincide con el calculado.",
  "descuento_calculado": "48.00"
}
```

Ejemplo de conflicto de clave en `usar/`, HTTP `409`:

```json
{"error": "La clave de idempotencia ya fue usada con otros datos de canje."}
```

El cliente debe manejar el código HTTP y la estructura del cuerpo, no
depender del texto exacto del mensaje. Los errores de infraestructura
pueden no devolver JSON.

## Recuperación y conciliación

- Guardar el cuerpo enviado a `usar/` antes del primer intento y mantenerlo
  sin cambios mientras el resultado sea incierto. La identidad de la cuenta
  también se compara; renovar el token no cambia la cuenta. La API compara
  los datos de canje, no el orden de las claves del JSON.
- Un `200` repetido confirma el mismo uso, no uno nuevo. No volver a cobrar
  ni cerrar la venta por segunda vez. Usar la referencia y la clave guardadas
  para reconocer una venta ya procesada en EFSystem.
- Si RuletaPremios confirma el canje pero falla el cobro o el cierre en
  EFSystem, guardar el resultado y enviar la operación a conciliación.
  **No existe reversión automática ni endpoint de anulación en v2.**
  No borrar la operación pendiente ni liberar el cupón por suposición.

## Pruebas de integración en caja

- Consulta y validación no consumen el cupón; un canje posterior devuelve `datos_registrados`.
- Ticket de S/220 con una unidad de S/160: cupón de S/48 y total a cobrar de S/172. Confirmar S/66 devuelve `409` y deja el cupón disponible.
- Probar una presentación distinta, dos unidades beneficiadas, base aplicable superior al total, vigencia incorrecta y cupón agotado.
- Verificar la regla de promociones en EFSystem con descuento sobre el mismo perfume, sobre otro producto y sobre todo el ticket.
- Simular dos cajas, pérdida de respuesta después de registrar el uso, renovación de JWT durante un reintento y reenvío de la misma clave con una venta diferente.
- Simular que falla el cierre de venta después de un canje confirmado; comprobar que queda un caso identificable para conciliación.
