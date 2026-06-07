# Admin Runtime Settings DB-first

Versión: 1.0 · Fecha: 2026-06-03

## Objetivo

Mover la configuración editable de DuckClaw Admin desde paneles crudos de `.env` hacia DuckDB, manteniendo `.env` solo como bootstrap técnico y fallback compatible.

Relacionado:

- `DUCKCLAW_ADMIN_UI.md`
- `ADMIN_IDENTITY_RBAC_ERD.md`
- `ADMIN_ACCESS_MANAGEMENT.md`

## Principio

DuckDB es la fuente de verdad para configuración operativa editable desde la consola. `.env` conserva valores necesarios para arrancar el proceso, secretos iniciales y compatibilidad con código legacy.

La UI no debe presentar una lista cruda de variables `.env` como interfaz principal.

## Tabla Canónica

`main.admin_runtime_settings`

```sql
CREATE TABLE IF NOT EXISTS main.admin_runtime_settings (
    setting_id VARCHAR PRIMARY KEY,
    tenant_id VARCHAR NOT NULL DEFAULT 'global',
    actor_email VARCHAR,
    domain VARCHAR NOT NULL,
    key VARCHAR NOT NULL,
    value_text TEXT,
    value_json TEXT,
    value_kind VARCHAR NOT NULL DEFAULT 'string',
    secret BOOLEAN DEFAULT false,
    source VARCHAR NOT NULL DEFAULT 'db',
    active BOOLEAN DEFAULT true,
    created_by VARCHAR,
    updated_by VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, actor_email, domain, key)
);
```

## Dominios Iniciales

- `duckdb`: vaults, schemas legacy permitidos, modo explorer.
- `llm`: proveedor/modelo/base URL no secreta.
- `playground`: preferencias del actor para agente y bóveda por defecto.
- `telegram`: configuración operativa no secreta.
- `mcp`: toggles y rutas de servidores.
- `security`: flags de sesión, auditoría y políticas visibles.
- `advanced`: compatibilidad temporal con claves legacy.

## Precedencia

Lectura efectiva:

1. Setting DB activo para `(tenant_id, actor_email, domain, key)`.
2. Setting DB activo para `(tenant_id, NULL, domain, key)`.
3. Setting DB activo para `('global', NULL, domain, key)`.
4. `.env` bootstrap/fallback permitido.
5. Default de código.

Las escrituras desde UI solo actualizan DuckDB. No editan `.env`.

## Secretos

- `secret=true` significa write-only desde UI.
- GET devuelve estado enmascarado: `configured=true`, `masked_value="********"`.
- PATCH permite reemplazar el valor, pero nunca leerlo en claro.
- Las respuestas no deben incluir API keys ni tokens.

## Auditoría

Cada escritura debe registrar:

- actor
- tenant
- domain
- key
- si era secreto
- origen `admin_ui`
- timestamp

La auditoría puede ir a `admin_resource_events` con `resource_kind='runtime_setting'`.

## API Gateway

| Método | Ruta | Uso |
|--------|------|-----|
| `GET` | `/settings/runtime` | Lista dominios y valores efectivos enmascarados |
| `PATCH` | `/settings/runtime` | Actualiza settings DB-first |
| `POST` | `/settings/runtime/apply` | Opcional: fuerza recarga/aplicación si el dominio lo requiere |

`GET /env` y `PATCH /env` quedan legacy para compatibilidad y diagnóstico, no como flujo principal de usuario.

## Primer Corte DuckDB

Migrar primero la sección `/duckdb`:

- El panel “Variables .env” se reemplaza por “Configuración DuckDB”.
- `DUCKCLAW_ADMIN_DUCKDB_LEGACY_SCHEMAS` se lee desde `admin_runtime_settings` con fallback env.
- La UI muestra `tenant_id`, `actor_email`, vault efectiva y schemas legacy configurados.
- La limpieza de schemas sigue usando confirmación explícita `DROP_LEGACY_SCHEMAS`.

## Segundo Corte Playground / LLM

Migrar defaults personales de Playground:

- `llm.provider`: proveedor LLM preferido del actor.
- `llm.model`: modelo LLM preferido del actor.
- `llm.base_url`: endpoint no secreto del proveedor cuando aplica.
- `playground.default_worker_id`: agente preferido del actor para conversaciones nuevas.
- `playground.default_vault_db_path`: bóveda preferida del actor para conversaciones nuevas.

Precedencia de lectura en `/playground/config`:

1. Override explícito por conversación (`/model`, selector de agente, selector de bóveda en Redis).
2. Runtime Settings DB-first del actor.
3. Configuración legacy (`agent_config` global / `.env`) como fallback compatible.
4. Defaults de código.

La acción UI “Guardar como default” en Playground escribe solo en `admin_runtime_settings` con scope `actor`.

## Tercer Corte Telegram

Migrar rutas webhook de Telegram:

- `telegram.webhook_routes`: valor compacto de rutas webhook, secreto/write-only porque contiene tokens Bot API.
- Lectura efectiva: Runtime Settings DB-first → `DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES` en `.env` → vacío.
- `GET /telegram/routes` parsea la configuración efectiva y devuelve tokens enmascarados, `source` y `runtime_key`.
- `PUT /telegram/routes` escribe solo en `admin_runtime_settings`; no modifica `.env`.
- El Gateway registra rutas dinámicas al arrancar desde `telegram.webhook_routes`, con fallback `.env` para compatibilidad.

## Cuarto Corte MCP

Migrar configuración visible de MCP:

- `mcp.port`: puerto del servidor DuckClaw MCP HTTP.
- Lectura efectiva: Runtime Settings DB-first → `DUCKCLAW_MCP_PORT` en `.env` → `8001`.
- `GET /catalog/mcp` devuelve `duckclaw_mcp.port`, `source` y `runtime_key`.
- La UI `/mcp` permite guardar el puerto en `admin_runtime_settings`; reiniciar MCP aplica el cambio.
- `config/mcp_servers.yaml` permanece como catálogo estático/stdio en v1; editarlo desde UI sigue fuera de alcance.

## Quinto Corte ComfyUI

Migrar configuración visible de imágenes:

- `comfyui.api_url`: URL base HTTP del API ComfyUI.
- `comfyui.timeout_sec`: timeout total de generación.
- Lectura efectiva: Runtime Settings DB-first → `COMFYUI_API_URL` / `COMFYUI_TIMEOUT_SEC` en `.env` → defaults locales.
- `GET /comfyui/status` devuelve fuente efectiva, runtime keys, estado de checkpoints y health.
- `POST /comfyui/generate` usa la configuración efectiva del Gateway y no depende solo de variables de entorno.
- La UI `/gen/image` permite guardar URL y timeout en DuckDB; `.env` queda como fallback bootstrap.

## Criterios de Aceptación

- `bootstrap_core_schema` crea `admin_runtime_settings`.
- Tests cubren precedencia DB > env > default.
- Secrets nunca salen en claro en `GET /settings/runtime`.
- `/duckdb` no renderiza “Variables .env” como panel principal.
- `DUCKCLAW_ADMIN_DUCKDB_LEGACY_SCHEMAS` funciona desde DB-first con fallback env.
- `/playground/config` usa defaults DB-first del actor sin pisar overrides por conversación.
- `/telegram` no renderiza un editor crudo de `.env` y guarda rutas webhook en DuckDB DB-first.
- `/mcp` muestra y guarda `mcp.port` DB-first con fallback `DUCKCLAW_MCP_PORT`.
- `/gen/image` muestra y guarda `comfyui.api_url` y `comfyui.timeout_sec` DB-first.
