# SPEC — Event-Driven Architecture (EDA)

> Versión: 1.0.0 | Tipo: Patrón Arquitectónico  
> Aplica a: Sistemas distribuidos, microservicios y aplicaciones que requieren alta escalabilidad y desacoplamiento

---

## Definición

**Event-Driven Architecture (EDA)** es un paradigma arquitectónico donde los componentes del sistema se comunican mediante la producción, detección y reacción a **eventos**. Un evento es un hecho ocurrido en el sistema que puede ser relevante para otros componentes.

```
ARQUITECTURA TRADICIONAL (acoplada):
  Servicio A llama directamente a Servicio B:
    ServicioPedidos.confirmarPago() → llama → ServicioStock.descontarStock()
                                    → llama → ServicioEmail.enviarConfirmacion()
                                    → llama → ServicioFactura.generarFactura()

  Problema: A depende de B, C y D. Si cualquiera falla → A falla.

ARQUITECTURA EVENT-DRIVEN (desacoplada):
  Servicio A publica un evento:
    ServicioPedidos → publica → PedidoConfirmadoEvent

  Cada servicio reacciona de forma independiente:
    ServicioStock    → escucha → PedidoConfirmadoEvent → desconta stock
    ServicioEmail    → escucha → PedidoConfirmadoEvent → envía email
    ServicioFactura  → escucha → PedidoConfirmadoEvent → genera factura

  ServicioPedidos no sabe ni le importa quién escucha. Es libre.
```

**Principio fundamental**: los productores de eventos no conocen a sus consumidores. Los consumidores no conocen a sus productores. El broker de mensajes es el único punto de coordinación.

---

## Conceptos Fundamentales

### Evento

```
Un evento es:
  - Un HECHO que YA OCURRIÓ en el sistema (pasado, no futuro)
  - INMUTABLE: no puede modificarse una vez emitido
  - INFORMACIONAL: describe qué pasó, no qué debe hacerse
  - NOMBRADO en tiempo pasado: PedidoCreado, PagoConfirmado, UsuarioRegistrado

Evento vs Comando:
  EVENTO:   "PedidoCreado"   — algo YA ocurrió, yo te informo
  COMANDO:  "CrearPedido"    — algo que QUIERO que hagas

  Los eventos son hechos. Los comandos son intenciones.
  Los eventos no esperan respuesta. Los comandos sí.
```

### Productor (Producer)

```
El componente que detecta que algo relevante ocurrió y publica el evento.
  - No sabe quién consumirá el evento ni cuántos consumidores hay.
  - Solo necesita saber: en qué topic/canal publicar.
  - Publica y continúa su trabajo sin esperar.
  - Desacoplado totalmente de los consumidores.
```

### Broker de Mensajes / Event Bus

```
El intermediario que recibe eventos de los productores y los distribuye a los consumidores.
  - Desacopla productores de consumidores en tiempo, espacio y lógica.
  - Garantiza la entrega (at-least-once, exactly-once según configuración).
  - Preserva el orden dentro de una partición/canal.
  - Permite replay: los consumidores pueden releer eventos pasados.
  - Actúa como buffer: absorbe picos de carga.

Tecnologías:
  Apache Kafka     → Streaming de alta escala, replay, retención larga
  RabbitMQ         → Mensajería, colas con enrutamiento flexible
  AWS SNS + SQS    → Notificaciones + Colas en ecosistema AWS
  Google Pub/Sub   → Mensajería gestionada en GCP
  Azure Event Hubs → Streaming en Azure
  NATS             → Mensajería ligera y ultra-rápida
  Redis Streams    → Streaming en Redis (para escala media)
```

### Consumidor (Consumer)

```
El componente que está suscrito a eventos y reacciona cuando los recibe.
  - Procesa eventos de forma asíncrona e independiente.
  - No sabe quién produjo el evento.
  - Puede haber múltiples consumidores del mismo evento (fan-out).
  - Cada consumidor tiene su propio ritmo de procesamiento.
  - DEBE ser idempotente: el mismo evento puede llegar más de una vez.
```

---

## Flujo Completo de un Evento

```
EJEMPLO: Usuario realiza una compra en e-commerce

1. ALGO SUCEDE
   El usuario hace clic en "Confirmar pedido".
   ServicioPedidos crea el pedido en su base de datos.

2. SE PUBLICA EL EVENTO
   ServicioPedidos → publica → PedidoCreadoEvent
   {
     "id":           "evt_001",
     "tipo":         "pedido.creado",
     "timestamp":    "2024-05-18T12:30:00Z",
     "version":      "1.0",
     "productor":    "servicio-pedidos",
     "datos": {
       "pedido_id":  "PED-001",
       "cliente_id": "user_123",
       "total":      150.00,
       "items":      [{ "producto_id": "SKU-456", "cantidad": 2 }]
     }
   }

3. EL BROKER LO RECIBE Y LO ALMACENA
   El evento queda en el topic "pedidos" del broker.
   Disponible para todos los consumidores suscritos.

4. CONSUMIDORES LO RECIBEN Y REACCIONAN (en paralelo, de forma independiente)

   ServicioInventario:
     Recibe PedidoCreadoEvent
     Desconta 2 unidades de SKU-456 del stock
     Emite: StockActualizadoEvent (si quedó bajo mínimo: AlertaStockBajoEvent)

   ServicioPagos:
     Recibe PedidoCreadoEvent
     Inicia el proceso de cobro
     Emite: PagoIniciadoEvent → (luego) PagoConfirmadoEvent o PagoFallidoEvent

   ServicioNotificaciones:
     Recibe PedidoCreadoEvent
     Envía email de confirmación al cliente

   ServicioAnalytics:
     Recibe PedidoCreadoEvent
     Actualiza métricas en tiempo real

5. EL SISTEMA SIGUE
   ServicioPedidos no esperó ninguna respuesta.
   El usuario ya tiene su confirmación.
   Cada servicio trabaja a su ritmo, sin bloquear a los demás.
```

---

## Anatomía de un Evento — Schema Estándar

```json
{
  "id":           "550e8400-e29b-41d4-a716-446655440000",
  "tipo":         "pedido.creado",
  "version":      "1.0",
  "timestamp":    "2024-05-18T12:30:00.000Z",
  "productor":    "servicio-pedidos",
  "correlacion_id": "req_abc123",
  "causacion_id":   "cmd_xyz789",
  "datos": {
    "pedido_id":  "PED-001",
    "cliente_id": "user_123",
    "total":      150.00
  },
  "metadata": {
    "ambiente":   "production",
    "region":     "eu-west-1",
    "version_esquema": "pedido.creado/1.0"
  }
}
```

**Campos recomendados:**

|Campo|Descripción|Requerido|
|---|---|---|
|`id`|UUID único del evento — deduplicación|✅|
|`tipo`|Nombre descriptivo en pasado (dominio.hecho)|✅|
|`timestamp`|Cuándo ocurrió el hecho (ISO 8601 UTC)|✅|
|`version`|Versión del schema del evento|✅|
|`productor`|Servicio que emitió el evento|✅|
|`datos`|Payload del evento — el hecho ocurrido|✅|
|`correlacion_id`|ID de la request/operación original|Recomendado|
|`causacion_id`|ID del comando o evento que causó éste|Recomendado|
|`metadata`|Información de contexto técnico|Opcional|

---

## Patrones Comunes en EDA

### Publish / Subscribe (Pub/Sub)

```
CONCEPTO:
  Un productor publica en un topic/canal.
  Todos los consumidores suscritos al topic reciben una copia del evento.
  Fan-out: 1 evento → N consumidores.

IDEAL PARA: Notificaciones, broadcast de cambios de estado.

Productor: ServicioPedidos → topic: "pedidos.creados"
Consumidor A: ServicioEmail     ← recibe PedidoCreadoEvent
Consumidor B: ServicioStock     ← recibe PedidoCreadoEvent (misma copia)
Consumidor C: ServicioAnalytics ← recibe PedidoCreadoEvent (misma copia)
```

### Event Sourcing

```
CONCEPTO:
  El estado del sistema NO se guarda como el estado actual.
  Se guarda la SECUENCIA DE EVENTOS que llevaron al estado actual.
  El estado actual se reconstruye reproduciendo los eventos.

SIN EVENT SOURCING:
  tabla pedidos: { id: 1, estado: "enviado", total: 100 }
  (historia perdida: ¿cómo llegó a "enviado"?)

CON EVENT SOURCING:
  evento 1: PedidoCreadoEvent    { pedido_id: 1, total: 100 }
  evento 2: PagoConfirmadoEvent  { pedido_id: 1, monto: 100 }
  evento 3: PedidoEnviadoEvent   { pedido_id: 1, tracking: "TRK-001" }
  Estado actual = reproducir eventos 1 + 2 + 3

BENEFICIOS:
  Historial completo e inmutable de todo lo que ocurrió.
  Posibilidad de "viaje en el tiempo" — reconstruir estado en cualquier punto.
  Audit log gratuito.
  Permite projections: distintas vistas calculadas desde los mismos eventos.

DESAFÍOS:
  Consultas más complejas (necesita projections/snapshots).
  El modelo crece con el tiempo.
  Cambios en el schema de eventos requiere estrategia de migración.

COMPAÑERO NATURAL: CQRS.
  Event Sourcing = cómo se almacena el estado.
  CQRS = cómo se accede al estado.
```

### Saga Pattern (Transacciones distribuidas)

```
PROBLEMA:
  En sistemas distribuidos, no existe una transacción ACID que abarque múltiples servicios.

SOLUCIÓN — SAGA:
  Una secuencia de transacciones locales, coordinadas mediante eventos.
  Si un paso falla: ejecutar compensaciones para deshacer pasos anteriores.

EJEMPLO: Proceso de compra como Saga
  Paso 1: CrearPedidoCommand        → PedidoCreadoEvent
  Paso 2: ReservarStockCommand      → StockReservadoEvent
  Paso 3: ProcesarPagoCommand       → PagoConfirmadoEvent
  Paso 4: ConfirmarReservaCommand   → PedidoConfirmadoEvent

  Si Paso 3 falla (pago rechazado):
    Compensación 3: (nada, el pago no se hizo)
    Compensación 2: LiberarStockCommand  → StockLiberadoEvent
    Compensación 1: CancelarPedidoCommand → PedidoCanceladoEvent

  TIPOS DE SAGA:
    Coreografía: cada servicio reacciona a eventos y emite los suyos.
                 Sin coordinador central. Más desacoplado, más difícil de trazar.
    Orquestación: un Saga Orchestrator dirige el flujo explícitamente.
                  Más visible y controlable, introduce un coordinador central.
```

### Eventual Consistency

```
En EDA asíncrona, la consistencia entre servicios es EVENTUAL, no inmediata.

EJEMPLO:
  Tiempo 0ms:   ServicioPedidos actualiza estado → "confirmado"
  Tiempo 0ms:   Evento publicado al broker
  Tiempo 50ms:  ServicioEmail recibe el evento → envía email
  Tiempo 100ms: ServicioAnalytics recibe el evento → actualiza métricas

  Entre el tiempo 0ms y el 50ms: el email aún no se ha enviado.
  Esto es aceptable: el sistema es EVENTUALMENTE consistente.

IMPLICACIONES DE DISEÑO:
  Los consumidores deben tolerar que los datos lleguen con delay.
  La UI no debe asumir que todos los efectos son instantáneos.
  Diseñar para idempotencia: el mismo evento puede llegar más de una vez.
  Diseñar para orden: los eventos pueden llegar fuera de orden en casos excepcionales.
```

---

## Idempotencia en Consumidores

Los brokers garantizan at-least-once delivery: el mismo evento puede llegar más de una vez (reintento por falla del consumidor). Los consumidores DEBEN ser idempotentes.

```
PROBLEMA:
  PedidoCreadoEvent con id "evt_001" llega al ServicioEmail.
  Email se envía. Antes de hacer ACK al broker: el proceso falla.
  El broker reenvía "evt_001" → el email se envía de nuevo. ¡Duplicado!

SOLUCIÓN:
  Tabla: eventos_procesados { event_id, consumidor, procesado_en }

  Al recibir un evento:
  1. Buscar event_id en eventos_procesados para este consumidor
  2. Si YA existe: hacer ACK al broker y no procesar → evento duplicado
  3. Si NO existe: procesar el evento → guardar event_id → hacer ACK

  TRANSACCIÓN: guardar el evento en eventos_procesados + ejecutar la acción
  deben ser atómicos (o usar outbox pattern).
```

---

## Dead Letter Queue (DLQ)

```
¿Qué ocurre si un consumidor no puede procesar un evento después de N reintentos?

SIN DLQ:
  El evento fallido bloquea el procesamiento de los eventos siguientes.
  O se pierde definitivamente.

CON DLQ (Dead Letter Queue / Dead Letter Topic):
  Después de N reintentos fallidos → el evento se mueve a la DLQ.
  El sistema continúa procesando los siguientes eventos.
  El equipo puede inspeccionar la DLQ, corregir el error y reinyectar los eventos.

CONFIGURACIÓN RECOMENDADA:
  max_reintentos:       3–5 intentos
  backoff:              exponencial con jitter
  acción al agotar:     mover a DLQ + alerta al equipo
  retención en DLQ:     7–30 días (tiempo para diagnóstico y reinyección)

MONITOREO CRÍTICO:
  La DLQ debe monitorearse. Un evento en DLQ = algo roto en el sistema.
  Alertas automáticas cuando la DLQ tiene mensajes.
```

---

## Diseño de Topics / Canales

```
CONVENCIÓN DE NOMBRES RECOMENDADA:
  {dominio}.{entidad}.{evento}  →  pedidos.pedido.creado
  {servicio}.{entidad}.{accion} →  pagos.cobro.confirmado

GRANULARIDAD:
  Un topic por tipo de evento:
    pedidos.pedido.creado
    pedidos.pedido.cancelado
    pedidos.pedido.enviado
  Ventaja: consumidores suscriben solo a lo que les interesa.
  Desventaja: muchos topics para gestionar.

  Un topic por entidad (con tipo en el payload):
    pedidos.eventos  (contiene todos los eventos de pedidos)
  Ventaja: simplicidad en número de topics.
  Desventaja: consumidores reciben eventos que no les interesan y deben filtrar.

PARTICIONAMIENTO:
  Los eventos del mismo agregado (mismo pedido_id) deben ir a la misma partición.
  Garantiza orden de procesamiento para ese agregado.
  Clave de partición: pedido_id, usuario_id, etc.
```

---

## Observabilidad en EDA

La naturaleza asíncrona y distribuida de EDA requiere observabilidad especial:

```
TRAZABILIDAD DISTRIBUIDA (Distributed Tracing):
  Cada evento lleva un correlacion_id que se propaga a través de todos los servicios.
  Permite reconstruir el flujo completo: desde el request inicial hasta todos los efectos.

  Herramientas: Jaeger, Zipkin, AWS X-Ray, OpenTelemetry.

MÉTRICAS CLAVE:
  - Tasa de producción de eventos por topic (eventos/seg)
  - Lag de consumidores (diferencia entre el último evento producido y el último procesado)
  - Tasa de error en consumidores
  - Mensajes en DLQ (debe ser 0 en condiciones normales)
  - Latencia end-to-end: desde que ocurre el hecho hasta que todos los consumidores reaccionan

ALERTAS CRÍTICAS:
  - Lag de consumidor creciendo sostenidamente → consumidor lento o caído
  - Mensajes en DLQ → evento no procesable, requiere intervención
  - Tasa de error en consumidor > umbral → bug o dependencia caída
```

---

## Cuándo Aplicar EDA

### ✅ Aplicar EDA cuando:

```
1. Múltiples servicios deben reaccionar al mismo hecho (fan-out).
2. Los servicios deben estar desacoplados y evolucionar independientemente.
3. Se necesita resiliencia: si un consumidor cae, los demás siguen.
4. El procesamiento puede ser asíncrono (el usuario no espera todos los efectos).
5. Se necesita escalabilidad horizontal independiente por servicio.
6. Se quiere audit trail o capacidad de replay.
```

### ❌ No aplicar EDA cuando:

```
1. Se necesita respuesta síncrona inmediata (el usuario espera el resultado).
2. El sistema es simple con pocas integraciones.
3. La consistencia eventual no es aceptable en ninguna parte del flujo.
4. El equipo no tiene experiencia con sistemas distribuidos asíncronos.
   (La complejidad operacional es significativa.)
```

---

## Buenas Prácticas

### ✅ Siempre

```
1. NOMBRAR eventos en pasado: PedidoCreado, PagoConfirmado (no CrearPedido).
2. INCLUIR id único en cada evento para deduplicación.
3. CONSUMIDORES son idempotentes: el mismo evento N veces = mismo resultado.
4. VERSIONAR el schema de los eventos: evolucionar sin breaking changes.
5. CONFIGURAR DLQ con alertas para eventos no procesables.
6. PROPAGAR correlacion_id a través de todos los servicios.
7. DOCUMENTAR qué eventos produce y consume cada servicio (Event Catalog).
8. MONITOREAR el lag de consumidores como métrica de salud crítica.
```

### ❌ Nunca

```
1. Hacer que los consumidores dependan del orden global de eventos entre topics distintos.
2. Poner lógica de negocio del productor en el consumidor.
3. Ignorar los mensajes en la DLQ.
4. Modificar el schema de un evento existente sin versionarlo.
5. Asumir que un evento llega exactamente una vez (diseñar para at-least-once).
6. Usar EDA donde se requiere respuesta síncrona — usar request/response en ese caso.
```

---

## Checklist de Implementación

### Diseño

- [ ] Eventos identificados y nombrados en tiempo pasado
- [ ] Schema de cada evento definido con campos estándar (id, tipo, timestamp, versión)
- [ ] Topics / canales definidos con convención de nombres
- [ ] Clave de particionamiento definida por agregado
- [ ] Estrategia de versionado de eventos documentada
- [ ] DLQ configurada para cada consumidor

### Implementación

- [ ] Productores incluyen id único (UUID v4) en cada evento
- [ ] Consumidores son idempotentes (tabla de eventos procesados)
- [ ] correlacion_id propagado desde el request original hasta todos los eventos
- [ ] Reintentos con backoff exponencial configurados en consumidores
- [ ] DLQ con alerta automática al recibir mensajes

### Observabilidad

- [ ] Distributed tracing configurado (correlacion_id en todos los servicios)
- [ ] Métricas de lag por consumidor
- [ ] Métricas de tasa de eventos por topic
- [ ] Dashboard de salud del sistema de mensajería
- [ ] Event Catalog documentado: qué produce y consume cada servicio

---

> **EDA = Eventos + Desacoplamiento + Asincronía + Escalabilidad = Apps Modernas**  
> "Menos acoplamiento, más reacción. El sistema reacciona a lo que ocurre, no a lo que se le ordena."