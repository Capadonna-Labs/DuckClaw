# Proactividad por alineación de /crons

> Complementa [FLY_COMMANDS_UI.md](FLY_COMMANDS_UI.md) (programación `/crons`) y [HOMEOSTASIS_HEARTBEAT.md](HOMEOSTASIS_HEARTBEAT.md) (ticker del daemon).

## Objetivo

Detectar cuando el **contexto observable** (PnL de sesión, drawdown, etc.) está **desalineado** con los objetivos del chat (`/crons`), y hacer que el agente **escriba proactivamente** al usuario con tono humano y propuestas concretas. La medición debe estar disponible:

1. En **ticks programados** (`/crons --delta`, heartbeat).
2. En **turnos normales** vía herramienta `assess_crons_alignment`.

## Herramienta: `assess_crons_alignment`

| Campo | Valor |
|-------|--------|
| Entrada | Sin parámetros (usa `chat_id` y bóveda del contexto de sesión) |
| Salida | JSON (`AlignmentReport`) |

```json
{
  "aligned": false,
  "misaligned_count": 1,
  "items": [
    {
      "belief_key": "max_portfolio_drawdown_pct",
      "title": "DD máximo 10%",
      "target": 0.1,
      "observed": 0.12,
      "threshold": 0.01,
      "delta": 0.02,
      "is_anomaly": true,
      "has_data": true
    }
  ],
  "goals_count": 2,
  "opener_hint": "Detecté que el drawdown supera el límite que fijaste en /crons."
}
```

- `aligned`: `true` solo si todos los goals con datos suficientes tienen `is_anomaly=false`.
- Goals sin `observed` tras `refresh_goal_observations` no cuentan como anomalía pero aparecen con `has_data=false`.

## Módulo atómico

`packages/agents/src/duckclaw/forge/homeostasis/goals_alignment.py`

- `refresh_goal_observations(db, chat_id, worker_id)` — actualiza `observed_value` en goals sin LLM.
- `assess_goals_alignment(db, chat_id, *, worker_id)` — evalúa sorpresa por goal.
- `pick_nudge_opener(chat_id, epoch)` — variante de apertura en español.
- `build_alignment_nudge_system_event(report, *, trading_objective)` — SYSTEM_EVENT con marca `Revisión de alineación con /crons`.

## Claves `chat_state`

| Clave | Uso |
|-------|-----|
| `goals_proactive_notify_channel` | `admin` \| `telegram` \| `both` (default env `DUCKCLAW_GOALS_ALIGNMENT_DEFAULT_NOTIFY`) |
| `goals_delta_meta.mode` | `always` \| `on_misalignment` (default `on_misalignment`) |
| `goals_delta_meta.jitter_ratio` | 0.0–0.5 (default 0.15) |

## Flags `/crons`

```
/crons --delta 20min [--notify admin|telegram|both] [--mode always|on_misalignment] [--jitter 20%]
```

`/crons --delta off` limpia también `goals_proactive_notify_channel`.

## Heartbeat

En `_run_goals_proactive_tick_one_db`:

1. `refresh_goal_observations` + `assess_goals_alignment`.
2. Si `mode=on_misalignment` y `aligned` → no POST (solo persistir observed).
3. Jitter en ventana `delta_s * (1 ± jitter_ratio * U(0,1))`.
4. Mensaje: nudge si desalineado; si `mode=always` y alineado → mensaje periódico legado.
5. Payload incluye `notify_channel` para el gateway.

Cooldown Redis: `cooldown:{tenant}:{chat_id}:alignment_nudge`, TTL `min(delta_s, 14400)`.

## Entrega (gateway)

Tras invoke con `is_system_prompt` y respuesta no vacía:

- **admin / both** + sesión `admin-conv-*` → persistir historial Redis + meta conversación.
- **telegram / both** + chat numérico → `deliver_outbound`.

## Criterios de aceptación

1. `/crons --delta 5min --notify admin --mode on_misalignment` con goal en anomalía dispara mensaje visible en playground admin.
2. Con todo alineado y `on_misalignment`, el ticker no invoca el grafo.
3. `assess_crons_alignment` en turno Quant devuelve JSON coherente con listado `/crons`.
4. Variantes de opener distintas entre ticks (seed por chat_id + epoch).

## Variables de entorno

- `DUCKCLAW_GOALS_ALIGNMENT_DEFAULT_MODE=on_misalignment`
- `DUCKCLAW_GOALS_ALIGNMENT_DEFAULT_NOTIFY=both`
- `DUCKCLAW_GOALS_ALIGNMENT_JITTER=0.15`
