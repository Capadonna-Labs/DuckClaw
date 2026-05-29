# Admin Console Roles UX Design

## Goal

DuckClaw Admin debe separar la experiencia de dos tipos de usuarios:

- `user`: crea agentes, usa el agente `default`, conversa con agentes propios o aprobados y revisa su historial.
- `admin`: hace todo lo anterior y además opera, audita, configura, diagnostica y protege la plataforma.

La consola actual expone demasiadas pantallas técnicas en el primer nivel. Esto genera carga cognitiva, dudas sobre qué pantalla usar y riesgo de que usuarios no técnicos entren a zonas como `Runtime`, `DuckDB`, `Train`, `VNC` o integraciones internas sin entender su impacto.

## Current State

La arquitectura vigente es:

```text
Browser -> Next.js BFF (/api/admin/*) -> API Gateway (/api/v1/admin/*) -> disco | DuckDB | Redis
```

El menú actual ya agrupa rutas, pero sigue mezclando intención de usuario y subsistemas técnicos:

- Operación: `Overview`, `Playground`, `Tablero`
- Construcción: `Workers`, `Proyectos`, `MCP`, `Skills`, `Gen Image`
- Datos y runtime: `Runtime`, `DuckDB`, `Train`, `VNC`
- Administración: `Telegram`, `Edge devices`, `Acceso`, `Auditoría`, `Ajustes`

La pantalla `Runtime (agent_config)` permite editar overrides por `vault` y `chat_id`, con escrituras vía cola Redis hacia `db-writer`. Es necesaria para soporte avanzado y debugging, pero no debe aparecer como ruta principal para `user`.

## Product Model

La app debe tener dos superficies de navegación dentro del mismo shell:

### User Console

Interfaz diaria para crear y usar agentes.

Rutas visibles:

- `Inicio`: estado simple, agentes recientes, conversaciones recientes y CTAs.
- `Chat`: uso del agente `default` y selección de agentes disponibles.
- `Mis agentes`: agentes propios, agentes compartidos y agentes aprobados.
- `Crear agente`: wizard basado en plantillas aprobadas.
- `Tablero`: tareas y conversaciones del usuario, sin detalles internos de swarm.
- `Historial`: conversaciones, resultados y artefactos del usuario.
- `Ajustes`: perfil y preferencias básicas.

El usuario no ve:

- `Runtime`
- `DuckDB`
- `Train`
- `VNC`
- `MCP`
- `Skills`
- `Telegram`
- `Edge devices`
- `Auditoría`
- `Usuarios/Roles`
- `API keys`
- `Rate limits`
- `Idempotencia`

### Admin Console

Interfaz avanzada para administración, seguridad, operación y diagnóstico.

Rutas visibles:

- `Operación`: `Overview`, `Playground`, `Tablero`, `Auditoría`
- `Agentes`: `Workers`, `Proyectos`, `Skills`, `MCP`
- `Datos`: `DuckDB`, `Runtime overrides`
- `Integraciones`: `Telegram`, `Edge devices`, `Tailscale/Funnel` si se incorpora a UI
- `Seguridad`: `Usuarios`, `Roles`, `Permisos`, `API keys`, `Rate limits`, `Idempotencia`
- `Sistema avanzado`: `Settings`, `Train`, `VNC`, logs y diagnóstico

## Navigation Rules

La navegación debe responder a intención, no a implementación.

Para `user`, los nombres deben evitar jerga técnica. Preferir:

- `Chat` en vez de `Playground`
- `Mis agentes` en vez de `Workers`
- `Crear agente` en vez de `Proyectos`
- `Historial` en vez de conversaciones técnicas

Para `admin`, se permite terminología técnica, pero las rutas peligrosas deben estar bajo grupos avanzados.

`Runtime` debe renombrarse a `Runtime overrides` y moverse fuera del primer nivel. La pantalla debe explicar:

> Sobrescribe configuración por bóveda y conversación. Úsalo solo para soporte, debugging o migraciones controladas.

## Role And Permission Model

El diseño debe anticipar permisos granulares aunque la primera implementación use roles.

Roles iniciales:

- `user`: creación y uso de agentes propios o aprobados.
- `admin`: acceso completo.

Permisos futuros:

- `agent:use`
- `agent:create`
- `agent:update_own`
- `agent:publish`
- `agent:approve`
- `conversation:read_own`
- `conversation:delete_own`
- `runtime:read`
- `runtime:write`
- `duckdb:read`
- `duckdb:query`
- `security:manage_users`
- `security:manage_roles`
- `security:manage_api_keys`
- `ops:view_audit`
- `ops:manage_integrations`
- `ops:manage_rate_limits`
- `ops:manage_idempotency`

El frontend nunca debe confiar solo en ocultar navegación. El BFF y el API Gateway deben validar permisos en cada operación.

## User Flows

### User: Usar agente default

1. Entra a `Inicio`.
2. Ve CTA principal `Hablar con default`.
3. Abre `Chat` con agente `default` preseleccionado.
4. La conversación se guarda en historial del usuario.

### User: Crear agente

1. Entra a `Crear agente`.
2. Escoge una plantilla aprobada.
3. Completa nombre, propósito, tono y capacidades permitidas.
4. Se crea un agente propio en estado usable o pendiente de aprobación, según política admin.

### Admin: Diagnosticar comportamiento de una conversación

1. Entra a `Operación > Playground` o `Auditoría`.
2. Localiza conversación, agente y vault.
3. Si necesita override, entra a `Datos > Runtime overrides`.
4. Aplica cambio con confirmación y registro auditable.

### Admin: Gestionar seguridad

1. Entra a `Seguridad`.
2. Administra usuarios, roles, permisos, API keys, rate limits e idempotencia.
3. Cada cambio queda en auditoría.

## Information Architecture

Primera iteración recomendada:

```text
User Console
  Inicio
  Chat
  Mis agentes
  Crear agente
  Tablero
  Historial
  Ajustes

Admin Console
  Operación
    Overview
    Playground
    Tablero
    Auditoría
  Agentes
    Workers
    Proyectos
    Skills
    MCP
  Datos
    DuckDB
    Runtime overrides
  Integraciones
    Telegram
    Edge devices
  Seguridad
    Usuarios
    Roles y permisos
    API keys
    Rate limits
    Idempotencia
  Sistema avanzado
    Settings
    Train
    VNC
```

## UX Bottlenecks To Fix

- Too many first-level choices: reduce visible routes by role.
- Technical naming in user flow: rename user-facing routes.
- Ambiguous configuration locations: consolidate basic settings for `user`, reserve overrides for `admin`.
- Dangerous advanced screens visible too early: move under `Admin Console`.
- Runtime lacks plain-language warning: add purpose, risk and audit context.
- Conversation-heavy screens can stretch panels: keep fixed-height layouts with internal scroll.

## Implementation Phases

### Phase 1: Navigation split

- Add role-aware nav definitions for `user` and `admin`.
- Keep existing routes where possible.
- Rename labels without breaking paths.
- Make advanced groups admin-only.

### Phase 2: User Console pages

- Add user-oriented wrappers or aliases for:
  - `Chat`
  - `Mis agentes`
  - `Crear agente`
  - `Historial`
- Hide technical controls that require admin.

### Phase 3: Admin advanced sections

- Rename `Runtime` to `Runtime overrides`.
- Move it into `Datos` or `Sistema avanzado`.
- Add explanatory copy, confirmation for writes and audit metadata.

### Phase 4: Auth and permissions

- Replace demo auth with JWT sessions.
- Enforce role and permission checks in BFF.
- Add rate limiting and idempotency controls on sensitive mutations.
- Ensure server-side authorization mirrors frontend navigation.

## Acceptance Criteria

- A `user` can create and use agents without seeing infrastructure screens.
- An `admin` can access all advanced tools from clearly labeled advanced groups.
- `Runtime` is not visible to `user`.
- `Runtime` copy explains what it does and when to use it.
- Navigation has fewer first-level choices for `user`.
- Route hiding is backed by server-side permission checks before release.
- Existing admin workflows remain reachable.

## Open Implementation Decisions

- Whether `Crear agente` creates immediately usable agents or `pending_approval` agents.
- Whether `Mis agentes` is a new route or a filtered view over `Workers`.
- Whether `Historial` is a new route or the existing `ConversationInbox` promoted to a full page.
- Whether advanced admin sections should be collapsed by default or exposed through an `Advanced` toggle.

## Self Review

- No placeholders remain.
- Scope is focused on IA, roles and navigation. JWT, rate limiting and idempotency are included as phase 4 boundaries, not mixed into the first navigation refactor.
- Runtime is retained for admin use and removed from the user-facing path.
- The spec preserves current BFF/API architecture and does not require a rewrite.
