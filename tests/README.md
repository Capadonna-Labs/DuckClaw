# Tests

```bash
uv run pytest tests/ -v -m "not integration"
```

## Variables (`.env`)

| Variable | Uso |
|----------|-----|
| `DUCKCLAW_OWNER_ID` / `DUCKCLAW_ADMIN_CHAT_ID` | Bypass gateway / tests que requieren owner |
| `DUCKCLAW_TEST_TELEGRAM_USER_ID` | ID Telegram en tests unitarios (opcional) |

Sin ellas, muchos tests usan `999000001` vía [`env_ids.py`](env_ids.py).

## Marcadores

| Marcador | Cuándo |
|----------|--------|
| `integration` | Redis + pipeline completo (`run_singleton_writer_pipeline.py`) |
| `slow` | DuckDB extensions / seed pesado |
| `requires_docker` | Smoke mercenario con imagen Strix |

## Smoke rápido

[`test_final.py`](test_final.py) — import core + gateway (complementa CI, no lo sustituye).
