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

### Telegram
- `GET /telegram/routes` — parseo `DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES`
- `GET|POST|DELETE /telegram/whitelist`

### Observabilidad
- `GET /chats/history?tenant_id=&session_id=`
- `GET /traces/langsmith?run_id=` — opcional si `LANGCHAIN_API_KEY`

### Health (admin)
- `GET /health` — gateway + workers count + flags Redis

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
| `/telegram` | bots + whitelist |
| `/duckdb` | vaults |
| `/traces` | historial + LangSmith |
| `/settings` | Settings pattern |

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
