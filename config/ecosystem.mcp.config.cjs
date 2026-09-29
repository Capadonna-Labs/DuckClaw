/**
 * PM2 — DuckClaw MCP (streamable HTTP). Puerto: DUCKCLAW_MCP_PORT en .env (default 8001).
 *
 *   pm2 start config/ecosystem.mcp.config.cjs
 *   pm2 restart DuckClaw-MCP --update-env
 */
const path = require("path");

const root = path.resolve(__dirname, "..");

module.exports = {
  apps: [
    {
      name: "DuckClaw-MCP",
      script: "uv",
      args: "run python -m duckclaw_mcp --host 0.0.0.0",
      cwd: root,
      env_file: path.join(root, ".env"),
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      // Telegram user account (Telethon). Opt-in: needs TELEGRAM_API_ID/HASH and a
      // prior `uv run python -m duckclaw_telegram_mcp.user login`. Binds 127.0.0.1.
      //   pm2 start config/ecosystem.mcp.config.cjs --only DuckClaw-Telegram-User-MCP
      name: "DuckClaw-Telegram-User-MCP",
      script: "uv",
      args: "run python -m duckclaw_telegram_mcp.user",
      cwd: root,
      env_file: path.join(root, ".env"),
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_restarts: 10,
      restart_delay: 5000,
    },
  ],
};
