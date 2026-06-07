# Legacy Retirement DB-first

## Objetivo

Retirar de la operación normal de DuckClaw Admin los flujos legacy basados en filesystem y `.env` que ya tienen reemplazo DB-first. El sistema debe usar DuckDB como fuente de verdad para usuarios, workers, proyectos, contextos, skills y runtime settings.

## Fuera de Retiro Inmediato

Estos elementos se conservan como fallback temporal:

- `.env` para bootstrap de `DUCKCLAW_ADMIN_API_KEY`, credenciales iniciales y API keys secretas.
- Lectura de templates filesystem solo para importación hacia `admin_worker_catalog`.
- Documentación bajo `specs/features/DOCS-DEPRECATED/`.
- Hashes PBKDF2 legacy hasta migración transparente de contraseñas.

## Retiro Inmediato

### Forge Projects filesystem

Las rutas y UI de `forge-projects` dejan de ser flujo operativo de consola. Los proyectos activos se crean y administran con:

- `main.admin_projects`
- `main.admin_project_agents`
- `main.admin_worker_catalog`
- `main.admin_worker_versions`

El wizard `/projects/new` y endpoints `/forge-projects*` deben redirigir o responder `410 Gone` con instrucciones hacia Proyectos DB-first / Platform Orchestrator.

### Team templates legacy

`DUCKCLAW_TEAM_*` y `team_templates` no deben alimentar selectores de Admin. Pueden seguir existiendo para compatibilidad Telegram mientras se migra `/workers` a proyectos DB-first.

### Templates filesystem operativos

La consola no debe crear, editar, desactivar ni asignar templates directamente desde carpetas. La operación permitida es importar al catálogo DB-first y luego operar sobre filas de DuckDB.

### `.env` editable desde Admin

La edición genérica de `.env` desde la UI/API Admin queda deshabilitada. La configuración visible va a Runtime Settings; secretos van a Secret Settings.

### LLM legacy scope

La UI no debe presentar `scope="legacy"` como estado normal. La resolución debe preferir:

1. Runtime Settings DB-first.
2. Override explícito de chat si todavía existe.
3. `.env` como bootstrap/fallback, etiquetado como `env_bootstrap`.

## Criterios de Aceptación

- `/api/v1/admin/forge-projects*` responde `410 Gone` o una ruta DB-first equivalente.
- Admin UI no enlaza a `/projects/new` como flujo recomendado.
- Playground workers salen del catálogo DB-first; no de templates filesystem ni `admin_user_agents`.
- Rutas de creación filesystem de templates no se usan desde UI normal.
- `/api/v1/admin/env` deja de modificar `.env` de forma genérica.
- Tests cubren rechazo de flujos legacy y preservación de fallbacks de bootstrap.
