# ADF — Agent Definition Framework (v1.0.0)

Documento SDM mínimo para definiciones de agente AXIS en DuckClaw. La fuente normativa de plantillas y criterios de PR es la feature spec enlazada abajo; este archivo fija el contrato de archivos y validación.

## Alcance

Los **seis agentes AXIS** (CODER, MIRROR, RADAR, SENTINEL, PHANTOM, MAESTRO) tienen ADF bajo el paquete **forge** (la carpeta `forge/` no es un agente; es donde vive `templates/`):

```
packages/agents/src/duckclaw/forge/templates/<agent_id>/
```

Cada `<agent_id>` es uno de: `coder`, `mirror`, `radar`, `sentinel`, `phantom`, `maestro`.

En cada carpeta hay exactamente **siete archivos** (contrato ADF):

| Archivo | Rol |
|---------|-----|
| `manifest.yaml` | Identidad, fase, memoria, dependencias, eventos, referencias a otros archivos ADF |
| `system_prompt.md` | Instrucciones LLM con secciones obligatorias (ver validador) |
| `schema.sql` | Tablas DuckDB/Silver; prefijo `\<agent_id\>_` o tablas `gold_*` acordadas |
| `security_policy.yaml` | `can_do` / `cannot_do`; `data_egress` recomendado |
| `domain_closure.md` | Límites de dominio y reglas de escalación a otros agentes |
| `homeostasis.yaml` | Reglas de autogestión / anomalías declarativas |
| `README.md` | Documentación humana del agente |

## Validación

- Script: [`packages/agents/src/duckclaw/adf_validator.py`](../packages/agents/src/duckclaw/adf_validator.py)
- Uso desde la raíz del monorepo: `uv run python packages/agents/src/duckclaw/adf_validator.py .`
- El campo `agent_id` del manifest debe coincidir con el nombre de carpeta **`<agent_id>`** bajo `forge/templates/`.

## Referencias

- Plantillas y contenido por agente: [`specs/features/AXIS_TEMPLATES_001.md`](features/AXIS_TEMPLATES_001.md)
- Marco conceptual workers/memoria: [`docs/agents/adf_framework.md`](../docs/agents/adf_framework.md)

## Versión

**PLAN ADF v1.0.0** — alineado con SPEC-01 v0.2.0 (secciones §6.x de agentes AXIS).
