# Forge Projects — agrupación lógica

**Estado:** legacy filesystem. El modelo canónico para proyectos operativos es DB-first (`admin_projects`, `admin_project_agents`) y está documentado en [`ADMIN_IDENTITY_RBAC_ERD.md`](ADMIN_IDENTITY_RBAC_ERD.md). Esta spec se conserva sólo para compatibilidad con carpetas locales `forge/projects/` y variables `DUCKCLAW_TEAM_*`.

## Objetivo

Agrupar workers y contexto compartido sin datos del operador en el repositorio.

## Equipo en `.env`

| Variable | Descripción |
|----------|-------------|
| `DUCKCLAW_TEAM_MEMBERS` | Ids de carpeta en `forge/templates/` (CSV) |
| `DUCKCLAW_TEAM_COORDINATOR` | Id del coordinador (opcional) |
| `DUCKCLAW_TEAM_DISPLAY_NAME` | Etiqueta en admin (opcional) |
| `DUCKCLAW_TEAM_ID` | Slug de `forge/projects/` (default `team`) |
| `DUCKCLAW_TEAM_VAULT_ID` | Bóveda compartida (opcional) |
| `DUCKCLAW_TEAM_SHARED_CONTEXT_FILE` | Ruta a markdown local |
| `DUCKCLAW_TEAM_SHARED_CONTEXT` | Texto inline (alternativa) |

**Runtime:** el gateway **no** debe depender de `project.yaml` en disco. El flujo nuevo usa proyectos DB-first en DuckDB; las carpetas bajo `forge/projects/` son metadata local opcional o import material para migraciones.

## Disco (gitignored)

`forge/projects/<slug>/project.yaml` + `_shared/context.md`

## API admin

Legacy: rutas `/api/v1/admin/forge-projects*` y BFF `/api/admin/forge-projects*`.

Nuevo contrato: `/api/v1/admin/workspace/projects*`, con asignación relacional de agentes sin duplicar datos del worker.

## Ejemplo de contexto compartido

`packages/agents/src/duckclaw/forge/projects/_examples/team_shared_context.md.example`
