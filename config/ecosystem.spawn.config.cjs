/**
 * PM2 — Perfil genérico Spawn (Gateway + Admin UI).
 * Spec: specs/features/platform/SPAWN_GENERIC_DEPLOY.md
 * Secretos: solo .env (env_file).
 *
 * pm2 start config/ecosystem.spawn.config.cjs
 */
const path = require("path");
const fs = require("fs");

const root = path.resolve(__dirname, "..");
const python = fs.existsSync(path.join(root, ".venv/bin/python3"))
  ? path.join(root, ".venv/bin/python3")
  : path.join(root, ".venv/bin/python");
const envFile = path.join(root, ".env");

module.exports = {
  apps: [
    {
      name: "duckclaw-gateway",
      script: python,
      args: "services/api-gateway/uvicorn_pm2.py main:app --host 0.0.0.0 --port 8000 --app-dir services/api-gateway",
      cwd: root,
      env_file: envFile,
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_restarts: 10,
      env: {
        PYTHONPATH: root,
        DUCKCLAW_REPO_ROOT: root,
        DUCKCLAW_PM2_PROCESS_NAME: "duckclaw-gateway",
        NODE_ENV: "production",
      },
    },
    {
      name: "duckclaw-admin-ui",
      script: "pnpm",
      args: "run start -- -p 3000 -H 0.0.0.0",
      cwd: path.join(root, "apps/duckclaw-admin"),
      env_file: envFile,
      interpreter: "none",
      autorestart: true,
      watch: false,
      env: {
        PORT: "3000",
        NODE_ENV: "production",
        DUCKCLAW_REPO_ROOT: root,
      },
    },
  ],
};
