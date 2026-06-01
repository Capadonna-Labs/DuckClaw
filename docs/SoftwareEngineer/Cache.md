# SPEC — Caché

> Versión: 1.0.0 | Tipo: Arquitectura Transversal | Aplica a: Cualquier stack tecnológico

---

## Definición

El **caché** es una capa de almacenamiento temporal que guarda resultados de operaciones costosas (consultas a base de datos, llamadas a APIs externas, cómputo intensivo) para reutilizarlos en peticiones posteriores sin regenerarlos.

```
SIN CACHÉ:  Cada petición → Origen (DB / API / Cómputo) → Respuesta
CON CACHÉ:  Petición → Caché HIT → Respuesta inmediata
            Petición → Caché MISS → Origen → Guardar en caché → Respuesta
```

**Objetivo**: reducir latencia, disminuir carga en el origen y aumentar la escalabilidad del sistema.

---

## Taxonomía de Caché

### Por ubicación

|Tipo|Descripción|Ejemplos|
|---|---|---|
|**Browser Cache**|El navegador almacena recursos estáticos en el dispositivo del usuario|HTML, CSS, JS, imágenes|
|**Application Cache**|Caché implementado dentro del código de la aplicación|Variables en memoria, diccionarios en proceso|
|**Server-Side Cache**|Almacén externo compartido entre múltiples instancias|Redis, Memcached|
|**CDN / Proxy Cache**|Caché en la red de distribución, cerca del usuario geográficamente|Cloudflare, Varnish, Fastly|
|**Database Cache**|Caché interno del motor de base de datos|Query cache, buffer pool|

### Por estrategia de escritura

|Estrategia|Descripción|Trade-off|
|---|---|---|
|**Cache-Aside (Lazy Loading)**|La app consulta caché; si MISS, obtiene del origen y guarda|Simple, datos solo cuando se necesitan; primera petición lenta|
|**Write-Through**|Escribe en caché y en origen simultáneamente|Consistencia alta; mayor latencia en escritura|
|**Write-Behind (Write-Back)**|Escribe primero en caché, luego asíncronamente en origen|Escritura rápida; riesgo de pérdida de datos|
|**Read-Through**|El caché obtiene del origen automáticamente en MISS|Transparente para la app; requiere librería/middleware|
|**Refresh-Ahead**|Pre-carga datos antes de que expiren|Sin MISS; puede calentar datos innecesarios|

---

## Flujo de Decisión (Cache-Aside)

```
┌─────────────────────────────────────────────────────┐
│                  PETICIÓN ENTRANTE                  │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
               ┌─────────────────┐
               │  Buscar en caché │
               └────────┬────────┘
                        │
              ┌─────────┴──────────┐
              │                    │
           HIT ✓                MISS ✗
              │                    │
              ▼                    ▼
     Retornar dato          Consultar ORIGEN
     del caché              (DB / API / Cómputo)
                                   │
                                   ▼
                           Guardar en caché
                           con TTL definido
                                   │
                                   ▼
                           Retornar dato
```

---

## Conceptos Fundamentales

### TTL (Time To Live)

El **TTL** define cuánto tiempo (en segundos) un dato permanece válido en caché antes de considerarse expirado (stale).

```
TTL muy bajo  → Muchos MISS → Alta carga en origen → Caché poco efectivo
TTL muy alto  → Datos desactualizados → Inconsistencia
TTL adecuado  → Balanceo entre frescura y rendimiento
```

**Guía de TTL por tipo de dato:**

|Tipo de Dato|TTL Recomendado|Justificación|
|---|---|---|
|Configuración de sistema|1 hora – 24 horas|Cambia raramente|
|Listado de catálogo (productos)|5 – 30 minutos|Actualización moderada|
|Perfil de usuario|5 – 15 minutos|Puede cambiar durante sesión|
|Resultados de búsqueda|1 – 5 minutos|Alta variabilidad|
|Precios / Stock en tiempo real|30 – 60 segundos|Alta volatilidad|
|Datos de sesión activa|Duración de sesión|Ligado al tiempo de vida del usuario|
|Datos críticos financieros|0 (no cachear)|Consistencia obligatoria|

### Cache Key Design

La **clave** identifica unívocamente un dato en caché. Una mala clave provoca colisiones (datos incorrectos) o fragmentación excesiva (caché ineficiente).

**Estructura recomendada:**

```
{namespace}:{entidad}:{identificador}:{versión_opcional}
```

**Ejemplos:**

```
usuarios:perfil:123
productos:detalle:SKU-456
busqueda:resultados:categoria=electronica&pagina=2
api:clima:ciudad=madrid:v2
```

**Reglas:**

- Usar separadores consistentes (`:` o `_`)
- Incluir parámetros que afecten el resultado
- Evitar datos sensibles en la clave (emails, tokens)
- Mantener longitud razonable (< 200 caracteres)
- Versionar cuando el schema del dato cambia (`v1`, `v2`)

### Invalidación de Caché

> "There are only two hard things in Computer Science: cache invalidation and naming things." — Phil Karlton

**Estrategias de invalidación:**

```
1. EXPIRACIÓN POR TTL
   Automática. El dato expira tras N segundos.
   Simple pero puede dejar datos stale hasta que expiren.

2. INVALIDACIÓN ACTIVA (Event-Driven)
   Al modificar un dato en el origen → eliminar/actualizar la clave en caché.
   Consistencia inmediata. Requiere coordinación entre escritura y caché.

3. CACHE BUSTING (versioning)
   Cambiar la clave al actualizar el dato.
   Usado principalmente en assets estáticos (CSS/JS): archivo.v2.css
   El dato viejo expira solo por TTL, el nuevo se accede por clave nueva.

4. INVALIDACIÓN POR TAGS / GRUPOS
   Asociar claves con tags y eliminar todas las claves de un tag.
   Ejemplo: todas las claves del tag "usuario:123" al actualizar el usuario.
```

---

## Headers HTTP de Caché (Browser/CDN)

El caché del navegador y de proxies/CDN se controla mediante headers HTTP estándar.

### Headers de Respuesta (Servidor → Cliente)

```
Cache-Control: max-age=3600, public
│              │             │
│              │             └── public: cualquier caché puede almacenarlo
│              │                 private: solo caché del navegador (no CDN)
│              └── max-age en segundos antes de que expire
└── Directiva principal de control de caché

Expires: Wed, 21 Oct 2025 07:28:00 GMT
└── Fecha absoluta de expiración (menos preciso que max-age)

ETag: "a1b2c3d4"
└── Identificador único de la versión del recurso (hash del contenido)

Last-Modified: Tue, 15 Oct 2024 12:00:00 GMT
└── Fecha de última modificación del recurso
```

### Directivas Cache-Control comunes

|Directiva|Efecto|
|---|---|
|`no-store`|No cachear bajo ninguna circunstancia|
|`no-cache`|Cachear pero revalidar antes de usar|
|`private`|Solo caché del navegador, no CDN/proxy|
|`public`|Cualquier caché puede almacenarlo|
|`max-age=N`|Válido por N segundos|
|`s-maxage=N`|Válido por N segundos solo en cachés compartidos (CDN)|
|`must-revalidate`|Revalidar cuando expira, no usar stale|
|`immutable`|El recurso nunca cambia; no revalidar (ideal para assets con hash)|

### Flujo de Revalidación (ETag / 304)

```
1ra petición:
  Cliente → GET /recurso
  Servidor → 200 OK + ETag: "abc123" + datos

2da petición (recurso expirado):
  Cliente → GET /recurso + If-None-Match: "abc123"
  Servidor → (si no cambió) 304 Not Modified  ← sin body, más rápido
  Servidor → (si cambió)    200 OK + ETag: "def456" + datos nuevos
```

---

## Políticas de Evicción

Cuando el caché está lleno y llega un dato nuevo, debe elegir qué eliminar:

|Política|Descripción|Uso típico|
|---|---|---|
|**LRU** (Least Recently Used)|Elimina el dato usado hace más tiempo|Redis default — uso general|
|**LFU** (Least Frequently Used)|Elimina el dato usado con menor frecuencia|Cuando popularidad importa más que recencia|
|**FIFO** (First In, First Out)|Elimina el dato más antiguo independientemente del uso|Streams, logs|
|**TTL**|Elimina primero los datos más próximos a expirar|Complemento a LRU|
|**Random**|Elimina aleatoriamente|Simple, bajo overhead|

---

## Tipos de Caché en Servidor — Comparativa

|Característica|En Memoria (proceso)|Redis / Memcached|CDN|
|---|---|---|---|
|Latencia|~nanosegundos|~microsegundos|~milisegundos|
|Compartido entre instancias|❌ No|✅ Sí|✅ Sí|
|Persistencia|❌ Muere con el proceso|⚠️ Configurable|❌ No|
|Tamaño máximo|Limitado por RAM del proceso|Alta (GBs)|Altísima|
|Invalidación distribuida|❌ Imposible|✅ Nativa|Vía API|
|Ideal para|Datos de sesión local, lookups frecuentes|Datos compartidos, sesiones, rate limiting|Assets estáticos, respuestas de API públicas|

---

## Buenas Prácticas

### ✅ Hacer

```
1. DEFINIR TTL EXPLÍCITO en cada dato cacheado. Nunca TTL indefinido en producción.

2. USAR CLAVES ESPECÍFICAS Y PREDECIBLES.
   Incluir todos los parámetros que afecten el resultado.

3. INVALIDAR ACTIVAMENTE al modificar datos críticos.
   No esperar solo al TTL para datos que cambian con escrituras conocidas.

4. CACHEAR EN LA CAPA CORRECTA.
   Datos estáticos → CDN/Browser
   Datos de sesión → Server-side (Redis)
   Resultados de cómputo → Application cache

5. MONITOREAR métricas clave:
   - Hit Rate (objetivo: > 80%)
   - Miss Rate
   - Latencia de hits vs misses
   - Uso de memoria / evictions

6. USAR NAMESPACES para organizar y facilitar invalidación por grupo.

7. VERSIONAR CLAVES al cambiar el schema del dato cacheado.
```

### ❌ No hacer

```
1. NO CACHEAR datos sensibles sin cifrado (contraseñas, tokens, PII).

2. NO CACHEAR resultados de operaciones con efectos secundarios (POST, DELETE).

3. NO USAR TTL indefinido (sin expiración) salvo casos muy justificados.

4. NO IGNORAR el tamaño del valor cacheado. Valores muy grandes desperdician memoria.

5. NO ASUMIR que el caché siempre estará disponible.
   El código debe funcionar correctamente con caché caído (degradación elegante).

6. NO CACHEAR datos que cambian en cada petición (son únicos por usuario/contexto).

7. NO COMPARTIR CLAVES entre entornos (development / staging / production).
   Usar prefix de entorno: prod:usuarios:123, dev:usuarios:123
```

---

## Patrones Avanzados

### Thundering Herd / Cache Stampede

**Problema**: cuando una clave popular expira, muchas peticiones simultáneas van al origen al mismo tiempo.

**Soluciones:**

- **Mutex/Lock**: solo una petición regenera la clave; las demás esperan
- **Probabilistic Early Expiration**: renovar la clave proactivamente antes de que expire
- **Stale-While-Revalidate**: servir el dato expirado mientras se regenera en segundo plano

### Multi-Level Cache (Caché en Capas)

```
Petición
   │
   ▼
L1: Caché en memoria del proceso  (nanosegundos, local)
   │ MISS
   ▼
L2: Redis / Memcached             (microsegundos, compartido)
   │ MISS
   ▼
L3: Base de datos / API origen    (milisegundos, fuente de verdad)
```

---

## Checklist de Implementación

### Diseño

- [ ] Identificados los datos candidatos a caché (costosos, frecuentes, relativamente estables)
- [ ] TTL definido y justificado por tipo de dato
- [ ] Estrategia de clave documentada (formato y componentes)
- [ ] Estrategia de invalidación definida (TTL, activa, por tags)
- [ ] Política de evicción seleccionada según caso de uso

### Implementación

- [ ] Código funciona correctamente cuando el caché está caído (fallback al origen)
- [ ] No se cachean datos sensibles sin protección
- [ ] Claves incluyen prefijo de entorno (prod/staging/dev)
- [ ] Versión de schema en la clave (prevención de datos stale tras deploy)
- [ ] Headers HTTP de caché configurados para recursos estáticos

### Operacional

- [ ] Monitoreo de Hit Rate, Miss Rate, latencia y evictions
- [ ] Alertas si el Hit Rate cae por debajo del umbral esperado
- [ ] Proceso documentado para invalidación manual en emergencias
- [ ] Tamaño máximo del caché definido y configurado

---

> **CACHÉ = Velocidad + Eficiencia + Mejor Experiencia**  
> La clave del caché es saber qué cachear, cuánto tiempo y cuándo invalidar.