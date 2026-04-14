# GitClaw Worker (soberano ADF)

## Objetivo

Worker declarativo **GitClaw** (`id: gitclaw`): experto en GitHub/Git para el tenant. Analiza repositorios, revisa código, gestiona issues y PRs, y apoya releases y automatización, integrado con el **GitHub MCP bridge** existente (`duckclaw.forge.skills.github_bridge`).

## Implementación (fuente de verdad)

- Directorio del template: `packages/agents/src/duckclaw/forge/templates/gitclaw/`
- Artefactos: `manifest.yaml`, `soul.md`, `system_prompt.md`, `domain_closure.md`, `security_policy.yaml`, `schema.sql`, `skills/search_semantic_context.py`

## Contrato runtime (`WorkerSpec`)

- `id: gitclaw`, `schema_name: gitclaw`, `read_only: false` (permite `admin_sql` acotado).
- `skills`: bloque `github` (token vía `GITHUB_TOKEN`, `hitl_destructive` para acciones destructivas del MCP) y `search_semantic_context` (VSS sobre `main.semantic_memory`).
- `allowed_tables`: `decisions`, `pr_log` (calificadas como `gitclaw.*` por el worker), `main.semantic_memory`.
- `security_policy.yaml`: política Strix válida (`SecurityPolicy` en `duckclaw.forge.schema`); sandbox sin red; GitHub fuera del contenedor vía MCP.

## Esquema DuckDB (`schema.sql`)

- Esquema `gitclaw`: tablas `decisions` (ADR / decisiones) y `pr_log` (seguimiento de PRs).

## Activación

- Descubrimiento: `list_workers()` incluye el nombre de carpeta `gitclaw`.
- Telegram / War Room: `/workers gitclaw` (coincidencia case-insensitive con el id de carpeta).

## Dependencias operativas

- `GITHUB_TOKEN` con permisos acordes al caso (repo, `read:org` si aplica).
- Paquete `mcp` y disponibilidad de `npx @modelcontextprotocol/server-github` en el proceso del gateway (ver consolidado en `specs/core/03_Skills_and_Tooling_Framework.md`).

## Criterios de aceptación

1. `load_manifest("gitclaw")` carga sin error y expone `github_config` no nulo.
2. `gitclaw` aparece en `GET /api/v1/agent/workers` (mismo inventario que `list_workers()`).
3. Prompts en capas (`soul` + `system` + `domain_closure`) y anti-alucinación de estado de repo sin tool calls en el turno actual.

## Relación con otras specs

- Marco de skills y GitHub MCP: `specs/core/03_Skills_and_Tooling_Framework.md`.
- Workers y factory: `specs/core/04_Cognitive_Agent_Logic.md` (plantillas bajo `forge/templates/<worker_id>/`).
