# DuckClaw Admin UI (Consola de configuración)

**Objetivo:** Consola web en `apps/duckclaw-admin` para CRUD de Telegram, DuckDB, plantillas de agentes, prompts, runtime (`agent_config`), proyectos y observabilidad (historial/traces), reutilizando el shell Next.js en `apps/duckclaw-admin` (pnpm).

**Patrones UX:** Ver `UIUX-PATTERNS.md` y sección 8 de `.cursorrules`.

---

## 1. Arquitectura

```
Browser → Next.js BFF (/api/admin/*) → API Gateway (/api/v1/admin/*) → disco | DuckDB | Redis
```

- **Auth v1:** Login demo (`admin@duckclaw.local` / `viewer@duckclaw.local`); rol `viewer` = solo lectura en BFF.
- **Auth API:** Header `X-Admin-Key` = `DUCKCLAW_ADMIN_API_KEY` (solo servidor BFF).
- **Secretos:** Tokens Telegram y API keys nunca al cliente; GET `/admin/env` enmascarado.

---

## 2. Matriz fuente de verdad

| Entidad | Lectura | Escritura | Validación |
|---------|---------|-----------|------------|
| `manifest.yaml`, `system_prompt.md`, `soul.md`, `skills/` | `forge/templates/<id>/` | `PUT .../files/{path}` | `load_manifest`, `adf_validator` (AXIS) |
| `.env` (Telegram, DuckDB, LLM) | `.env` enmascarado | `PATCH /admin/env` atómico + `.env.bak` | Dotenv spec |
| `agent_config` | DuckDB por vault | `PUT /admin/runtime/config` vía db-writer | Allow-list claves |
| `authorized_users` | DuckDB | CRUD `/admin/telegram/whitelist` | Telegram Guard spec |
| Historial chat | Redis | Solo lectura | `chat_history.py` |
| LangSmith traces | API externa | Solo lectura (opt-in) | PII masking |

Badge UI: **canónico (archivo)** vs **override (runtime)**.

---

## 3. Contrato REST `/api/v1/admin`

### Plantillas
- `GET /templates` — lista workers + metadata manifest
- `GET /templates/{id}` — árbol de archivos + contenidos editables
- `PUT /templates/{id}/files/{path}` — body `{ "content": "..." }`; path allow-list relativo al worker
- `POST /templates` — body `{ "id", "source_template?" }` — clonar desde industria
- `DELETE /templates/{id}` — deny-list: `entry_router`, `manager_router`, workers sistema
- `POST /templates/{id}/validate` — ADF + manifest
- `GET /templates/{id}/vault-options` — `.duckdb` del usuario + `db/shared/` (ver [TEMPLATE_VAULT_BINDING](TEMPLATE_VAULT_BINDING.md))
- `GET|PUT /templates/{id}/vault-binding` — `forge_context.vault_binding` en manifest

### Proyectos
- `POST /projects` — alias `POST /templates` + opcional apply `schema.sql`

### Entorno
- `GET /env` — claves permitidas enmascaradas
- `PATCH /env` — merge parcial de claves permitidas

### Runtime DuckDB
- `GET /runtime/vaults`
- `GET /runtime/config?vault=&chat_id=`
- `PUT /runtime/config` — `{ vault, chat_id, key, value }`

### DuckDB Explorer (consola `/duckdb`)

Ver [`ADMIN_DUCKDB_EXPLORER.md`](ADMIN_DUCKDB_EXPLORER.md).

| Método | Ruta |
|--------|------|
| `GET` | `/duckdb/tables` |
| `POST` | `/duckdb/query` |
| `GET` | `/duckdb/pgq-graph` |
| `POST` | `/duckdb/vector-search` |

### Acceso (usuarios, roles, permisos)

Ver [`ADMIN_ACCESS_MANAGEMENT.md`](ADMIN_ACCESS_MANAGEMENT.md).

| Método | Ruta |
|--------|------|
| `POST` | `/auth/login` |
| `GET` | `/access/overview` |
| `GET/POST/PATCH/DELETE` | `/console-users` |
| `GET/POST/DELETE` | `/access/shared-grants` |

### Telegram
- `GET /telegram/routes` — parseo `DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES`
- `GET|POST|DELETE /telegram/whitelist`

### Playground chat (imágenes)

Ver [`ADMIN_CHAT_IMAGE_ATTACHMENTS.md`](ADMIN_CHAT_IMAGE_ATTACHMENTS.md).

- `POST /playground/chat` — body opcional `images[]` (`mime_type`, `data_base64`); VLM en gateway antes del worker.
- `PUT /playground/model` — `{ chat_id, provider, model?, base_url? }`; equivalente a `/model provider=…` por conversación (agent_config).
- `GET /playground/config?chat_id=` — LLM efectivo del chat (override) o .env global.

### Catálogo MCP y Skills

Ver [`ADMIN_MCP_OFFICIAL_CATALOG.md`](ADMIN_MCP_OFFICIAL_CATALOG.md).

- Navegación: **MCP** antes que **Skills** en sidebar.
- `GET /catalog/mcp` — incluye `official_reference` (servidores de referencia [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers)).
- `GET /catalog/skills` — bridges en `forge/skills/` y skills por plantilla.

### Observabilidad
- `GET /chats/history?tenant_id=&session_id=`
- `GET /traces/langsmith?run_id=` — opcional si `LANGCHAIN_API_KEY`

### Conversaciones admin (inbox unificado)
Bandeja única por `tenant_id` para retomar hilos del Playground y del chat flotante. El historial de mensajes sigue en Redis (`chat_history.py`); el índice añade metadatos consultables.

| Clave Redis | Tipo | Contenido |
|-------------|------|-----------|
| `duckclaw:admin:conv:z:{tenant_id}` | ZSET | `session_id` → score `updated_at` (unix ms) |
| `duckclaw:admin:conv:meta:{tenant_id}:{session_id}` | JSON | Metadatos de conversación |

**Metadatos:** `session_id`, `tenant_id`, `title`, `created_at`, `updated_at`, `actor` (`X-Duckclaw-Actor`), `section` (`playground` \| `kanban` \| `vnc` \| `train` \| `root` \| `other`), `last_worker_id`, `workers[]`, `last_message_preview`, `message_count`, `origin=admin_ui`.

**TTL:** alineado con `DUCKCLAW_CHAT_HISTORY_TTL_SEC` (default 7 días); override opcional `DUCKCLAW_ADMIN_CONV_INDEX_TTL_SEC`.

**Session IDs:** nuevos hilos `admin-conv-{uuid}`; legacy `admin-playground` / `admin-section-*` se indexan al guardar historial o vía reindex.

| Método | Ruta |
|--------|------|
| `GET` | `/conversations?tenant_id=&section=&worker=&actor=&q=&limit=&offset=` |
| `POST` | `/conversations` — body `{ title?, section?, worker_id? }` |
| `GET` | `/conversations/{session_id}` — meta + `messages` |
| `PATCH` | `/conversations/{session_id}` — body `{ title }` |
| `DELETE` | `/conversations/{session_id}` |
| `POST` | `/conversations/reindex?tenant_id=` — SCAN historial admin y registrar en índice |

UI: `ConversationInbox` en Playground (panel lateral) y burbuja flotante (drawer); `localStorage` `duckclaw-admin-active-conv` para conversación activa.

### Health (admin)
- `GET /health` — gateway + workers count + flags Redis

### Tablero (Kanban) y agent swarms
- `GET /kanban/worker-states?workers=` — último `task_audit_log` por worker; claves `worker_id` y `{worker_id}:1`.
- `GET /kanban/swarm-slots?workers=&tenant_id=` — instancias activas en Redis (`list_active_swarm_slots` en `packages/agents/.../subagent_run_id.py`) y estados `{worker_id}:{slot}`.
- BFF `GET /api/admin/kanban` — persiste en `.duckclaw/admin-kanban.json` y sincroniza con `/workers` del playground.

**Modelo swarm (Tablero):**
- Cada worker del equipo (`/workers`) tiene siempre tarjeta auto-sync **`{worker_id} 1`** (instancia base).
- Ejecuciones paralelas del mismo worker aparecen como **`{worker_id} 2`**, **`3`**, … mientras el token siga en el ZSET `duckclaw:subagent_active:{tenant}:{worker}[:{chat}]` (rank + 1 = slot). Al `release`, las tarjetas con slot ≥ 2 desaparecen del tablero.
- Estado slot 1: `en_progreso` si activo en Redis; si no, audit `task_audit_log`. Slots ≥ 2: siempre `en_progreso` mientras activos.
- UI `/kanban`: filtro **Filtrar por agente** (cliente, `sessionStorage` `duckclaw-kanban-worker-filter`); con worker elegido solo se muestran tarjetas swarm de ese `worker_id`; tarjetas manuales solo en **Todos**. Contador `visibles / total` por columna con filtro activo.
- Referencia números en logs/chat: `specs/core/00_Flujo de Vida del Dato (Wizard).md` (sufijo numérico subagente).

### VNC (browser sandbox + contenedores Strix)
- `GET /sandbox/status` — Docker, `STRIX_BROWSER_PUBLISH_NOVNC`, `DUCKCLAW_PUBLIC_URL`, TTL.
- `GET /sandbox/sessions` — contenedores `strix_sandbox_*` (tipo `browser` | `compute`) + sesiones noVNC activas.
- `POST /sandbox/novnc/prepare` — body `{ chat_id?, worker_id?, tenant_id? }`; levanta browser-env y devuelve `vnc_url` (proxy `/api/v1/sandbox/novnc/view/{token}/…`).
- `GET /sandbox/chat-policy` — `sandbox_enabled`, `sandbox_network_enabled`, política YAML vs efectiva, `network_toggle_available`, `browser_sandbox` del worker.
- `POST /sandbox/network` — body `{ chat_id, enabled, worker_id?, tenant_id? }`; persiste `sandbox_network_enabled`, recrea contenedor Strix de la sesión (respeta YAML: Quant-Trader no permite toggle).
- UI `/vnc` (solo rol admin): iframe noVNC + tabla de contenedores + toggle **Internet en sandbox** (mismo `chat_id` que el chat flotante de la sección, p. ej. `admin-section-vnc`); requiere `STRIX_BROWSER_PUBLISH_NOVNC=1` en el gateway. Ver [`STRIX_BROWSER_NOVNC.md`](STRIX_BROWSER_NOVNC.md).
- `run_sandbox` soporta **python** y **bash** (sin VNC); el visor es solo para **browser sandbox** (Playwright).

Errores: JSON `{ "type", "title", "status", "detail" }` (RFC 7807 style).

---

## 4. Rutas frontend

| Ruta | Función |
|------|---------|
| `/login` | Account Registration pattern |
| `/overview` | Status + Activity Stream |
| `/templates` | Lista + Table Filter |
| `/templates/[workerId]` | Module Tabs editor |
| `/projects/new` | Wizard |
| `/runtime` | agent_config grid |
| `/admin/access` | usuarios consola, Telegram whitelist, grants shared DB |
| `/telegram` | bots + whitelist (enlace a Acceso para usuarios) |
| `/duckdb` | vaults |
| `/traces` | historial + LangSmith |
| `/settings` | Settings pattern |
| `/kanban` | Tablero de agentes (swarms 1..n, filtro por worker) |
| `/vnc` | Visor noVNC del browser sandbox + estado contenedores Strix |

---

## 5. Workers protegidos (no DELETE)

`entry_router`, `manager_router`, y los definidos en deny-list del router admin.

---

## 6. Criterios de aceptación

1. Login demo admin puede listar y editar `system_prompt.md` de un worker y ver validación.
2. Viewer no puede PUT/DELETE (403 en BFF).
3. PATCH env persiste en `.env` con backup; valor completo de token no aparece en GET.
4. Overview muestra health del gateway.
5. Crear proyecto desde wizard clona `business_standard`.
