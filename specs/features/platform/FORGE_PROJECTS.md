# Forge Projects — agrupación lógica

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

**Runtime:** el gateway **no** depende de `project.yaml` en disco; solo de env + DuckDB (`/workers`, tenant). Las carpetas bajo `forge/projects/` son metadata local opcional para la consola admin.

## Disco (gitignored)

`forge/projects/<slug>/project.yaml` + `_shared/context.md`

## API admin

Ver rutas `/api/v1/admin/forge-projects*` y BFF `/api/admin/forge-projects*`.

## Ejemplo de contexto compartido

`packages/agents/src/duckclaw/forge/projects/_examples/team_shared_context.md.example`
