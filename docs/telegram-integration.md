# Telegram Integration Guide (Third-Party Access)

This guide explains how to expose DuckClaw to a third party through Telegram using local polling and the built-in `TelegramBotBase`.

## Architecture

`TelegramBotBase` handles:
- table bootstrap (`telegram_messages`)
- automatic persistence of each incoming update
- optional app creation via `python-telegram-bot`

Flow:
1. Telegram sends an update to your bot.
2. `TelegramBotBase` persists the update into DuckClaw.
3. Your bot logic runs in `handle_message(update)`.

## 1) Create the Telegram bot token

1. Open Telegram and chat with **BotFather**.
2. Run `/newbot`.
3. Save the generated token.

Required environment variables:
- `TELEGRAM_BOT_TOKEN`
- `DUCKCLAW_DB_PATH` (optional, defaults to `db/gateway.duckdb`)

## 2) Install dependencies

From repo root:

```bash
pip install -e ".[telegram]" --no-build-isolation
```

If you prefer uv:

```bash
uv pip install -e ".[telegram]"
```

## 3) Run the bot locally (polling)

**Option A – Installer (wizard):** from repo root:

```bash
./scripts/install_duckclaw.sh
```

**Option B – Manual:** set env and run the sample:

```bash
export TELEGRAM_BOT_TOKEN="your_bot_token"
export DUCKCLAW_DB_PATH="telegram.duckdb"
python examples/telegram_bot.py
```

## 4) Validate persisted messages

```python
import duckclaw
db = duckclaw.DuckClaw("telegram.duckdb")
print(db.query("SELECT chat_id, username, text, received_at FROM telegram_messages ORDER BY received_at DESC LIMIT 20"))
```

## Troubleshooting

### Invalid token / Unauthorized
- Confirm token in `TELEGRAM_BOT_TOKEN`.
- Regenerate token in BotFather if needed.

### Missing optional dependency
- Error: `Telegram integration requires optional dependency python-telegram-bot`
- Fix:
  ```bash
  pip install -e ".[telegram]" --no-build-isolation
  ```

### `telegram_messages` table not created
- Ensure bot receives at least one message.
- Confirm you are opening the same DB file from `DUCKCLAW_DB_PATH`.

### Editable install errors (`No module named pip`)
- Use:
  ```bash
  pip install -e ".[telegram]" --no-build-isolation
  ```
  and install build deps in your venv if needed.

## Which DB is used when you ask from Telegram (Gateway)

**One** .duckdb is used for the full flow: Telegram → DuckClaw-Gateway → agent SQL → response in Telegram. When you analyze the DB later (scripts or SQL), it is the same file.

- **Path:** `DUCKCLAW_DB_PATH` if set (e.g. in `.env` or pm2), otherwise **`db/gateway.duckdb`**.
- **Contents:** main (`api_conversation`, `agent_config`), finance_worker (`transactions`, `categories`, `cuentas`, `presupuestos`, `deudas`, `agent_beliefs`), etc.

**To analyze the same DB:** Run scripts from the repo root; they load `.env` and use the same path as the Gateway. Or set `DUCKCLAW_DB_PATH` to match the Gateway process.

- Which file: `python3 scripts/where_gateway_writes.py`
- Inspect: `python3 scripts/inspect_telegram_db.py` or `python3 scripts/validate_cuentas_gateway.py` (no argument = Gateway path; or pass path as first argument)

**To recreate the DB from scratch:** `python3 scripts/recreate_gateway_db.py`. The current file is renamed to `{path}.bak.{timestamp}` and a new DB is created with the full schema (main + finance_worker).
