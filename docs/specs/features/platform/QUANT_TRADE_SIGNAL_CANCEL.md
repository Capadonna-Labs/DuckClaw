# Quant-Trader · cancel_trade_signal

## Objetivo

Permitir que el worker **Quant-Trader** cancele señales en el ledger HITL desde el chat (admin playground, Telegram vía grafo), sin depender del fly command `/cancel_signal`.

## Tool

| Campo | Valor |
|-------|--------|
| Nombre | `cancel_trade_signal` |
| Args | `signal_id` (str, requerido), `reason` (str, opcional), `force` (bool, default false) |
| Worker | Quant-Trader (`quant_trader_bridge`) |
| Escritura | `_vault_apply_sql_statements` → cola Redis db-writer si vault `read_only` |

## Resolución de `signal_id`

1. **UUID completo** (`8-4-4-4-12` hex): uso directo.
2. **Prefijo** (≥4 caracteres hex tras normalizar): `LIKE '{prefix}%'` en `finance_worker.trade_signals` y `quant_core.trade_signals`.
   - 0 coincidencias → error.
   - 1 coincidencia → UUID resuelto.
   - >1 → error listando hasta 8 candidatos.

El fly command `/cancel_signal` sigue exigiendo UUID completo (sin prefijo).

## Estados cancelables

| Modo | Estados permitidos (pre-check) |
|------|--------------------------------|
| Normal (`force=false`) | `PENDING_HITL`, `AWAITING_HITL`, `PENDING`, `FAILED` |
| `force=true` | Cualquiera excepto `EXECUTED` |

- Ya `CANCELLED`: idempotente (`status=ok`, sin re-encolar escritura).
- `EXECUTED`: rechazo (también con `force=true`).

## SQL

Misma semántica que [FLY_COMMANDS_UI.md](./FLY_COMMANDS_UI.md) G1:

```sql
UPDATE finance_worker.trade_signals SET status='CANCELLED' WHERE …
UPDATE quant_core.trade_signals SET status='CANCELLED', updated_at=now() WHERE …
```

No hay columnas `cancellation_reason` / `cancelled_at` en el schema actual; `reason` solo aparece en el JSON de respuesta de la tool.

## Respuesta tool (JSON)

```json
{
  "status": "ok",
  "signal_id": "<uuid>",
  "previous_status": "PENDING_HITL",
  "new_status": "CANCELLED",
  "reason": "…",
  "message": "Señal cancelada"
}
```

Errores: `status=error`, `message` descriptivo.

## Prompt (Caveman)

Tras cancelar exitosamente:

```
Señal: CANCELLED
ID: <signal_id>
Razón: …
```

**Prohibido** inventar `/execute_signal --action cancel` (no existe). Usar `cancel_trade_signal` o `/cancel_signal` en Telegram.

## Tests

- `tests/test_cancel_signal_fly.py` — fly command (UUID completo).
- `tests/test_cancel_trade_signal_tool.py` — tool + prefijo UUID.

## Referencias

- Fly equivalente: `/cancel_signal` en [FLY_COMMANDS_UI.md](./FLY_COMMANDS_UI.md) G1
- Átomo: `packages/agents/src/duckclaw/forge/atoms/trade_signal_cancel.py`
