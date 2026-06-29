/**
 * LEGACY — Bot Telegram (core.integrations.telegram_bot). Secretos: .env (env_file).
 */
const path = require("path");
const root = path.resolve(__dirname, "..");
const { resolveRepoPython } = require("./ecosystem.runtime.cjs");
const python = resolveRepoPython(root);

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
