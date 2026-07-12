# Integration Secrets (API keys DB-first)

Versión: 1.0 · Fecha: 2026-07-11

## Objetivo

Centralizar API keys de integraciones en `admin_runtime_settings` sin obligar a editar `.env` en operación diaria.

Relacionado:

- `ADMIN_RUNTIME_SETTINGS.md`
- `REMOTE_MCP_CONNECTORS.md` (patrón Bearer MCP)
- `WORKER_COMPOSITION_UI.md`

## Precedencia

1. `admin_runtime_settings` — `domain=integrations`, scope tenant → global
2. `.env` bootstrap (fallback legacy por integración)
3. Gap visible en Admin / Playground

## Catálogo canónico

Fuente empaquetada: `packages/shared/src/duckclaw/seeds/framework_integration_secrets_v1.json`

Loader: `duckclaw.integration_catalog`

API Admin: `GET /api/v1/admin/integrations/catalog` — grupos + estado `configured` por tenant/actor.

El frontend **no** hardcodea la lista; consume el catálogo del gateway (mismo patrón que `skill-categories`).

## Ámbito multi-tenant

| Scope PATCH | Uso |
|-------------|-----|
| `tenant` | Default — clave del workspace (N usuarios del mismo negocio) |
| `global` | Plataforma compartida (operador) |
| `actor` | Clave personal del usuario admin |

Precedencia lectura: tenant → global → actor → `.env` bootstrap.

## Tabla de claves

| Setting key | Integración | Env fallback |
|-------------|-------------|--------------|
| `tavily.api_key` | Skill `research` / `tavily_search` | `TAVILY_API_KEY` |
| `openweather.api_key` | Skill `openweather` | `OPENWEATHER_API_KEY` |
| `fal.api_key` | Skill `fal` | `FAL_KEY`, `FAL_API_KEY` |
| `higgsfield.api_key` | Skill `higgsfield` REST | `HIGGSFIELD_API_KEY`, `HIGGSFIELD_KEY` |
| `github.token` | GitHub / MCP stdio | `GITHUB_TOKEN` |

Todas con `secret=true` (write-only en UI).

## Qué sigue en `.env`

Bootstrap e infra: `REDIS_URL`, `DUCKCLAW_GATEWAY_DB_PATH`, `DUCKCLAW_ADMIN_API_KEY`, LLM keys del gateway.

Ver `.env.example` — sección integraciones opcionales como fallback.

## ¿Por qué JSON?

| Ventaja | Detalle |
|---------|---------|
| Versionado | El catálogo viaja con el framework (git, releases) |
| Sin redeploy UI | Admin lee `GET /integrations/catalog` |
| Validación | `validate_integration_secrets_pack` rechaza ids/keys duplicados |
| Extensible | Fork copia `config/integration_secrets_pack.example.json` |

**No uses JSON para:** APIs ad-hoc que cada usuario inventa en runtime → futuro dominio `skill_secret.*` + skill Python custom.

## Prioridad del pack (override)

| Orden | Origen |
|-------|--------|
| 1 | `DUCKCLAW_INTEGRATION_SECRETS_PACK_PATH` |
| 2 | `{DUCKCLAW_REPO_ROOT}/config/integration_secrets_pack.json` |
| 3 | Bundled `framework_integration_secrets_v1.json` |

Ejemplo de extensión: `config/integration_secrets_pack.example.json`

## Agregar integración N (checklist)

1. **Seed JSON** — añadir entrada en `framework_integration_secrets_v1.json` (o pack override):

```json
{
  "id": "mi_saas",
  "setting_key": "mi_saas.api_key",
  "label": "Mi SaaS",
  "description": "Qué hace para el usuario.",
  "env_keys": ["MI_SAAS_API_KEY"],
  "related_skills": ["mi_saas"],
  "docs_url": "https://…",
  "default_scope": "tenant"
}
```

2. **Bridge** — en el skill Python, leer clave con:

```python
from duckclaw.integration_secrets import resolve_integration_api_key
key = resolve_integration_api_key("mi_saas", db=db, tenant_id=tenant_id)
```

3. **Skill registry** — pasar `db` / `tenant_id` en `skill_tool_registry` si aplica.

4. **Tests** — `tests/test_integration_catalog.py` + test del bridge.

5. **Reiniciar gateway** — el pack se cachea al arranque (`lru_cache`); tras cambiar JSON en dev, reinicia PM2.

La UI **Integraciones → API keys** muestra la nueva fila automáticamente.

## API / UI

- `GET/PATCH /api/v1/admin/settings/runtime` con `domain=integrations`
- Admin: `/integraciones?tab=keys`

## Runtime

Módulo: `duckclaw.integration_secrets.resolve_integration_api_key`

Bridges que consumen:

- `research_bridge` (Tavily)
- `openweather_bridge` (OpenWeather + contexto Tavily opcional)
- `higgsfield_env` / `fal_env`

## Skills custom (futuro)

Secrets por skill: `domain=skill_secret`, `key={skill_name}.api_key` — fuera de este corte.

## Acceptance

1. Admin guarda Tavily en Integraciones → Playground deja de mostrar gap research/Tavily.
2. GET runtime lista `configured=true` sin valor en claro.
3. Sin valor DB, `TAVILY_API_KEY` en `.env` sigue funcionando.
