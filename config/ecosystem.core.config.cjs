/**
 * LEGACY — Bot Telegram (core.integrations.telegram_bot). Secretos: .env (env_file).
 * Regenerar manualmente o ignorar si no usas DuckClaw-Brain.
 */
const path = require("path");
const fs = require("fs");
const root = path.resolve(__dirname, "..");
const python = fs.existsSync(path.join(root, ".venv/bin/python3"))
  ? path.join(root, ".venv/bin/python3")
  : path.join(root, ".venv/bin/python");

module.exports = {
  apps: [
    {
      name: "DuckClaw-Brain",
      script: python,
      args: "-m core.integrations.telegram_bot",
      cwd: root,
      env_file: path.join(root, ".env"),
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_restarts: 10,
      env: {
        PYTHONPATH: root,
        DUCKCLAW_PM2_PROCESS_NAME: "DuckClaw-Brain",
      },
    },
  ],
};
