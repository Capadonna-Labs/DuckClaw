# SPEC — Webhooks

> Versión: 1.0.0 | Tipo: Integración / Comunicación entre Sistemas  
> Aplica a: Cualquier sistema que necesite notificar eventos a sistemas externos

---

## Definición

Un **Webhook** es un mecanismo de comunicación HTTP orientado a eventos en el que una aplicación (origen) notifica automáticamente a otra aplicación (destino) cuando ocurre un evento específico, enviando una petición HTTP POST al endpoint registrado.

```
POLLING (ineficiente):
  Destino → "¿Pasó algo?" → Origen  (cada N segundos, sin importar si hay eventos)
  Destino ← "No"          ← Origen
  Destino → "¿Pasó algo?" → Origen
  Destino ← "No"          ← Origen
  ... (90% de peticiones son innecesarias)

WEBHOOK (eficiente):
  [Ocurre un evento en Origen]
  Origen → HTTP POST /webhook → Destino  (solo cuando hay algo que notificar)
  Origen ← 200 OK             ← Destino
```

**Principio**: el origen "empuja" (push) la información al destino en el momento exacto en que ocurre el evento. El destino no necesita preguntar (polling).

---

## Flujo Completo

```
1. CONFIGURACIÓN (una sola vez)
   El destino registra su URL de webhook en el origen:
   "Cuando ocurra X, envíame un POST a https://mi-app.com/webhooks/origen"

2. EVENTO OCURRE
   En el sistema origen sucede algo relevante:
   pago completado, nuevo usuario, archivo subido, build finalizado...

3. DISPARO
   El origen genera el payload del evento (JSON) y hace:
   POST https://mi-app.com/webhooks/origen
   Content-Type: application/json
   X-Signature: hmac-sha256=<firma>
   { ...datos del evento... }

4. RECEPCIÓN
   El servidor destino recibe la petición.
   Verifica la firma (autenticidad).
   Responde 200 OK en menos de 2 segundos.
   Encola el procesamiento real para background.

5. PROCESAMIENTO
   El worker en background procesa el evento:
   actualiza base de datos, envía email, activa flujo de negocio...

6. RESPUESTA (al sistema origen)
   200 OK → evento recibido y procesado correctamente
   4xx    → error del destino (no reintentar sin corrección)
   5xx    → error temporal (el origen debe reintentar)
```

---

## Anatomía de un Webhook

### Headers estándar de un webhook entrante

```
POST /webhooks/stripe HTTP/1.1
Host: mi-app.com
Content-Type: application/json
Content-Length: 347
User-Agent: Stripe/1.0 (+https://stripe.com/docs/webhooks)
X-Stripe-Signature: t=1716384000,v1=abc123def456...
Idempotency-Key: evt_1OqX4k2eZvKYlo2C8D1234567
```

### Payload (body JSON) — Estructura recomendada

```json
{
  "id":           "evt_001_uuid",
  "tipo":         "pago.completado",
  "version":      "2024-01-01",
  "timestamp":    "2024-05-18T12:30:00Z",
  "origen":       "pasarela-pagos",
  "idempotency_key": "evt_001_uuid",
  "datos": {
    "id_pago":    "pay_123456",
    "monto":      49.99,
    "moneda":     "USD",
    "estado":     "completado",
    "cliente": {
      "id":       "user_789",
      "email":    "ana@email.com"
    }
  },
  "metadata": {
    "retry_count": 0,
    "environment": "production"
  }
}
```

**Campos recomendados en todo webhook:**

|Campo|Propósito|
|---|---|
|`id`|Identificador único del evento — permite deduplicación|
|`tipo`|Nombre del evento — determina cómo procesarlo|
|`timestamp`|Cuándo ocurrió el evento en el origen (ISO 8601 UTC)|
|`version`|Versión del schema del payload — para evolución sin breaking changes|
|`idempotency_key`|Igual al `id` o derivado — para procesar exactamente una vez|

---

## Seguridad — Verificación de Firma

El mayor riesgo de un webhook es que cualquiera puede hacer un POST a tu endpoint. La firma garantiza que el evento viene realmente del sistema origen.

### Mecanismo HMAC-SHA256 (estándar de la industria)

```
LADO ORIGEN (quien envía el webhook):

1. Concatenar: timestamp + "." + body_raw (string del JSON sin parsear)
2. Calcular HMAC-SHA256 con el secret compartido:
   firma = HMAC-SHA256(secret, timestamp + "." + body_raw)
3. Incluir en header:
   X-Signature: t=<timestamp>,v1=<firma_hex>

LADO DESTINO (quien recibe el webhook):

1. Extraer timestamp y firma del header X-Signature
2. Verificar que el timestamp no sea demasiado antiguo (ventana: ±5 minutos)
   Previene replay attacks: si alguien intercepta y reenvía el webhook más tarde.
3. Recalcular la firma con el mismo secret:
   firma_esperada = HMAC-SHA256(secret, timestamp + "." + body_raw)
4. Comparar firma recibida vs firma calculada usando comparación en tiempo constante
   (previene timing attacks)
5. Si coinciden → webhook auténtico → procesar
   Si no coinciden → 401 Unauthorized → descartar
```

### Reglas críticas de verificación

```
✅ Usar el body RAW (bytes sin parsear) para calcular la firma.
   Si parseas el JSON primero y luego re-serializas, puede diferir del original.

✅ Comparación en tiempo constante (constant-time comparison).
   No usar == entre strings. Usar función dedicada que no revele información
   por timing side-channel.

✅ Validar ventana de tiempo del timestamp (±5 minutos).
   Previene que un webhook interceptado sea reproducido horas después.

✅ El secret es diferente por integración, nunca compartido entre sistemas.

✅ Rotar secrets periódicamente o ante sospecha de compromiso.
```

---

## Estrategia de Respuesta: Responde Rápido, Procesa Después

```
REGLA DE ORO:
  Responder 200 OK en menos de 2-5 segundos.
  Nunca procesar la lógica de negocio de forma síncrona en el handler.

POR QUÉ:
  El sistema origen tiene un timeout (generalmente 5-30 segundos).
  Si el destino tarda más → timeout → el origen considera que falló → reintenta.
  Múltiples reintentos + procesamiento lento = procesamiento duplicado.

PATRÓN CORRECTO:
  1. Recibir webhook
  2. Verificar firma → si inválida: 401, terminar
  3. Validar estructura mínima del payload
  4. Guardar el evento en una cola / base de datos (operación rápida: <100ms)
  5. Responder 200 OK inmediatamente
  6. Worker en background procesa el evento de la cola de forma asíncrona

PATRÓN INCORRECTO:
  1. Recibir webhook
  2. Verificar firma
  3. Consultar base de datos (lento)
  4. Procesar lógica de negocio compleja (lento)
  5. Enviar emails (puede fallar)
  6. Responder 200 OK (si todo fue bien) o 500 (si algo falló)
  → Tiempo total: 10+ segundos → timeout → reintento → procesamiento duplicado
```

---

## Idempotencia en Webhooks

El sistema origen **va a reintentar** si no recibe 200 OK. Tu handler debe poder procesar el mismo evento múltiples veces sin efectos secundarios.

```
PROBLEMA:
  Evento "pago.completado" llega.
  Handler procesa: crea orden, envía email de confirmación.
  La red falla al enviar 200 OK → timeout en el origen.
  Origen reintenta → el evento llega de nuevo.
  Handler procesa de nuevo: crea orden DUPLICADA, envía email DUPLICADO.

SOLUCIÓN — Tabla de eventos procesados:

  Al recibir:
    1. Extraer event_id del payload
    2. Buscar event_id en tabla "eventos_procesados"
    3. Si YA EXISTE → ya fue procesado → responder 200 OK sin hacer nada más
    4. Si NO EXISTE → procesar → guardar event_id en tabla → responder 200 OK

  Estructura mínima de tabla "eventos_procesados":
    event_id    : string (PK)
    tipo        : string
    procesado_en: timestamp
    resultado   : string (ok / error)
    expira_en   : timestamp (limpiar registros antiguos con TTL)
```

---

## Política de Reintentos (Retry Policy)

Los sistemas de webhooks bien diseñados reintentan automáticamente los envíos fallidos.

### Estrategia de Backoff Exponencial con Jitter

```
Reintento 1: esperar  30 segundos  + jitter aleatorio (0-5s)
Reintento 2: esperar   1 minuto    + jitter
Reintento 3: esperar   5 minutos   + jitter
Reintento 4: esperar  30 minutos   + jitter
Reintento 5: esperar   2 horas     + jitter
Reintento 6: esperar  12 horas     + jitter
Reintento 7: esperar  24 horas     + jitter
Después de N reintentos fallidos → marcar como DEAD, notificar al dueño.

Jitter: valor aleatorio sumado al tiempo de espera.
Propósito: evitar que múltiples reintentos de distintos eventos lleguen simultáneamente
(thundering herd en el receptor).
```

### Cuándo NO reintentar

```
NO REINTENTAR si el destino responde:
  400 Bad Request    → el payload es inválido, reintentar no lo corregirá
  401 Unauthorized   → firma inválida, reintentar no ayudará
  404 Not Found      → el endpoint no existe
  410 Gone           → el endpoint fue eliminado explícitamente

SÍ REINTENTAR si el destino responde:
  408 Request Timeout → el destino tardó demasiado
  429 Too Many Requests → rate limiting, respetar Retry-After header
  500 Internal Server Error → error temporal del servidor
  502 Bad Gateway           → servidor caído temporalmente
  503 Service Unavailable   → mantenimiento, respetar Retry-After
  504 Gateway Timeout       → timeout en backend
  Sin respuesta (timeout)   → red caída o servidor no disponible
```

---

## Registro y Trazabilidad

```
LOGS MÍNIMOS A REGISTRAR POR EVENTO RECIBIDO:
  - event_id
  - tipo de evento
  - timestamp de recepción
  - origen (sistema que lo envió)
  - resultado de verificación de firma (ok / inválida)
  - tiempo de procesamiento
  - resultado (procesado / duplicado / error)
  - retry_count (si viene en el payload o header)

LOGS DE EVENTOS ENVIADOS (webhooks salientes):
  - event_id
  - tipo de evento
  - url destino
  - timestamp de intento
  - status code de respuesta
  - tiempo de respuesta
  - número de intento (1 = primer envío, 2+ = reintento)
  - resultado final (entregado / dead)
```

---

## Webhook Dashboard — Funcionalidades Recomendadas

Para sistemas que envían webhooks a clientes/integraciones:

```
HISTORIAL DE EVENTOS
  Lista de todos los eventos disparados con estado:
  entregado ✓ | reintentando ↺ | fallido ✗ | dead ✗✗

DETALLE DE EVENTO
  Payload enviado (JSON)
  Headers enviados
  Respuesta recibida (status code + body)
  Historial de intentos con timestamps

REINTENTO MANUAL
  Botón para re-enviar manualmente un evento dead.
  Útil para recuperar integraciones caídas sin esperar al cliente.

LOGS EN TIEMPO REAL
  Stream de eventos entrantes/salientes.

ALERTAS
  Notificar cuando una URL de webhook tiene alta tasa de fallos.
```

---

## Tipos de Webhooks

### Outgoing Webhook (De salida — el más común)

```
Tu sistema emite eventos → sistemas externos reciben.
Ejemplo: Tu plataforma de pagos notifica a los comercios sobre pagos.
Gestión: Registro de URLs por cliente, retry policy, firma, logs.
```

### Incoming Webhook (De entrada)

```
Sistemas externos te notifican → tu sistema recibe y procesa.
Ejemplo: Stripe te notifica sobre pagos, GitHub sobre push events.
Gestión: Verificar firma, idempotencia, respuesta rápida, procesamiento async.
```

---

## Casos de Uso Comunes por Industria

|Dominio|Eventos típicos|
|---|---|
|**E-commerce / Pagos**|`pago.completado`, `pago.fallido`, `pedido.enviado`, `devolución.iniciada`|
|**Email / Marketing**|`email.abierto`, `enlace.clickeado`, `usuario.suscrito`, `rebote.detectado`|
|**DevOps / CI-CD**|`build.completado`, `deploy.exitoso`, `alerta.activada`, `issue.creado`|
|**Mensajería**|`mensaje.recibido`, `usuario.mencionado`, `canal.creado`|
|**Almacenamiento**|`archivo.subido`, `cuota.excedida`, `carpeta.compartida`|
|**IoT**|`sensor.alerta`, `dispositivo.conectado`, `umbral.superado`|

---

## Buenas Prácticas

### ✅ Siempre

```
1. VERIFICAR FIRMA antes de procesar cualquier evento.
2. RESPONDER en menos de 2 segundos — encolar el procesamiento.
3. IMPLEMENTAR IDEMPOTENCIA — el mismo evento puede llegar múltiples veces.
4. REGISTRAR todos los eventos recibidos con su resultado.
5. VALIDAR estructura mínima del payload antes de procesar.
6. USAR HTTPS siempre — nunca exponer endpoint de webhook en HTTP.
7. VERSIONAR el schema del payload — evolución sin breaking changes.
8. RETORNAR CÓDIGOS HTTP SEMÁNTICOS — 200 OK, 400 Bad Request, 500 Error.
```

### ❌ Nunca

```
1. Procesar lógica compleja síncronamente en el handler del webhook.
2. Confiar en un webhook sin verificar su firma.
3. Ignorar el campo event_id (sin idempotencia).
4. Exponer el webhook en HTTP sin TLS.
5. Almacenar el secret del webhook en el código fuente.
6. Retornar siempre 200 OK sin importar el resultado (enmascara errores).
7. Reintentar indefinidamente sin política de dead letter.
```

---

## Checklist de Implementación

### Seguridad

- [ ] Verificación de firma HMAC implementada en el handler
- [ ] Validación de ventana de tiempo del timestamp (±5 minutos)
- [ ] Comparación de firmas en tiempo constante
- [ ] Endpoint expuesto solo por HTTPS
- [ ] Secret almacenado en variables de entorno / vault (nunca en código)

### Fiabilidad

- [ ] Procesamiento asíncrono: respuesta inmediata + cola para procesamiento
- [ ] Idempotencia implementada: tabla de event_ids procesados
- [ ] Retry policy con backoff exponencial y jitter
- [ ] Dead letter queue para eventos fallidos definitivamente
- [ ] Manejo diferenciado de 4xx (no reintentar) vs 5xx (reintentar)

### Observabilidad

- [ ] Log de cada evento recibido: id, tipo, resultado, tiempo
- [ ] Log de cada intento de envío (webhooks salientes): url, status, intento N
- [ ] Alertas por alta tasa de fallos en un endpoint
- [ ] Dashboard con historial y estado de eventos

---

> **WEBHOOK = Eventos en Tiempo Real + Automatización + Integración + Eficiencia**  
> La clave es: verificar, responder rápido, procesar después, y nunca asumir que el evento llega una sola vez.