# Quant Trader Agent

`quant_trader` handles quantitative market workflows and strategy-oriented analysis.

## Scope

- Market context synthesis and signal-oriented reasoning.
- Quant-specific skills integrated via worker factory registration.
- Coordinated handoff/routing from manager when quant intent is detected.

## Integration Notes

- Telegram multiplex routing uses `bot_name=quanttrader` and `worker_id=quant_trader`.
- Session IDs are namespaced by bot in multiplex mode to avoid cross-bot context collisions.
- Quant flows must still honor global zero-trust and evidence constraints.
