# SPEC — CQRS (Command Query Responsibility Segregation)

> Versión: 1.0.0 | Tipo: Patrón Arquitectónico  
> Aplica a: Sistemas con alta carga de lectura/escritura o requisitos diferenciados por operación

---

## Definición

**CQRS** es un patrón arquitectónico que separa las operaciones de un sistema en dos modelos distintos e independientes:

```
COMANDO (Command) = Operación que CAMBIA el estado del sistema
  Crear, actualizar, eliminar, confirmar, cancelar.
  No retorna datos. Retorna éxito/fallo.
  Prioridad: consistencia, validación, reglas de negocio.

CONSULTA (Query) = Operación que LEE el estado del sistema
  Obtener, buscar, listar, filtrar, reportar.
  No cambia nada. Solo retorna datos.
  Prioridad: velocidad, formato óptimo para presentación.

MODELO TRADICIONAL (CRUD):
  Un solo modelo maneja lectura Y escritura.
  El mismo objeto de dominio se usa para guardar y para mostrar.
  → Conflicto: lo que necesitas para escribir ≠ lo que necesitas para leer.

MODELO CQRS:
  Modelo de escritura (Write Model): optimizado para consistencia y reglas de negocio.
  Modelo de lectura (Read Model):   optimizado para velocidad y formato de consulta.
  → Cada lado hace exactamente lo que necesita, sin compromisos.
```

---

## Por qué separar lectura y escritura

```
PROBLEMA EN SISTEMAS CRUD TRADICIONALES:

1. IMPEDANCIA DE MODELOS
   El modelo normalizado (escritura) requiere múltiples JOINs para mostrar datos.
   Ejemplo: mostrar un pedido con cliente, productos, dirección, estado, historial
   → 5 tablas, JOINs costosos, solo para una pantalla.

2. CONTENCIÓN POR RECURSOS
   Las consultas pesadas (reportes, búsquedas) compiten con las escrituras
   por los mismos índices y locks de base de datos.

3. ESCALABILIDAD ASIMÉTRICA
   En la mayoría de sistemas: lecturas >> escrituras (80-95% vs 5-20%).
   No tiene sentido escalar lectura y escritura de la misma manera.

4. OPTIMIZACIÓN IMPOSIBLE
   Optimizar para lectura (índices, denormalización) empeora escritura.
   Optimizar para escritura (normalización, constraints) empeora lectura.

SOLUCIÓN CQRS:
  Cada lado se optimiza independientemente sin afectar al otro.
```

---

## Arquitectura CQRS

```
                        ┌─────────────────────┐
                        │     APLICACIÓN      │
                        └──────────┬──────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                                         │
              ▼                                         ▼
   ┌──────────────────────┐              ┌──────────────────────┐
   │   COMANDO (Write)    │              │   CONSULTA (Read)    │
   │                      │              │                      │
   │ CrearPedidoCommand   │              │ ObtenerPedidoQuery   │
   │ ConfirmarPagoCommand │              │ ListarPedidosQuery   │
   │ CancelarReservaCmd   │              │ BuscarProductosQuery │
   └──────────┬───────────┘              └──────────┬───────────┘
              │                                     │
              ▼                                     ▼
   ┌──────────────────────┐              ┌──────────────────────┐
   │   COMMAND HANDLER    │              │   QUERY HANDLER      │
   │                      │              │                      │
   │ Valida el comando    │              │ Ejecuta la consulta  │
   │ Aplica reglas        │              │ directamente contra  │
   │ de negocio           │              │ el Modelo de Lectura │
   │ Actualiza el estado  │              │ (sin lógica de       │
   └──────────┬───────────┘              │ negocio compleja)    │
              │                          └──────────┬───────────┘
              ▼                                     │
   ┌──────────────────────┐                         │
   │   MODELO ESCRITURA   │                         ▼
   │   (Write Model)      │              ┌──────────────────────┐
   │                      │              │   MODELO LECTURA     │
   │ Normalizado          │              │   (Read Model)       │
   │ Orientado a dominio  │    EVENTO    │                      │
   │ Consistencia fuerte  │ ──────────►  │ Denormalizado        │
   │ (SQL normalizado,    │              │ Orientado a UI/API   │
   │  Document Store)     │              │ Consistencia eventual│
   └──────────────────────┘              │ (Vistas, NoSQL,      │
                                         │  Search Index)       │
                                         └──────────────────────┘
```

---

## Commands — Especificación

### Anatomía de un Command

```
Un Command es:
  - Una intención de cambiar el estado del sistema
  - Inmutable (no cambia una vez creado)
  - Nombrado en imperativo: CrearPedido, ConfirmarPago, CancelarReserva
  - Contiene todos los datos necesarios para ejecutar la operación
  - Retorna void / resultado mínimo (éxito/fallo + ID generado si aplica)

ESTRUCTURA:
  {
    tipo:          "CrearPedido"
    id_comando:    UUID (para trazabilidad e idempotencia)
    timestamp:     ISO 8601 UTC
    ejecutado_por: user_id (quién ordenó la acción)
    datos: {
      cliente_id: "user_123"
      items: [{ producto_id: "SKU-456", cantidad: 2 }]
      direccion_entrega: { ... }
    }
  }
```

### Command Handler

```
Responsabilidades:
  1. Recibir el command
  2. VALIDAR que el command es ejecutable:
     - Validación de schema (campos requeridos, tipos)
     - Validación de reglas de negocio (stock disponible, usuario activo, etc.)
     - Validación de autorización (¿tiene permisos para esto?)
  3. Si inválido: retornar error detallado. NO proceder.
  4. Ejecutar la operación sobre el modelo de escritura
  5. Emitir evento(s) de dominio que describan el cambio ocurrido
  6. Retornar éxito (+ ID del recurso creado si aplica)

REGLA: El Command Handler NUNCA retorna datos de dominio complejos.
  ✅ Retorna: { exito: true, id_pedido: "PED-001" }
  ❌ No retorna: el objeto Pedido completo con todos sus datos.
  Si necesitas los datos después del command: haz una Query.
```

### Ejemplos de Commands

```
ESCRITURA — Commands (cambian estado):
  CrearPedidoCommand         → crea el pedido
  ValidarStockCommand        → reserva el stock
  ConfirmarPagoCommand       → registra el cobro
  MarcarPedidoEnviadoCommand → actualiza el estado
  CancelarPedidoCommand      → cancela y libera stock

NO SON COMMANDS (son Queries disfrazadas):
  ObtenerEstadoPedido        → esto es una Query
  CalcularTotalCarrito       → esto es una Query (cómputo sin efecto)
```

---

## Queries — Especificación

### Anatomía de una Query

```
Una Query es:
  - Una solicitud de datos, sin efectos secundarios
  - Nombrada en descriptivo: ObtenerPedido, ListarPedidosPorUsuario, BuscarProductos
  - Puede retornar exactamente lo que el cliente necesita (forma libre)
  - Puede tener proyecciones distintas según el caso de uso
  - NUNCA modifica estado

ESTRUCTURA:
  {
    tipo:      "ObtenerDetallePedido"
    id_query:  UUID
    parametros: {
      pedido_id: "PED-001"
      usuario_id: "user_123"   // para control de acceso
    }
    proyeccion: "detalle_completo" | "resumen" | "estado_solo"
  }
```

### Query Handler

```
Responsabilidades:
  1. Recibir los parámetros de la consulta
  2. Validar autorización (¿puede este usuario ver estos datos?)
  3. Consultar directamente el Modelo de Lectura (sin pasar por el dominio)
  4. Retornar los datos en el formato exacto que el cliente necesita

REGLA: El Query Handler NO tiene lógica de negocio compleja.
  Lee, transforma y retorna. Nada más.
  La lógica de negocio vive en los Command Handlers y el dominio.
```

### Ejemplos de Queries

```
LECTURA — Queries (no cambian estado):
  ObtenerDetallePedidoQuery     → pedido completo con todos los datos
  ListarPedidosPorUsuarioQuery  → listado paginado de pedidos de un usuario
  PedidosPorEstadoQuery         → filtro por estado (pendiente, enviado, etc.)
  ReporteVentasMensualQuery     → agregación para reporting
  BuscarProductosQuery          → búsqueda full-text con filtros
  TopProductosQuery             → ranking con métricas calculadas
```

---

## Modelos de Datos — Escritura vs Lectura

### Modelo de Escritura (Write Model)

```
CARACTERÍSTICAS:
  - Normalizado (3ra Forma Normal o similar)
  - Optimizado para integridad y consistencia
  - Refleja el modelo de dominio
  - Indices mínimos (optimizados para escritura)
  - Reglas de negocio aplicadas (constraints, validaciones)

EJEMPLO — Pedido en modelo de escritura (normalizado):
  tabla pedidos:      id, cliente_id, estado, fecha_creacion, total
  tabla items_pedido: id, pedido_id, producto_id, cantidad, precio_unitario
  tabla pagos:        id, pedido_id, monto, estado, timestamp
  tabla direcciones:  id, pedido_id, calle, ciudad, codigo_postal

  Para mostrar el detalle completo: JOIN de 4 tablas.
```

### Modelo de Lectura (Read Model)

```
CARACTERÍSTICAS:
  - Denormalizado (datos pre-joinados, pre-calculados)
  - Optimizado para consultas específicas
  - Un documento/vista por caso de uso de lectura
  - Sin reglas de negocio — solo datos listos para mostrar
  - Puede ser eventualmente consistente (ver sección de sincronización)
  - Tecnología puede diferir del modelo de escritura (NoSQL, Search, Cache)

EJEMPLO — Pedido en modelo de lectura (denormalizado):
  {
    id_pedido: "PED-001",
    estado: "enviado",
    fecha_creacion: "2024-05-18T10:00:00Z",
    cliente: {
      id: "user_123",
      nombre: "Ana García",
      email: "ana@mail.com"
    },
    items: [
      { nombre: "Laptop", cantidad: 1, precio: 1200.00, imagen_url: "..." }
    ],
    totales: {
      subtotal: 1200.00,
      descuento: 0,
      envio: 15.00,
      total: 1215.00
    },
    direccion_entrega: "Calle Mayor 1, Madrid 28001",
    ultimo_evento: "Paquete salió del almacén a las 14:30"
  }

  → Una sola lectura, sin JOINs, exactamente lo que necesita la pantalla de detalle.
```

---

## Sincronización entre Modelos

Cuando el Command Handler actualiza el modelo de escritura, el modelo de lectura debe actualizarse para reflejar el cambio.

### Vía Eventos de Dominio

```
FLUJO:
  1. Command Handler actualiza Modelo de Escritura
  2. Emite Evento de Dominio: PedidoCreadoEvent { datos del pedido }
  3. Projection Handler escucha el evento
  4. Projection Handler actualiza el Modelo de Lectura
     (construye la vista denormalizada)
  5. Las próximas Queries leen la vista actualizada

TIPOS DE CONSISTENCIA:
  SÍNCRONA (consistencia inmediata):
    El modelo de lectura se actualiza en la misma transacción que la escritura.
    El comando retorna cuando ambos modelos están actualizados.
    Ventaja: sin lag. Desventaja: acopla los modelos, más lento.

  ASÍNCRONA (consistencia eventual):
    El comando actualiza el modelo de escritura y emite el evento.
    El evento se procesa en background → actualiza el modelo de lectura.
    Puede haber un lag de milisegundos a segundos.
    Ventaja: comandos rápidos, modelos desacoplados. Desventaja: eventual consistency.
    RECOMENDADO para la mayoría de casos en CQRS.
```

### Projection Handlers

```
Un Projection Handler es el componente que:
  - Escucha eventos de dominio
  - Transforma los datos del evento al formato del modelo de lectura
  - Actualiza la vista / documento / índice de lectura

PROPIEDADES CRÍTICAS:
  Idempotente: procesar el mismo evento N veces produce el mismo resultado.
  Ordenado: los eventos deben procesarse en orden para consistencia.
  Recuperable: si falla, puede reiniciar desde el último evento procesado.

EJEMPLO:
  Evento: PedidoEstadoCambiadoEvent { pedido_id: "PED-001", nuevo_estado: "enviado" }
  Projection: actualizar documento de lectura PED-001 → estado = "enviado"
              actualizar índice de búsqueda → filtro por estado
              actualizar vista de estadísticas
```

---

## Event Bus (Bus de Eventos)

```
El Event Bus es el canal que conecta Commands con Projections.

OPCIONES:
  EN PROCESO (in-process):
    Los eventos se publican y consumen en el mismo proceso.
    Sin dependencias externas. Síncrono o asíncrono interno.
    Ideal para: CQRS en una sola aplicación (inicio de adopción).

  FUERA DE PROCESO (external):
    Los eventos se publican a un broker externo.
    Kafka, RabbitMQ, AWS SNS/SQS, Google Pub/Sub.
    Los Projection Handlers consumen del broker.
    Ideal para: microservicios, sistemas distribuidos, alta escala.

GARANTÍAS NECESARIAS:
  At-least-once delivery: el evento llega al menos una vez.
  Order preservation: los eventos del mismo agregado llegan en orden.
  → Combinar con Projection Handlers idempotentes.
```

---

## Cuándo Aplicar CQRS

### ✅ Aplicar CQRS cuando:

```
1. Las lecturas son mucho más frecuentes que las escrituras (> 70% lecturas)
   y requieren formatos muy distintos al modelo de escritura.

2. Las consultas necesitan datos de múltiples agregados con JOINs complejos
   que afectan el rendimiento de escritura.

3. Se necesita escalar lectura y escritura de forma independiente.

4. Las vistas de lectura son muy distintas entre sí (listado vs detalle vs reporte).

5. El sistema usa Event Sourcing (CQRS es compañero natural de ES).

6. Hay equipos distintos trabajando en el modelo de escritura (dominio) y
   el modelo de lectura (reporting/UI).
```

### ❌ No aplicar CQRS cuando:

```
1. El sistema es simple: CRUD con pocas reglas de negocio.
   La complejidad de CQRS no se justifica.

2. El equipo es pequeño y la curva de aprendizaje sería un obstáculo.

3. La consistencia eventual no es aceptable para el negocio.
   (Operaciones que requieren datos absolutamente frescos inmediatamente.)

4. No hay diferencia significativa entre el modelo de escritura y lectura.

REGLA: CQRS no es para todo. Usarlo donde la complejidad del dominio lo justifica.
```

---

## Buenas Prácticas

### ✅ Siempre

```
1. NOMBRAR con intención clara: XxxCommand, XxxQuery, XxxEvent, XxxHandler.
2. COMMANDS son inmutables una vez creados.
3. QUERIES nunca modifican estado — ningún side effect.
4. PROJECTION HANDLERS son idempotentes.
5. EVENTS son hechos inmutables del pasado — en pasado: PedidoCreado, PagoConfirmado.
6. DOCUMENTAR el lag esperado de consistencia eventual.
7. EXPONER el estado de sincronización si el lag puede ser visible para el usuario.
8. VERSIONAR los eventos para evolución sin breaking changes.
```

### ❌ Nunca

```
1. Retornar datos complejos desde un Command Handler (es responsabilidad de Query).
2. Modificar estado desde un Query Handler.
3. Saltarse el Event Bus para actualizar el Read Model directamente desde el Command.
4. Ignorar el orden de los eventos en los Projection Handlers.
5. Hacer los Projection Handlers no idempotentes (duplicados causarán datos corruptos).
```

---

## Checklist de Implementación

### Diseño

- [ ] Operaciones clasificadas: Commands (escritura) vs Queries (lectura)
- [ ] Commands nombrados en imperativo (verbo + sustantivo)
- [ ] Queries nombrados descriptivamente (Obtener/Listar/Buscar + entidad)
- [ ] Modelo de escritura (normalizado) y lectura (denormalizado) definidos por separado
- [ ] Eventos de dominio identificados (qué cambios deben sincronizar el Read Model)
- [ ] Estrategia de consistencia definida: síncrona vs eventual

### Implementación

- [ ] Command Handlers con validación completa antes de ejecutar
- [ ] Command Handlers emiten eventos de dominio
- [ ] Projection Handlers son idempotentes
- [ ] Projection Handlers preservan orden de eventos
- [ ] Event Bus configurado con al-least-once delivery

### Operacional

- [ ] Métricas de lag entre Write Model y Read Model
- [ ] Proceso de rebuild del Read Model documentado (para sincronización tras fallo)
- [ ] Versionado de eventos implementado
- [ ] Alertas si el lag de sincronización supera el umbral aceptable

---

> **CQRS = Separación + Optimización + Escalabilidad + Flexibilidad**  
> "Escribimos con consistencia, leemos con velocidad. Cada lado hace lo que mejor sabe hacer."