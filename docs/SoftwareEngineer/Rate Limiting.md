# SPEC — Rate Limiting

> Versión: 1.0.0 | Tipo: Seguridad / Resiliencia de APIs  
> Aplica a: Cualquier API pública, interna o de terceros

---

## Definición

**Rate Limiting** es una técnica de control que restringe la cantidad de peticiones que un cliente (usuario, IP, API key o aplicación) puede realizar a una API en un período de tiempo determinado.

```
SIN RATE LIMITING:
  Cliente malicioso / script → 10,000 req/seg → Servidor sobrecargado → Caído
  Todos los usuarios afectados.

CON RATE LIMITING:
  Cliente normal  → 100 req/min → Procesado normalmente
  Cliente abusivo → 101 req/min → 429 Too Many Requests (bloqueado temporalmente)
  El servidor y los demás clientes siguen funcionando.
```

**Objetivo**: proteger la infraestructura, garantizar calidad de servicio para todos los usuarios y controlar el consumo de recursos.

---

## Flujo de Decisión

```
Petición entrante
       │
       ▼
┌─────────────────────────────────┐
│  Identificar al cliente         │
│  (IP / user_id / api_key / app) │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  Obtener contador actual         │
│  del almacén (Redis, etc.)       │
└────────────────┬────────────────┘
                 │
       ┌─────────┴──────────┐
       │                    │
  Dentro del límite    Límite excedido
       │                    │
       ▼                    ▼
  Procesar petición    Retornar 429
  Incrementar contador Too Many Requests
  Retornar respuesta   + Headers de info
```

---

## Algoritmos de Rate Limiting

### Fixed Window (Ventana Fija)

```
CONCEPTO:
  El tiempo se divide en ventanas de tamaño fijo (ej: 1 minuto).
  El contador se reinicia al inicio de cada ventana.

  00:00 - 01:00: permite máx. 100 peticiones
  01:00 - 02:00: reinicia → permite máx. 100 peticiones

IMPLEMENTACIÓN CONCEPTUAL:
  clave = cliente_id + ":" + timestamp_redondeado_al_minuto
  conteo_actual = incrementar(clave)
  si conteo_actual > LIMITE: rechazar
  establecer_expiracion(clave, 60_segundos)

VENTAJA: Simple de implementar. Bajo uso de memoria.
DESVENTAJA: Problema de burst en el borde de ventana.
  Un cliente puede hacer 100 req a las 00:59 y 100 req a las 01:00
  → 200 req en 2 segundos, cumpliendo el límite técnicamente.

IDEAL PARA: Límites de cuota por hora/día donde el burst no es crítico.
```

### Sliding Window Log (Ventana Deslizante con Log)

```
CONCEPTO:
  Guarda el timestamp de cada petición en una lista.
  Al llegar una nueva petición, elimina los timestamps fuera de la ventana.
  Cuenta los timestamps restantes vs el límite.

IMPLEMENTACIÓN CONCEPTUAL:
  ahora = timestamp_actual()
  ventana_inicio = ahora - 60_segundos

  registros = obtener_timestamps(cliente_id)
  registros = filtrar(registros, donde timestamp >= ventana_inicio)
  guardar(cliente_id, registros)

  si len(registros) >= LIMITE: rechazar
  guardar_timestamp(cliente_id, ahora)

VENTAJA: Precisión exacta. No hay burst en los bordes.
DESVENTAJA: Alto uso de memoria (guarda cada timestamp).
            Para 1M clientes × 100 req/min = 100M registros.

IDEAL PARA: Sistemas de alta precisión donde el burst entre ventanas es inaceptable.
```

### Sliding Window Counter (Ventana Deslizante con Contador)

```
CONCEPTO:
  Combina Fixed Window y Sliding Window Log.
  Mantiene el contador de la ventana actual y la anterior.
  Estima el conteo en la ventana deslizante mediante interpolación.

CÁLCULO:
  peso_ventana_anterior = (60 - segundos_transcurridos_en_ventana_actual) / 60
  estimacion = contador_ventana_anterior * peso_ventana_anterior + contador_ventana_actual

VENTAJA: Precisión razonable. Muy bajo uso de memoria (solo 2 contadores).
DESVENTAJA: Es una aproximación, no exacto.
IDEAL PARA: Producción — mejor balance entre precisión, rendimiento y memoria.
```

### Token Bucket (Cubeta de Tokens)

```
CONCEPTO:
  Una "cubeta" contiene tokens.
  Los tokens se reponen a una tasa constante (ej: 10 tokens/segundo).
  Cada petición consume 1 token.
  Si no hay tokens → petición rechazada.
  La cubeta tiene capacidad máxima (burst máximo).

PARÁMETROS:
  capacidad = 100  (máximo de tokens acumulables → burst máximo)
  tasa_recarga = 10 tokens/segundo

IMPLEMENTACIÓN CONCEPTUAL:
  tokens_actuales = leer(cliente_id)
  tiempo_desde_ultima_peticion = ahora - ultima_actualizacion(cliente_id)
  tokens_recargados = tiempo_desde_ultima_peticion * TASA_RECARGA
  tokens_disponibles = min(tokens_actuales + tokens_recargados, CAPACIDAD)

  si tokens_disponibles < 1: rechazar (429)
  guardar(cliente_id, tokens_disponibles - 1)

VENTAJA: Permite bursts controlados (acumulación de tokens en períodos de inactividad).
         Más natural para el usuario — puede enviar ráfagas ocasionales.
DESVENTAJA: Más complejo de implementar correctamente.
IDEAL PARA: APIs donde se quiere permitir bursts razonables (upload de archivos, batch ops).
```

### Leaky Bucket (Cubeta con Fuga)

```
CONCEPTO:
  Las peticiones entran a una cola a cualquier velocidad.
  Se procesan a una velocidad constante (la "fuga").
  Si la cola está llena → petición descartada.

VENTAJA: Salida perfectamente uniforme — protege el backend de cualquier burst.
DESVENTAJA: Agrega latencia (las peticiones esperan en cola).
IDEAL PARA: Proteger servicios downstream con capacidad muy fija (legados, terceros).
```

---

## Dimensiones de Identificación del Cliente

El rate limiting puede aplicarse a diferentes niveles, combinables:

|Dimensión|Descripción|Caso de uso|
|---|---|---|
|**IP Address**|Por dirección IP del cliente|APIs públicas sin autenticación, prevención DDoS|
|**User ID**|Por usuario autenticado|APIs con auth, limitar por cuenta|
|**API Key**|Por clave de API del cliente|APIs B2B, planes de suscripción|
|**Endpoint**|Límites distintos por ruta|`/pagos` más restrictivo que `/usuarios`|
|**Tenant / Organización**|Por cuenta/empresa|SaaS multi-tenant|
|**Global**|Límite total del sistema|Protección máxima del servidor|

**Estrategia combinada recomendada:**

```
Límite global del sistema:   10,000 req/seg
Límite por IP:               100 req/min
Límite por usuario auth:     500 req/min
Límite por endpoint crítico: 10 req/min (ej: /login, /pagos)
```

---

## Headers de Respuesta — Comunicación al Cliente

Los headers informan al cliente sobre su estado de rate limiting. Son obligatorios para una buena experiencia de desarrollador.

```
Headers estándar (RateLimit header fields — RFC 6585 / draft IETF):

X-RateLimit-Limit: 100
  El límite máximo de peticiones permitidas en la ventana actual.

X-RateLimit-Remaining: 23
  Peticiones restantes disponibles en la ventana actual.

X-RateLimit-Reset: 1715606400
  Timestamp Unix cuando el contador se reinicia / se recarga.
  El cliente puede calcular cuánto tiempo esperar.

Retry-After: 12
  (Presente solo en respuestas 429)
  Segundos que el cliente debe esperar antes de reintentar.
  También puede ser una fecha HTTP: Retry-After: Wed, 21 Oct 2025 07:28:00 GMT

RateLimit-Policy: "100;w=60"
  (Header emergente IETF) Describe la política: 100 peticiones por 60 segundos.
```

### Respuesta 429 completa

```
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1715606412
Retry-After: 12

{
  "error": "RATE_LIMIT_EXCEEDED",
  "message": "Has excedido el límite de 100 peticiones por minuto.",
  "retry_after_seconds": 12,
  "reset_at": "2025-05-13T10:00:12Z",
  "documentation": "https://docs.miapi.com/rate-limiting"
}
```

---

## Límites por Tipo de Operación

No todos los endpoints deben tener el mismo límite. Calibrar según el costo de la operación:

```
ENDPOINTS DE LECTURA SIMPLE (bajo costo):
  GET /usuarios          → 1,000 req/min por usuario
  GET /productos         → 2,000 req/min por usuario

ENDPOINTS DE ESCRITURA (costo medio):
  POST /comentarios      → 60 req/min por usuario
  PUT /perfil            → 30 req/min por usuario

ENDPOINTS COSTOSOS (alta carga):
  POST /exportar-reporte → 5 req/min por usuario
  POST /enviar-email     → 20 req/hora por usuario
  GET /busqueda-compleja → 30 req/min por usuario

ENDPOINTS CRÍTICOS DE SEGURIDAD (muy restrictivos):
  POST /login            → 5 req/min por IP, 20 req/hora total
  POST /recuperar-password → 3 req/hora por email
  POST /verificar-otp    → 5 intentos por token
  POST /pagos            → 10 req/min por usuario
```

---

## Almacén para Rate Limiting

El rate limiting requiere un almacén de acceso ultra-rápido y compartido entre todas las instancias:

|Almacén|Latencia|Compartido|TTL nativo|Recomendación|
|---|---|---|---|---|
|**Redis**|~0.1ms|✅|✅|✅ **Recomendado para producción**|
|**Memcached**|~0.1ms|✅|✅|✅ Alternativa válida|
|**Memoria del proceso**|~0.001ms|❌|Manual|❌ Solo desarrollo — no compartido entre instancias|
|**Base de datos SQL**|~5ms|✅|Manual|❌ Muy lento para rate limiting|

### Operaciones Redis para Rate Limiting

```
Fixed Window con Redis:
  INCR   cliente:ventana        → incrementa contador
  EXPIRE cliente:ventana 60     → TTL de 60 segundos

Token Bucket con Redis:
  Usar scripts Lua para operaciones atómicas:
  (leer tokens + calcular recarga + verificar + decrementar) en una sola transacción

OPERACIÓN ATÓMICA (crítico):
  Las operaciones de verificar + incrementar deben ser atómicas.
  Si no son atómicas: condición de carrera → clientes pueden exceder el límite.
  Redis + Lua scripts o transacciones garantizan atomicidad.
```

---

## Rate Limiting en Contexto de Microservicios

```
DÓNDE APLICAR RATE LIMITING EN LA ARQUITECTURA:

1. API GATEWAY (capa de entrada — recomendado)
   Centraliza el rate limiting para todos los servicios.
   Los servicios backend no necesitan implementarlo individualmente.
   Herramientas: Kong, AWS API Gateway, Nginx, Traefik.

2. CADA MICROSERVICIO (defensa en profundidad)
   Protección adicional si el Gateway falla o es bypasseado.
   Puede tener límites distintos según la capacidad del servicio.

3. ENTRE SERVICIOS (service-to-service)
   Previene que un servicio saturado cause efecto cascada.
   Circuit breaker + rate limiting = resiliencia.

RATE LIMITING DISTRIBUIDO:
  Con múltiples instancias del API Gateway:
  El almacén (Redis) debe ser compartido entre todas las instancias.
  Cada instancia consulta el mismo Redis para un conteo global consistente.
```

---

## Estrategias para el Cliente

Cuando el cliente recibe 429, debe seguir estas prácticas:

```
1. RESPETAR Retry-After
   No reintentar antes de que pase el tiempo indicado.
   El reintentar inmediatamente empeora la situación.

2. BACKOFF EXPONENCIAL con Jitter
   Si no hay Retry-After:
   espera = min(2^intento * base_ms + jitter_aleatorio, max_espera_ms)
   Intento 1: 1s + jitter
   Intento 2: 2s + jitter
   Intento 3: 4s + jitter
   Intento 4: 8s + jitter

3. MONITOREAR headers preventivamente
   Si X-RateLimit-Remaining es bajo → ralentizar voluntariamente antes de llegar a 0.
   Spread requests: en vez de 100 req en 1 segundo, distribuir en 60 segundos.

4. CIRCUIT BREAKER
   Si se reciben N respuestas 429 consecutivas → abrir el circuit breaker.
   Detener todas las peticiones por un tiempo para no empeorar la situación.
```

---

## Buenas Prácticas

### ✅ Siempre

```
1. INCLUIR headers de rate limit en TODAS las respuestas (no solo en 429).
   El cliente necesita saber su estado antes de llegar al límite.

2. RETORNAR Retry-After en respuestas 429.
   El cliente debe saber exactamente cuándo puede reintentar.

3. DEFINIR LÍMITES DISTINTOS por tipo de endpoint.
   Un login tiene restricciones diferentes a un listado de productos.

4. USAR ALMACÉN COMPARTIDO (Redis) entre todas las instancias.
   Límite por instancia ≠ límite global.

5. OPERAR ATÓMICAMENTE: verificar + incrementar en una sola operación.

6. DOCUMENTAR los límites en la referencia de la API.
   Los desarrolladores necesitan saber qué esperar.

7. APLICAR LÍMITES MÁS ESTRICTOS a endpoints de autenticación.
   Prevención de fuerza bruta.

8. MONITOREAR y AJUSTAR los límites según métricas reales de uso.
```

### ❌ Nunca

```
1. Omitir headers de rate limit — deja al cliente a ciegas.
2. Retornar 503 en vez de 429 — son semánticas distintas.
3. Baneo permanente por exceder rate limit — es temporal, no un bloqueo de seguridad.
4. Mismo límite para todos los endpoints — desperdicia recursos o es muy restrictivo.
5. Rate limiting solo en memoria del proceso — inconsistente con múltiples instancias.
6. Omitir documentación de los límites — pésima experiencia de desarrollador.
```

---

## Checklist de Implementación

### Diseño

- [ ] Algoritmo seleccionado y justificado (Fixed Window / Sliding / Token Bucket)
- [ ] Límites definidos por endpoint y por tipo de cliente
- [ ] Dimensiones de identificación definidas (IP / user_id / API key)
- [ ] Almacén seleccionado (Redis recomendado)
- [ ] Política de límites documentada en la referencia de la API

### Implementación

- [ ] Operaciones de verificar + incrementar son atómicas
- [ ] Headers `X-RateLimit-*` incluidos en todas las respuestas
- [ ] Header `Retry-After` incluido en respuestas 429
- [ ] Body de respuesta 429 con mensaje claro y documentación
- [ ] Aplicado en API Gateway o middleware central

### Seguridad

- [ ] Endpoints de login/auth con límites más estrictivos
- [ ] Protección contra DDoS por IP
- [ ] Rate limiting por tenant/usuario autenticado (no solo por IP)

### Observabilidad

- [ ] Métricas: peticiones bloqueadas por período, por cliente, por endpoint
- [ ] Alertas si un cliente excede el límite repetidamente (posible abuso)
- [ ] Logs de peticiones bloqueadas con identificador del cliente

---

> **RATE LIMITING = Protección + Control + Rendimiento + Seguridad + Escalabilidad**  
> Un buen rate limiting protege tu sistema sin molestar a los usuarios legítimos.