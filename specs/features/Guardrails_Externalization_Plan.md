# Plan: externalización de guardrails y textos hardcodeados

## Problema

Prompts, directivas de turno (`[DIRECTIVA_*]`) y mensajes de error al usuario viven como strings multilínea en módulos grandes (`workers/factory.py` ~5k líneas, `graphs/manager_graph.py` ~2.7k). Eso dificulta revisión, i18n, tests de copy y alineación con specs.

## Estrategia adoptada (fase 1 — hecho)

```
packages/agents/src/duckclaw/guardrails/
  loader.py              # load_guardrail("directives", "quant_autoexec")
  prompts/               # task awareness, saludos
  directives/            # SystemMessage por turno / worker
  errors/                # mensajes LLM failure (plantillas {detail})
```

Uso:

```python
from duckclaw.guardrails.loader import load_guardrail

SystemMessage(content=load_guardrail("directives", "reddit_share_exhausted"))
```

**Reglas:**

1. Código solo elige *cuándo* inyectar; el *texto* vive en `.md`.
2. Nombres de archivo = snake_case del tag (sin `[DIRECTIVA_]`).
3. Plantillas con `{detail}` documentadas en el `.md`; `.format()` en Python.
4. `@lru_cache` en `load_guardrail` para no releer disco en cada turno.

## Inventario por módulo (pendiente de migrar)

| Módulo | Tipo | Ejemplos | Prioridad |
|--------|------|----------|-----------|
| `workers/factory.py` | prompts, directives, errors | task_awareness, DIRECTIVA_*, llm_failure | **Migrado (fase 1)** |
| `graphs/manager_graph.py` | `_plan_task` TAREA strings, `_FINANZ_TOOL_PRESSURE_TASK`, capability blurbs | Finanz, Quant HRP, JobHunter, Leila | Alta |
| `graphs/on_the_fly_commands.py` | respuestas fly /help | miles de líneas | Media (por comando) |
| `forge/atoms/validators.py` | FACT_CHECKER_PROMPT | auditoría | Media |
| `forge/atoms/user_reply_nl_synthesis.py` | frases de sustitución NL | Finanz cuentas | Media |
| `graphs/general_graph.py`, `retail_graph.py`, `telegram_bot.py` | system prompts default | retail/general | Baja (migrar a `forge/templates/`) |
| `graphs/dreamer_job.py` | CONSOLIDATION_PROMPT | memoria | Baja |

## Fase 2 — manager_graph (completada)

1. `guardrails/manager_tasks/` — 17 tareas de `_plan_task`, handoff A2A y síntesis Finanz.
2. `guardrails/capabilities/` — blurbs de presentación por worker (`_worker_capability_blurb`).
3. `format_guardrail(*parts, **kwargs)` en `loader.py` para plantillas con `{table_name}`, `{context}`, etc.
4. `manager_graph.py` sin bloques `TAREA:` inline en `_plan_task` ni capabilities.

## Fase 3 — fly commands, graphs y atoms (parcial)

- [x] `fly_commands/`: `/help`, `/ayuda`, `/roles`, hint `/workers`
- [x] `resilience/`: replan suffix + exhausted failure
- [x] `heartbeat/tool_steps.md`: mensajes por herramienta
- [x] `system_prompts/`: general, retail, dreamer consolidation
- [x] `validators/`: fact_checker, self_correction
- [ ] Resto de `on_the_fly_commands.py` (~7000 líneas): mensajes de error/uso por comando
- [ ] `user_reply_nl_synthesis.py`: sustituciones NL

## Fase 4 — i18n (opcional)

- Sufijo de locale: `directives/quant_autoexec.es.md`, `quant_autoexec.en.md`.
- Resolver con `DUCKCLAW_LOCALE` en `loader.py`.

## Tests

- `tests/test_guardrails_loader.py`: todos los `.md` referenciados existen.
- Snapshot opcional de longitud máxima por directiva (evitar TPM blow-up).

## Criterios de aceptación

- [x] Paquete `duckclaw.guardrails` con loader cacheado
- [x] factory.py sin strings de DIRECTIVA_* / task awareness / llm errors inline
- [x] manager_graph.py sin constantes TAREA > 3 líneas inline (`_plan_task` + capabilities)
- [ ] CI incluye `test_guardrails_loader.py`
