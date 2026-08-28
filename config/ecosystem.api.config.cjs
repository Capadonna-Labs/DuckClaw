/**
 * PM2 — API Gateways DuckClaw (generado). Secretos: solo .env (env_file).
 * Regenerar: uv run duckops serve --pm2 --gateway
 * pm2 start config/ecosystem.api.config.cjs --only "NombreGateway"
 */
const path = require("path");
const fs = require("fs");
const root = path.resolve(__dirname, "..");
const { resolveRepoPython } = require("./ecosystem.runtime.cjs");
const python = resolveRepoPython(root);
module.exports = {
  apps: [
    {
      name: "DuckClaw-Gateway",
      script: python,
      args: "services/api-gateway/uvicorn_pm2.py main:app --host 0.0.0.0 --port 8000 --app-dir services/api-gateway",
      cwd: root,
      env_file: path.join(root, ".env"),
      interpreter: "none",
      autorestart: true,
      watch: false,
      windowsHide: true,
      max_restarts: 10,
      filter_env: [
        /^npm_/,
        /^NEXT_/,
        /^PNPM_/,
        /^__NEXT_/,
        "NODE_OPTIONS",
        "NODE_ENV",
        "PORT",
        "INIT_CWD",
      ],
      env: {
        PYTHONPATH: root,
        PYTHONUNBUFFERED: "1",
        "DUCKCLAW_PM2_PROCESS_NAME": "DuckClaw-Gateway",
        DUCKCLAW_GATEWAY_RO_LOCK_ATTEMPTS: "8",
        DUCKCLAW_GATEWAY_RO_LOCK_BASE_SLEEP_S: "0.15",
      },
    },
  ],
};
