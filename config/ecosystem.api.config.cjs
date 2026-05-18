/**
 * PM2 — API Gateways DuckClaw (generado). Secretos: solo .env (env_file).
 * Regenerar: uv run duckops serve --pm2 --gateway
 * pm2 start config/ecosystem.api.config.cjs --only "NombreGateway"
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
      name: "DuckClaw-Gateway",
      script: python,
      args: "services/api-gateway/uvicorn_pm2.py main:app --host 0.0.0.0 --port 8000 --app-dir services/api-gateway",
      cwd: root,
      env_file: path.join(root, ".env"),
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_restarts: 10,
      env: {
        PYTHONPATH: root,
        "DUCKCLAW_PM2_PROCESS_NAME": "DuckClaw-Gateway",
      },
    },
  ],
};
