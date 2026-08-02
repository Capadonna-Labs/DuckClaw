# Agent tool surface (SOTA)

Contrato de diseño para tools del worker (LangChain `StructuredTool` / Forge bridges).
Referencias: Anthropic *Advanced tool use* (Tool Search / `defer_loading`, Tool Use Examples),
reglas de context engineering Claude 5 (progressive disclosure, descriptions en la tool),
y límites prácticos (~20–30 tools always-loaded antes de degradar selección).

## Principios

1. **Description = contrato de selección.** Cada tool declara: qué hace, cuándo usarla, qué NO hacer, qué devuelve. El system prompt no debe repetir catálogos enteros.
2. **Lanes explícitas.** Prefijos en copy (`[RAG indexado]`, `[Disco / raíces permitidas]`, `[DuckDB]`, …) para evitar confusión dual-lane.
3. **Errores accionables.** Preferir JSON `{ok:false, error, hint, retry}` frente a strings opacos.
4. **Surface acotada.** Mantener always-loaded bajo ~20 tools críticas; el resto via discovery (Tool Search / skill gating / MCP on-demand).
5. **Read vs write.** Lecturas auto-ejecutables; mutaciones (admin_sql, write_output, report patches, prompt updates) con policy / HITL cuando el riesgo lo exige.
6. **No God tools.** Preferir CRUD/átomos (report engine, knowledge) sobre un único “do_anything”.

## Surface actual (baseline factory)

Always-loaded típico (sin MCP ni skills extra):

| Lane | Tools |
|------|--------|
| Tiempo | `get_current_time` (si expuesto) |
| DuckDB | `read_sql`, `admin_sql` (condicional), `inspect_schema`, `get_db_path` |
| RAG | `get_project_context`, `search_project_knowledge`, `list_project_knowledge`, `read_project_knowledge` |
| Disco | `list_disk_roots`, `list_disk_folder`, `read_disk_text`, `extract_document_text` |
| Docs out | `write_output_document`, `render_docx_template`, `export_docx_to_pdf` |
| Offline web | `kiwix_*` (si disponible) |
| Meta | update system prompt tools |
| Report | Report Engine (varios átomos) |

Copy canónico: `packages/agents/.../knowledge_tool_copy.py`.
Registro disco: `disk_knowledge_bridge.register_disk_knowledge_tools`.

## Runtime tool packs (progressive disclosure)

Implementación DuckClaw (no depende del `defer_loading` del API de Claude):

| Pieza | Rol |
|-------|-----|
| `workers/data/runtime_tool_packs.yaml` | Catálogo: packs, membresía exact/prefix, señales de activación |
| `tool_pack_catalog.py` | Load + merge con `manifest.tool_surface.runtime_packs` |
| `tool_pack_policy.py` | Resolve packs activos + filtro (sticky / unlock / signals) |
| `tool_pack_bridge.py` | `list_tool_packs` / `unlock_tool_pack` |
| `factory_graph_nodes_agent_invoke.py` | Aplica filtro en bind `auto` + log `runtime_tool_packs …` |

Activación (unión): `always` ∪ señales del turno ∪ sticky (tools ya usadas tras el último human) ∪ `unlock_tool_pack`.
Overrides por worker sin tocar código: `tool_surface.runtime_packs` (`enabled`, `orphan_policy`, `pack_overrides`, `extra_packs`, …).
Gates previos (sandbox / `admin_sql` / `get_db_path`) se mantienen; packs no los reemplazan.

## Gaps SOTA (backlog ordenado)

| Prioridad | Gap | Por qué importa | Acción sugerida |
|-----------|-----|-----------------|-----------------|
| P0 | Métrica admin `tools_bound` / packs activos | El log del worker existe; falta UI | Exponer en Studio / health |
| P1 | `Field(description=…)` / schema estricto en todos los args | Param errors son el fallo #2 tras selection | ArgsSchema Pydantic en bridges |
| P1 | Errores estructurados homogéneos | El modelo reintenta mal con texto libre | Helper `_tool_error` compartido |
| P2 | Risk tiers + HITL writes | SOTA separa read auto / write confirm | Tags `risk` + confirm UI |
| P2 | Namespacing fuerte | Prefijos en description ayudan | Alias de compat al renombrar |
| P3 | Programmatic tool calling | Pipelines multi-step hinchan contexto | Sandbox code-exec (Strix) |
| P3 | Mid-conversation tool changes / provider Tool Search | Cache prefix vs tool set dinámico | Cuando el provider lo soporte de forma estable |

## Dual-lane (conocimiento)

- **En el chat (RAG):** indexado → `search_*` / `list_*` / `read_project_knowledge`.
- **En disco:** `ALLOWED_ROOTS` → `list_disk_*` / `read_disk_text` / `extract_document_text`.
- **No** indexar árboles enormes (p.ej. `~/Developer`) para “dar tools”; el disco ya es la lane correcta.

## Inventario

Snapshot de descriptions: `docs/superpowers/tool-descriptions-inventory.json` (regenerar al cambiar copy).
