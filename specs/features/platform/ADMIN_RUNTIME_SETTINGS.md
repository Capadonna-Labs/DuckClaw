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

## Criterios de Aceptación

- `bootstrap_core_schema` crea `admin_runtime_settings`.
- Tests cubren precedencia DB > env > default.
- Secrets nunca salen en claro en `GET /settings/runtime`.
- `/duckdb` no renderiza “Variables .env” como panel principal.
- `DUCKCLAW_ADMIN_DUCKDB_LEGACY_SCHEMAS` funciona desde DB-first con fallback env.
- `/playground/config` usa defaults DB-first del actor sin pisar overrides por conversación.
