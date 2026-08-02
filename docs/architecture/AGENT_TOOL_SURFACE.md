# Agent tool surface (SOTA)

Contrato de diseño para tools del worker (LangChain `StructuredTool` / Forge bridges).
Referencias: Anthropic [Tool Search / `defer_loading`](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)
(always-load 3–5), OpenAI function calling (menos de ~20 tools al inicio del turno),
Google Gemini (active set 10–20 + selección dinámica).

## Principios (N agentes × N MCP)

1. **Description = contrato de selección.** Qué / cuándo / NO / qué devuelve.
2. **Progressive disclosure.** Always-on pequeño (`core`); dominios y MCP bajo demanda.
3. **Namespacing MCP obligatorio.** `mcp__{connector_id}__{tool}` (conectores DB-first y skill GitHub).
4. **Orphans excluidos por defecto.** Si una tool no está en un pack, no entra al bind (`orphan_policy: exclude`).
5. **Sin hardcode por agente.** El catálogo es YAML; cada worker solo override vía `tool_surface.runtime_packs`.
6. **Read vs write.** Mutaciones con policy / HITL; lecturas auto.
7. **No God tools.** Átomos por dominio (reports, knowledge, mcp, …).

## Runtime tool packs

| Pieza | Rol |
|-------|-----|
| `workers/data/runtime_tool_packs.yaml` | Catálogo default (packs, membership, señales, `max_bound_tools`) |
| `tool_pack_catalog.py` | Load + merge manifest |
| `tool_pack_policy.py` | Activos = always ∪ señales ∪ sticky ∪ unlock ∪ **connector id en intent** |
| `tool_pack_bridge.py` | `list_tool_packs` / `unlock_tool_pack` |
| `factory_graph_nodes_agent_invoke.py` | Filtro en bind `auto` + log |

### Packs default

| Pack | Always | Membership |
|------|--------|------------|
| `core` | sí | contexto, SQL lectura, discovery |
| `mcp` | no | Umbrella (sin members); unlock expande a `mcp_*` |
| `mcp_{connector}` | no (dinámico) | Prefijo `mcp__{connector}__` |
| `knowledge` | no | RAG + disco |
| `reports` | no | Report Engine |
| `docs_output` | no | OUTPUT / PDF ad-hoc |
| `research` | no | web / kiwix |
| `prompt_meta` | no | system prompt |
| `visual` | no | Comfy / Fal / … |
| `sandbox` | no | Strix / browser |
| `integrations` | no | reddit / weather / … |

Activación MCP multi-agente:
- Packs dinámicos `mcp_{connector_id}` (prefijo `mcp__{id}__`) derivados de tools registradas.
- Intent con el id del conector como **token** (word-boundary; citar `mcp_github` no activa GitHub).
- `unlock_tool_pack('mcp')` (umbrella) → todos los conectores del worker.
- `unlock_tool_pack('mcp_github')` → un conector.
- Métrica por turno (log `runtime_tool_packs_metric`): `active_packs`, `bound_count`,
  `hidden`, `truncated`, `connector_ids`.

### Override por worker (sin tocar código)

```yaml
tool_surface:
  runtime_packs:
    enabled: true
    orphan_policy: exclude
    max_bound_tools: 16
    pack_overrides:
      mcp:
        activation_signals: [mcp, github, notion, slack]
    extra_always: []   # p.ej. [knowledge] para un agente solo-RAG
```

## Gaps restantes

| Pri | Gap |
|-----|-----|
| P0 | Exponer `tools_bound` / `harness_metric` en admin Overview |
| P1 | ArgsSchema / Field descriptions homogéneos |
| P1 | Envelope en **todos** los bridges (harness ya normaliza fallos en `tools_node`) |
| P1 | HITL real `PENDING_HITL` para destructive (hoy: gate in-graph `suggest`/`never`) |
| P2 | Verify-loop post-sandbox |
| P3 | Provider Tool Search nativo |

Harness de ejecución: ver [`AGENT_HARNESS_CONTROL.md`](./AGENT_HARNESS_CONTROL.md).

## Dual-lane conocimiento

- RAG: `search/list/read_project_knowledge`
- Disco: `list_disk_*` / `read_disk_text` / `extract_document_text`
