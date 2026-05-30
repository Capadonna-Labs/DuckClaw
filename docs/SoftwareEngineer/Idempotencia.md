# SPEC — Idempotencia en APIs

> Versión: 1.0.0 | Tipo: Diseño de APIs / Fiabilidad de Sistemas  
> Aplica a: Cualquier API, servicio o sistema distribuido

---

## Definición

Una operación es **idempotente** si ejecutarla una o múltiples veces produce exactamente el mismo resultado que ejecutarla una sola vez. El estado final del sistema es idéntico independientemente del número de ejecuciones.

```
OPERACIÓN NO IDEMPOTENTE:
  POST /pedidos  →  Pedido #101 creado
  POST /pedidos  →  Pedido #102 creado  ← ¡DUPLICADO!
  POST /pedidos  →  Pedido #103 creado  ← ¡DUPLICADO!

OPERACIÓN IDEMPOTENTE:
  POST /pedidos + Idempotency-Key: abc-123  →  Pedido #101 creado
  POST /pedidos + Idempotency-Key: abc-123  →  Pedido #101 (mismo resultado)
  POST /pedidos + Idempotency-Key: abc-123  →  Pedido #101 (mismo resultado)
```

**Principio central**: La idempotencia hace que los sistemas sean resilientes ante reintentos, timeouts y fallos de red — inevitables en sistemas distribuidos.

---

## Por qué es Crítico en Sistemas Distribuidos

En una red, cualquier petición puede fallar de formas ambiguas:

```
ESCENARIOS DONDE LA IDEMPOTENCIA SALVA:

1. TIMEOUT EN EL CLIENTE
   El cliente envía POST /cobrar con monto=100.
   El servidor procesa, cobra el dinero.
   La respuesta se pierde en la red → timeout en el cliente.
   El cliente no sabe si se cobró o no.
   El cliente reintenta → SIN idempotencia: cobro duplicado.
                       → CON idempotencia: respuesta del cobro original.

2. ERROR DE RED EN RESPUESTA
   Petición llega, se procesa correctamente.
   Al retornar la respuesta: error de red.
   El cliente recibe error → asume que falló → reintenta.
   SIN idempotencia: segunda ejecución duplica el efecto.
   CON idempotencia: segunda ejecución retorna resultado original.

3. RETRY AUTOMÁTICO DE INFRAESTRUCTURA
   Load balancers, SDKs, message queues reintentan automáticamente.
   Sin idempotencia: cada reintento crea datos duplicados.

4. DOBLE CLIC DEL USUARIO
   El usuario hace clic dos veces en "Pagar" antes de que cargue.
   Sin idempotencia: dos cobros.
   Con idempotencia: un cobro, dos respuestas idénticas.
```

---

## Idempotencia por Método HTTP

### Métodos naturalmente idempotentes

```
GET — Siempre idempotente
  Obtiene datos sin modificar estado.
  Múltiples GET al mismo recurso → mismo resultado.
  Garantía: RFC 7231.

PUT — Siempre idempotente
  Reemplaza el recurso completo con los datos enviados.
  PUT /usuarios/123 { "nombre": "Ana" }
  Llamar 1 vez o 10 veces → el usuario 123 siempre queda con nombre "Ana".

DELETE — Idempotente (con manejo correcto)
  El primer DELETE elimina el recurso → 204 No Content.
  El segundo DELETE: el recurso ya no existe → 404 Not Found.
  El estado final (recurso no existe) es el mismo.
  IMPORTANTE: retornar 404 en el segundo DELETE, no 500.

HEAD, OPTIONS — Siempre idempotentes (no modifican estado)
```

### Métodos NO idempotentes por defecto

```
POST — No idempotente por defecto
  Crea un nuevo recurso cada vez que se ejecuta.
  POST /pedidos → Pedido #1
  POST /pedidos → Pedido #2 (diferente)
  SOLUCIÓN: Implementar Idempotency Keys.

PATCH — Depende de la operación
  PATCH idempotente:   { "nombre": "Ana" }           → siempre resultado igual
  PATCH no idempotente: { "saldo": { "incrementar": 100 } } → suma N veces
```

---

## Idempotency Key — Implementación

La **Idempotency Key** es un identificador único que el cliente genera y envía en el header de la petición. El servidor lo usa para detectar y deduplicar peticiones repetidas.

### Flujo completo

```
CLIENTE:
  1. Antes de enviar la petición, generar un ID único: UUID v4
  2. Incluirlo en el header: Idempotency-Key: <uuid>
  3. Guardar localmente: { key: uuid, petición: { endpoint, body, timestamp } }
  4. Si hay que reintentar: usar EXACTAMENTE el mismo uuid

SERVIDOR — Al recibir la petición:
  1. Extraer el valor de Idempotency-Key del header
  2. Si no viene el header:
     → Para operaciones críticas: retornar 400 Bad Request (requerir la key)
     → Para operaciones no críticas: procesar normalmente sin idempotencia
  3. Buscar la key en el almacén de idempotencia
  4. Si YA EXISTE la key:
     → Retornar la respuesta almacenada (mismo status code + mismo body)
     → NO ejecutar la operación de nuevo
  5. Si NO EXISTE la key:
     → Guardar la key en el almacén con estado "en_proceso"
     → Ejecutar la operación
     → Guardar el resultado (status code + body)
     → Actualizar la key a estado "completado"
     → Retornar el resultado al cliente
```

### Header estándar

```
Request:
  POST /pagos HTTP/1.1
  Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
  Content-Type: application/json

  { "monto": 100, "moneda": "USD", "cliente_id": "user_789" }

Response (primera vez — procesado):
  HTTP/1.1 201 Created
  Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
  Idempotent-Replayed: false

  { "id": "pay_001", "estado": "completado", "monto": 100 }

Response (segunda vez — mismo resultado):
  HTTP/1.1 201 Created
  Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
  Idempotent-Replayed: true

  { "id": "pay_001", "estado": "completado", "monto": 100 }
```

### Almacén de Idempotency Keys — Schema

```
Tabla: idempotency_keys

Campo             Tipo          Descripción
─────────────────────────────────────────────────────────────────
key               STRING (PK)   El UUID enviado por el cliente
endpoint          STRING        Endpoint de la operación (/pagos)
request_hash      STRING        Hash del body de la petición (detectar misma key, body diferente)
status            ENUM          en_proceso | completado | error
response_status   INTEGER       HTTP status code de la respuesta
response_body     JSON          Body completo de la respuesta
created_at        TIMESTAMP     Cuándo se recibió la primera petición
expires_at        TIMESTAMP     Cuándo se puede eliminar este registro (TTL)
user_id           STRING        Quién hizo la petición (scope de la key)
```

### Validaciones adicionales en el servidor

```
1. MISMA KEY, BODY DIFERENTE → Error 422
   Si llega la misma Idempotency-Key pero con un body distinto,
   es una inconsistencia del cliente.
   Retornar 422 Unprocessable Entity con mensaje explicativo.
   NO procesar la segunda petición.

2. KEY EN PROCESO → Responder apropiadamente
   Si llega una petición con una key que está en estado "en_proceso"
   (la primera ejecución aún no terminó):
   Opción A: Retornar 409 Conflict (el cliente debe esperar y reintentar)
   Opción B: Esperar a que termine (long polling, máx. N segundos)

3. TTL DE LAS KEYS
   Las keys no deben guardarse indefinidamente.
   TTL recomendado: 24 horas a 30 días según la criticidad.
   Pasado el TTL: una nueva petición con la misma key se trata como nueva.
   El cliente debe generar keys nuevas para operaciones realmente distintas.
```

---

## Scope de la Idempotency Key

La key debe tener scope para prevenir colisiones entre usuarios:

```
SIN SCOPE (inseguro):
  Usuario A envía key: "abc-123"
  Usuario B envía key: "abc-123" → ¡Colisión! Recibiría la respuesta del usuario A.

CON SCOPE (correcto):
  La key se valida siempre junto al ID del usuario autenticado.
  La búsqueda en el almacén usa: (key + user_id) como identificador compuesto.
  Colisiones entre usuarios son imposibles.

Alternativa: el servidor puede prefijar la key internamente:
  user_123:abc-123 → clave interna del almacén
```

---

## Idempotencia en Operaciones Compuestas

Cuando una operación involucra múltiples pasos, la idempotencia debe cubrir la transacción completa:

```
EJEMPLO: "Cobrar y actualizar inventario"

Paso 1: Cobrar al cliente       ← puede fallar después de cobrar
Paso 2: Actualizar inventario   ← puede fallar después del paso 1

SIN IDEMPOTENCIA:
  Reintento → cobra de nuevo → inventario incorrecto

CON IDEMPOTENCIA:
  Al reintentar con la misma key:
  - Si el paso 1 ya se completó: no volver a cobrar
  - Si el paso 2 no se completó: continuar desde el paso 2
  Requiere: guardar el estado de progreso junto a la key.

PATRÓN: Saga idempotente
  Cada paso de la saga verifica si ya fue ejecutado antes de proceder.
  Cada paso tiene su propia sub-key derivada de la key principal:
    key principal: abc-123
    step_1_key:    abc-123:cobro
    step_2_key:    abc-123:inventario
```

---

## Diseño de APIs Idempotentes — Guía de Referencia

### Para el equipo que diseña el endpoint

```
OPERACIONES QUE DEBEN SER IDEMPOTENTES (críticas):
  ✓ Cobros y pagos
  ✓ Transferencias bancarias
  ✓ Creación de pedidos / reservas
  ✓ Envío de emails transaccionales
  ✓ Activación de cuentas
  ✓ Cualquier operación con efecto económico

OPERACIONES DONDE LA IDEMPOTENCIA ES RECOMENDADA:
  ✓ Actualizaciones de estado de recursos
  ✓ Notificaciones push
  ✓ Webhooks salientes

OPERACIONES DONDE LA IDEMPOTENCIA ES OPCIONAL:
  ✓ Consultas de logs o histórico (GET)
  ✓ Métricas y analytics
```

### Para el equipo que consume el endpoint

```
RESPONSABILIDADES DEL CLIENTE:
  1. Generar el UUID antes de la petición (UUID v4, criptográficamente aleatorio).
  2. Guardar el UUID localmente asociado a la operación.
  3. Reintentar con el MISMO UUID ante timeout o error 5xx.
  4. Generar un UUID NUEVO para una operación genuinamente distinta.
  5. No reutilizar UUIDs de operaciones anteriores completadas.
  6. Implementar backoff exponencial entre reintentos.
```

---

## Casos Límite y Manejo de Errores

```
CASO: Primera petición falló con error del servidor (500)
  ¿Guardar el error como resultado idempotente?
  Opción A: SÍ — guardar el 500, retornarlo en reintentos.
            El cliente sabe que falló y puede decidir con un UUID nuevo.
  Opción B: NO — no guardar el error, permitir reintento con misma key.
  RECOMENDADO: Guardar errores 5xx como resultado transitorio con TTL corto (30s).
               Guardar errores 4xx como resultado definitivo.

CASO: Petición en proceso tarda demasiado
  El cliente reintenta mientras la primera aún procesa.
  Retornar 202 Accepted con status "en_proceso".
  El cliente puede hacer polling: GET /operaciones/{key}

CASO: Key expirada (el TTL venció)
  La misma key se trata como nueva operación.
  Si el cliente necesita idempotencia después del TTL: operación imposible de deduplicar.
  MITIGACIÓN: Diseñar el sistema para que el cliente sepa el resultado antes de que expire el TTL.
```

---

## Buenas Prácticas

### ✅ Siempre

```
1. REQUERIR Idempotency-Key en operaciones críticas (pagos, creación de recursos únicos).
2. RETORNAR exactamente la misma respuesta (mismo status + mismo body) en duplicados.
3. INCLUIR header Idempotent-Replayed: true en respuestas reproducidas.
4. DEFINIR TTL para las keys (limpiar el almacén periódicamente).
5. VALIDAR que la misma key con body diferente retorna error 422.
6. USAR UUID v4 o equivalente criptográficamente seguro para las keys.
7. DOCUMENTAR en la API: qué endpoints soportan idempotencia y cómo usarla.
8. SCOPE de la key: siempre asociada al usuario autenticado.
```

### ❌ Nunca

```
1. Permitir que POST repita efectos secundarios sin Idempotency-Key en operaciones críticas.
2. Guardar keys indefinidamente sin TTL.
3. Aceptar la misma key con body diferente como operación válida.
4. Retornar respuestas distintas para la misma key (inconsistencia).
5. Generar la key en el servidor (la genera el CLIENTE para controlar reintentos).
6. Compartir scope de keys entre usuarios distintos.
```

---

## Checklist de Implementación

### Diseño del endpoint

- [ ] Identificadas operaciones críticas que requieren idempotencia
- [ ] Header `Idempotency-Key` documentado en la especificación de la API
- [ ] TTL de las keys definido y justificado
- [ ] Comportamiento documentado: misma key + body diferente = 422

### Almacén de keys

- [ ] Schema de la tabla definido con todos los campos necesarios
- [ ] Índice en (key + user_id) para búsquedas eficientes
- [ ] Proceso de limpieza de keys expiradas (TTL/cron job)
- [ ] Manejo de concurrencia: dos peticiones con la misma key simultáneas

### Servidor

- [ ] Extracción y validación del header Idempotency-Key
- [ ] Búsqueda en almacén antes de ejecutar la operación
- [ ] Almacenamiento de resultado (status + body) tras operación exitosa
- [ ] Header `Idempotent-Replayed: true` en respuestas reproducidas
- [ ] Manejo del caso "en_proceso" (petición concurrente con misma key)

### Cliente

- [ ] Generación de UUID v4 antes de cada operación nueva
- [ ] Reintento con el mismo UUID ante timeout o error 5xx
- [ ] Backoff exponencial entre reintentos
- [ ] Almacenamiento local del UUID asociado a cada operación pendiente

---

> **IDEMPOTENCIA = Seguridad + Confianza + Consistencia + Resiliencia = APIs Confiables**  
> En sistemas distribuidos, los reintentos no son un error — son una garantía. La idempotencia los hace seguros.