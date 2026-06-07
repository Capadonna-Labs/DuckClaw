# Admin Console — User Agent Workspaces

Versión: 1.0 · Fecha: 2026-05-30

## Objetivo

Cada usuario autenticado en `apps/duckclaw-admin` debe operar en un tenant propio, configurar sus canales de comunicación y crear agentes aislados sin modificar los templates globales del repositorio.

Relacionado: [`ADMIN_CONSOLE_AUTH.md`](ADMIN_CONSOLE_AUTH.md), [`ADMIN_ACCESS_MANAGEMENT.md`](ADMIN_ACCESS_MANAGEMENT.md).

## Identidad y Tenant

- `main.admin_console_users` sigue siendo la fuente de credenciales y rol.
- `main.admin_user_profiles` define el perfil operativo:
  - `email` como clave primaria.
  - `tenant_id` único por usuario.
  - `telegram_user_id` opcional.
  - `channels_json` para canales configurables.
  - `default_worker_id` para el agente default del usuario.
- El tenant se genera de forma estable desde el email normalizado si no existe perfil previo.

## Agentes Runtime

- Los templates del repo son catálogo semilla y no deben modificarse por usuarios normales.
- `main.admin_user_agents` indexa agentes creados por usuario:
  - `tenant_id`
  - `owner_email`
  - `worker_id`
  - `display_name`
  - `source_template_id`
  - `manifest_path`
  - `active`
- Cada agente runtime también debe registrar su identidad actual en `main.admin_worker_catalog` y una versión inicial en `main.admin_worker_versions`.
  Así `/templates`, el selector de workers y los proyectos DB-first leen el mismo catálogo visible por tenant.
- `active=false` / `status='inactive'` en `main.admin_worker_catalog` es soft-delete: por defecto no aparece en Workers, selectores ni Playground.
  La consola admin puede pedir `GET /templates?include_inactive=true` para auditoría y usar `POST /templates/{worker_id}/reactivate` para restaurar un worker owned por el actor sin tocar snapshots ni carpetas.
- Cada perfil debe tener un worker DB-first permanente `platform-orchestrator` (`Platform Orchestrator`) para guiar creación de proyectos, workers, contexto y skills. Ver [`PLATFORM_ORCHESTRATOR_WORKER.md`](PLATFORM_ORCHESTRATOR_WORKER.md).
- Los manifiestos runtime se guardan fuera del árbol de templates globales, por defecto en `.duckclaw/runtime/agents/{tenant_id}/{worker_id}/manifest.json`.

## Contexto de Sesión

- El BFF deriva `X-Duckclaw-Actor` desde la sesión Redis.
- El gateway resuelve `tenant_id`, `telegram_user_id` y `default_worker_id` desde `admin_user_profiles`.
- Parámetros del browser como `tenant_id` o `telegram_user_id` no pueden suplantar otro usuario cuando hay actor de consola.

## Criterios de Aceptación

- Usuario nuevo recibe perfil con tenant único y agente default.
- Usuario A no ve agentes runtime de Usuario B.
- Crear agente como usuario normal no escribe en `packages/agents/src/duckclaw/forge/templates`.
- `/playground/config` expone el catálogo del usuario logueado y su tenant efectivo.
- Tests cubren auth, CSRF/RBAC, tenant único, aislamiento de agentes y no suplantación de tenant/Telegram.
