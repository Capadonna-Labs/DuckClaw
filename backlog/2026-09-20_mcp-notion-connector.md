# Backlog — MCP Connector de Notion

**Fecha**: 2026-09-20 (sábado)
**Solicitado por**: Juan
**Estado**: AGENDADO (pendiente de priorización)

## Objetivo
Crear un conector MCP de Notion para que los workers (quant_analyst, quant_trader, quant_reporter) puedan consultar/escribir en el workspace `Juan Arevalo's Notion` desde el chat, similar al conector `mcp__google_gmail__*` ya existente.

## Contexto verificado (2026-09-20)
- El workspace Notion `Juan Arevalo's Notion` está conectado a nivel de usuario (páginas revisadas: `DuckClaw - Proyecto`, `Capadonna Driller - Proyecto`, `DuckClaw - Proyecto (arquitectura de referencia)`).
- **No existe** conector MCP de Notion en el codebase:
  - `packages/mcp/` solo tiene `duckclaw` y `telegram`.
  - `integrations/` tiene `edge-devices`, `pipecat-voice`, `sensory-node` — sin Notion.
  - `tool_packs` está desactivado en tool_surface (todo always-loaded) → no hay pack oculto que desbloquear.
- La conexión actual de Notion es vía API key/config en el Gateway o integración OAuth del Admin UI, no expuesta como tool para workers.

## Alcance técnico propuesto
1. Crear MCP Server de Notion en `packages/mcp/` (patrón: `mcp__google_gmail__*`).
2. Endpoints mínimos:
   - `notion_search` (búsqueda de páginas/bases de datos)
   - `notion_get_page` (leer contenido de página)
   - `notion_create_page` (crear página)
   - `notion_update_page` (actualizar propiedades/contenido)
3. Config: API token de integración Notion (Internal Integration) + page ID raíz permitida.
4. Registrar en el tool surface del worker para que quede always-loaded.

## Dependencias
- Acceso al repo `/root/duckclaw` (prod) o repo local de desarrollo.
- Token de integración Notion (crear en https://www.notion.so/my-integrations).
- Revisión humana antes de deploy (aislamiento intencional del sandbox).

## Notas
- No confundir con la conexión OAuth del Admin UI (frontend) — esto es para workers.
- La API de Notion soporta búsqueda, páginas, bases de datos y comentarios; el conector mínimo cubre búsqueda + lectura/escritura de páginas.
