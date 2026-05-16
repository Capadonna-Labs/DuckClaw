# AXIS — Templates ADF (resumen)

**Estado:** implementado en disco como `packages/agents/src/duckclaw/forge/templates/AXIS-{Coder,Mirror,Radar,Sentinel,Phantom,Maestro}/`.

## Convención de nombres

| `agent_id` (manifest + validador) | Carpeta en repo |
|-----------------------------------|----------------|
| `coder` | `AXIS-Coder` |
| `mirror` | `AXIS-Mirror` |
| `radar` | `AXIS-Radar` |
| `sentinel` | `AXIS-Sentinel` |
| `phantom` | `AXIS-Phantom` |
| `maestro` | `AXIS-Maestro` |

El validador (`adf_validator.py`) resuelve ambas formas vía `resolve_axis_adf_path()`.

## Archivos ADF (7 por agente)

`manifest.yaml`, `system_prompt.md`, `schema.sql`, `security_policy.yaml`, `domain_closure.md`, `homeostasis.yaml`, `AGENT_OVERVIEW.md`

## Specs relacionadas

- `specs/05_ADF_AGENT_DEFINITION_FRAMEWORK.md` — marco ADF
- `docs/archive/AXIS_TEMPLATES_IMPLEMENTATION_PROMPT.md` — prompt histórico de implementación Cursor (no normativo)

## Verificación

```bash
uv run python packages/agents/src/duckclaw/adf_validator.py
```
