# Plan: Runtime tool packs (progressive disclosure)

## Goal

Bound ≤ ~20 tools per auto-bind turn via declarative packs (YAML + manifest overrides), not hardcoded filters in the factory.

## Layers

| Layer | Responsibility |
|-------|----------------|
| `data/runtime_tool_packs.yaml` | Pack IDs, membership (exact/prefix), activation signals, always flags |
| `tool_pack_catalog.py` | Load/merge catalog (default YAML ∪ manifest `tool_surface.runtime_packs`) |
| `tool_pack_policy.py` | Pure: resolve active packs, sticky/unlock from messages, filter tools |
| `tool_pack_bridge.py` | Meta-tools `list_tool_packs` / `unlock_tool_pack` |
| `factory_tool_builder.py` | Register meta-tools only |
| `factory_graph_nodes_agent_invoke.py` | Apply filter on `forced_name == "auto"` + log metrics |
| Existing policies | Keep sandbox / admin_sql / get_db_path gates (packs do not replace them) |

## Manifest contract

```yaml
tool_surface:
  runtime_packs:
    enabled: true
    orphan_policy: include   # tools outside catalog stay visible
    max_bound_tools: 28
    disabled_packs: []
    extra_always: []
    pack_overrides: {}       # per-pack activation_signals / always
```

## Activation sources (union)

1. Packs with `always: true`
2. Intent text matching pack `activation_signals`
3. Sticky: pack of any tool used after last human message
4. Unlock: successful `unlock_tool_pack` ToolMessage this turn

## Tests

- Catalog loads; membership by prefix
- Filter hides reports when intent is knowledge-only
- Sticky keeps reports after `patch_report_section` ToolMessage
- Manifest `enabled: false` is no-op
- Unlock parses ToolMessage content
