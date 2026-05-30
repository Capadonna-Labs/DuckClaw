# SPEC — Load Balancer

> Versión: 1.0.0 | Tipo: Infraestructura / Alta Disponibilidad  
> Aplica a: Cualquier sistema distribuido con múltiples instancias

---

## Definición

Un **Load Balancer (balanceador de carga)** es un componente de infraestructura que distribuye el tráfico de red entrante entre múltiples servidores backend, garantizando disponibilidad, rendimiento y escalabilidad.

```
SIN LOAD BALANCER:
  Todo el tráfico → Servidor único
  Fallo del servidor = Aplicación caída
  Pico de tráfico   = Servidor saturado

CON LOAD BALANCER:
  Todo el tráfico → Load Balancer → Servidor 1
                                  → Servidor 2
                                  → Servidor N
  Fallo de un servidor = Tráfico redirigido automáticamente a los demás
  Pico de tráfico      = Distribuido entre todas las instancias
```

**Principio fundamental**: el Load Balancer actúa como punto de entrada único (IP virtual / VIP) y es transparente para el usuario final.

---

## Flujo de una Petición

```
1. USUARIO
   El usuario hace una petición a tuapp.com

2. DNS / IP VIRTUAL
   DNS resuelve tuapp.com → 203.0.113.10 (IP del Load Balancer)

3. LOAD BALANCER RECIBE
   El LB recibe la petición HTTPS y decide a qué servidor enviarla
   según el algoritmo de balanceo configurado.

4. SERVIDOR BACKEND
   La petición se envía al servidor seleccionado.
   El servidor procesa y genera la respuesta.

5. RESPUESTA
   El servidor envía la respuesta al Load Balancer.

6. ENTREGA AL USUARIO
   El LB retorna la respuesta al usuario de forma transparente.
   El usuario nunca sabe qué servidor procesó su petición.

Todo el proceso ocurre en milisegundos.
```

---

## Algoritmos de Balanceo

### Round Robin

```
Descripción: Distribuye peticiones en orden secuencial cíclico.
  Petición 1 → Servidor A
  Petición 2 → Servidor B
  Petición 3 → Servidor C
  Petición 4 → Servidor A  (vuelve al inicio)

Ideal para: Servidores con capacidad homogénea y peticiones de duración similar.
Limitación: No considera carga real ni tiempo de respuesta de cada servidor.
```

### Weighted Round Robin

```
Descripción: Igual que Round Robin pero cada servidor tiene un peso.
  Servidor A (peso 3) → recibe 3 de cada 5 peticiones
  Servidor B (peso 2) → recibe 2 de cada 5 peticiones

Ideal para: Servidores con capacidades heterogéneas (distintas specs de hardware).
Configuración: Ajustar pesos según capacidad de CPU, RAM o benchmarks.
```

### Least Connections

```
Descripción: Envía la petición al servidor con MENOS conexiones activas en ese momento.
  Servidor A: 150 conexiones activas
  Servidor B: 42 conexiones activas  ← recibe la nueva petición
  Servidor C: 98 conexiones activas

Ideal para: Peticiones de larga duración (WebSockets, uploads, streaming).
Ventaja: Considera carga real, no solo turno.
```

### Least Response Time

```
Descripción: Envía al servidor con menor tiempo de respuesta promedio reciente.
Combina: Mínimas conexiones + menor latencia.

Ideal para: Cuando el rendimiento de los servidores varía dinámicamente.
Requiere: Que el LB mida y mantenga métricas de latencia por servidor.
```

### IP Hash (Sticky Sessions por IP)

```
Descripción: La IP del cliente se usa para calcular un hash que determina
siempre el mismo servidor destino.
  hash(IP cliente) % N servidores = índice del servidor

Ideal para: Aplicaciones con estado en servidor (sesiones en memoria local).
Limitación: Si un servidor cae, todos sus usuarios pierden sesión.
            No balancea bien si muchos usuarios comparten IP (NAT corporativo).
Alternativa preferida: Externalizar el estado a Redis y usar Round Robin.
```

### Random

```
Descripción: Selección aleatoria del servidor destino.
Uso: Sistemas muy grandes donde la aleatoriedad estadística garantiza distribución uniforme.
```

---

## Tipos de Load Balancer

### Por capa OSI

```
CAPA 4 — Transport Layer (TCP/UDP)
  Opera sobre IP y puerto. No inspecciona el contenido HTTP.
  Más rápido (menos procesamiento).
  No puede hacer routing basado en URL o headers.
  Uso: balanceo de bases de datos, servicios TCP genéricos.

CAPA 7 — Application Layer (HTTP/HTTPS)
  Inspecciona el contenido: URL, headers, cookies, body.
  Puede hacer routing inteligente:
    /api/*      → Servidores de API
    /static/*   → Servidores de archivos estáticos
    /admin/*    → Instancias de administración
  Puede terminar TLS (SSL termination).
  Puede modificar headers, redirigir, comprimir.
  Uso: aplicaciones web, APIs REST, microservicios.
  Ejemplos: NGINX, HAProxy, AWS ALB, Cloudflare.
```

### Por modo de despliegue

|Tipo|Descripción|Ejemplos|
|---|---|---|
|**Hardware**|Dispositivo físico dedicado. Máximo rendimiento, alto costo.|F5 BIG-IP, Citrix ADC|
|**Software**|Instalado en servidores estándar. Flexible y económico.|NGINX, HAProxy, Traefik|
|**Cloud / Managed**|Gestionado por el proveedor cloud. Sin mantenimiento.|AWS ELB/ALB/NLB, GCP Load Balancing, Azure LB|
|**DNS Load Balancing**|El DNS retorna múltiples IPs en rotación. Simple, sin infraestructura adicional.|Route 53, Cloudflare DNS|

---

## Health Checks

El Load Balancer debe verificar continuamente que los servidores backend están sanos antes de enviarles tráfico.

### Tipos de Health Check

```
PASSIVE (pasivo)
  El LB observa las respuestas reales del tráfico.
  Si N peticiones consecutivas fallan → marcar servidor como unhealthy.
  Ventaja: sin overhead adicional.
  Desventaja: el fallo se detecta cuando ya hay peticiones fallando.

ACTIVE (activo) — RECOMENDADO
  El LB envía peticiones de prueba periódicas al servidor.
  Independiente del tráfico real.
  Tipos:
    TCP Check:  Intenta abrir conexión TCP. Verifica que el puerto responde.
    HTTP Check: Hace GET a /health. Verifica que retorna 2xx.
    HTTPS Check: Igual que HTTP pero con TLS.
```

### Endpoint de Health Check

```
GET /health

Respuesta esperada: 200 OK
Tiempo máximo de respuesta: < 1 segundo
Body recomendado:
{
  "status":    "healthy",
  "timestamp": "2025-01-15T10:00:00Z",
  "version":   "1.4.2",
  "checks": {
    "database":   "ok",
    "cache":      "ok",
    "disk_space": "ok"
  }
}

Estados de servidor desde perspectiva del LB:
  HEALTHY   → recibe tráfico normal
  DEGRADED  → recibe tráfico reducido (si LB soporta weighted drain)
  UNHEALTHY → no recibe tráfico, LB redirige todo a los demás
  DRAINING  → no recibe peticiones nuevas, termina las activas (graceful shutdown)
```

### Parámetros de Health Check

```
Intervalo de chequeo:      cada 10–30 segundos
Timeout por chequeo:       2–5 segundos
Umbral para unhealthy:     2–3 fallos consecutivos
Umbral para recovery:      2–3 éxitos consecutivos antes de recibir tráfico
```

---

## SSL/TLS Termination

El Load Balancer puede gestionar el cifrado TLS, liberando a los servidores backend de esta carga.

```
MODO: SSL TERMINATION (recomendado)
  Cliente ←→ [HTTPS/TLS] ←→ Load Balancer ←→ [HTTP] ←→ Servidores backend
  
  Ventajas:
  - Certificados gestionados en un solo lugar (el LB)
  - Los servidores backend no necesitan gestionar TLS
  - El LB puede inspeccionar el contenido (Capa 7)
  - Menor carga de CPU en los backends

  Consideración de seguridad:
  - El tráfico interno (LB → backends) va en HTTP (no cifrado)
  - Solo seguro si la red interna es de confianza (VPC / red privada)
  - En redes no confiables: usar SSL passthrough o re-encryption

MODO: SSL PASSTHROUGH
  Cliente ←→ [HTTPS/TLS] ←→ Load Balancer ←→ [HTTPS/TLS] ←→ Servidores backend
  El LB reenvía el tráfico cifrado sin descifrarlo.
  Opera en Capa 4. No puede inspeccionar contenido.
  Uso: cuando el backend debe ver el certificado del cliente (mutual TLS).

MODO: SSL RE-ENCRYPTION
  Cliente ←→ [HTTPS] ←→ LB (descifra y re-cifra) ←→ [HTTPS] ←→ Backends
  Máxima seguridad end-to-end.
  Mayor overhead de CPU.
```

---

## Sticky Sessions (Afinidad de Sesión)

En algunos sistemas, el mismo usuario debe ir siempre al mismo servidor (estado local de sesión).

```
MECANISMO DE STICKY SESSIONS:
  El LB asigna una cookie (o usa IP hash) para identificar
  qué servidor debe atender a cada usuario.

  Set-Cookie: SERVERID=srv-02; Path=/; HttpOnly

  Petición siguiente del usuario → LB lee SERVERID → envía a srv-02.

PROBLEMA:
  Si srv-02 falla, el usuario pierde su sesión.
  Si se agrega un servidor nuevo, los usuarios existentes no se redistribuyen.
  Genera desbalanceo cuando algunos usuarios son más activos.

ALTERNATIVA RECOMENDADA:
  Externalizar el estado de sesión a un store compartido (Redis, Memcached).
  Cualquier servidor puede atender cualquier petición.
  El LB puede usar Round Robin puro → distribución óptima.
  Sesión no se pierde si un servidor falla.
```

---

## Arquitectura de Alta Disponibilidad

### Load Balancer como Single Point of Failure

El LB en sí mismo puede fallar. Soluciones:

```
ACTIVE / PASSIVE (Failover)
  LB Primario: recibe todo el tráfico (ACTIVE)
  LB Secundario: en espera, monitorea al primario (PASSIVE)
  Si el primario falla → IP virtual migra al secundario automáticamente (VRRP/Keepalived)
  Tiempo de failover: ~1–3 segundos

ACTIVE / ACTIVE
  Ambos LBs reciben tráfico simultáneamente.
  DNS retorna las IPs de ambos en rotación.
  Si uno falla → DNS deja de incluirlo.
  Mayor throughput + redundancia.
  Más complejo de configurar.

CLOUD MANAGED
  El proveedor cloud gestiona la alta disponibilidad del LB.
  Sin configuración adicional de HA para el LB.
  AWS ELB, GCP LB, Azure LB son inherentemente redundantes.
```

---

## Patrones de Arquitectura con Load Balancer

### Global Load Balancing (Multi-región)

```
Usuario en Europa    → DNS → LB Europa  → Servidores en Frankfurt
Usuario en América   → DNS → LB US-East → Servidores en Virginia
Usuario en Asia      → DNS → LB Asia    → Servidores en Tokio

Beneficios:
  - Menor latencia (usuario va al datacenter más cercano)
  - Resistencia a fallos de región completa
  - Cumplimiento de regulaciones de datos (datos en región específica)

Tecnologías: Cloudflare, AWS Route 53 + latency routing, GCP Global LB
```

### Load Balancer en Microservicios

```
EXTERNAL LOAD BALANCER (North-South)
  Internet → LB Externo → API Gateway → Microservicios

INTERNAL LOAD BALANCER (East-West)
  Servicio A → LB Interno → Servicio B (múltiples instancias)
  Implementado como: Service Mesh (Istio, Linkerd), sidecar proxy

SERVICE DISCOVERY + LB DINÁMICO
  Los servicios se registran al arrancar (Consul, Kubernetes DNS).
  El LB descubre automáticamente nuevas instancias.
  No requiere configuración manual al escalar.
```

---

## Métricas Clave a Monitorear

|Métrica|Descripción|Umbral de Alerta|
|---|---|---|
|**Requests per Second (RPS)**|Tráfico total procesado por el LB|Según capacidad planificada|
|**Active Connections**|Conexiones abiertas simultáneas|> 80% del límite configurado|
|**Backend Response Time**|Latencia de los servidores backend|p99 > 1 segundo|
|**Error Rate (5xx)**|Porcentaje de respuestas de error|> 1%|
|**Healthy Backends**|Servidores marcados como healthy|< 50% del total|
|**Connection Queue**|Peticiones en espera de servidor disponible|> 0 sostenido|
|**SSL Handshake Time**|Tiempo de negociación TLS|> 200ms promedio|

---

## Buenas Prácticas

### ✅ Siempre

```
1. Implementar health checks activos en /health con verificación de dependencias.
2. Externalizar el estado de sesión (Redis) — evitar sticky sessions por estado.
3. Configurar timeouts explícitos: connect timeout, read timeout, write timeout.
4. SSL/TLS termination en el LB con certificados auto-renovados (Let's Encrypt / ACM).
5. Monitorear distribución del tráfico entre backends — detectar desbalanceo.
6. Configurar graceful drain al escalar hacia abajo (Kubernetes: terminationGracePeriodSeconds).
7. Registrar IPs de origen reales: usar header X-Forwarded-For o X-Real-IP.
8. Alta disponibilidad del propio LB: active/passive o managed service.
```

### ❌ Nunca

```
1. Depender de sticky sessions por estado local — single point of failure por servidor.
2. Ignorar los health checks — el LB seguirá enviando tráfico a servidores caídos.
3. Exponer el LB en HTTP sin redirección a HTTPS.
4. Olvidar logs de acceso del LB — son esenciales para auditoría y debugging.
5. Usar un único LB sin redundancia en producción.
6. Configurar timeouts demasiado largos — una instancia lenta bloquea conexiones.
```

---

## Checklist de Implementación

### Configuración

- [ ] Algoritmo de balanceo seleccionado y justificado
- [ ] Health check activo configurado: endpoint, intervalo, umbral
- [ ] SSL/TLS termination configurado con certificado válido
- [ ] Redirección HTTP → HTTPS habilitada
- [ ] Timeouts definidos: connect, read, write, idle
- [ ] Header `X-Forwarded-For` propagado a los backends

### Alta Disponibilidad

- [ ] Load Balancer con redundancia (active/passive o managed)
- [ ] Mínimo 2 instancias backend en zonas de disponibilidad distintas
- [ ] Estado de sesión externalizado (Redis/DB compartida)
- [ ] Graceful drain configurado para deploys sin downtime

### Observabilidad

- [ ] Logs de acceso del LB habilitados y centralizados
- [ ] Métricas exportadas: RPS, error rate, latencia, backends healthy
- [ ] Alertas configuradas para backends unhealthy y error rate elevado
- [ ] Dashboard de distribución de tráfico entre instancias

---

> **LOAD BALANCER = Distribución + Rendimiento + Disponibilidad + Escalabilidad**  
> Un buen LB es invisible para el usuario y garantiza que la aplicación nunca tenga un único punto de fallo.