/**
 * PM2 — Perfil genérico Spawn (Gateway + Admin UI).
 * Spec: specs/features/platform/SPAWN_GENERIC_DEPLOY.md
 */
const path = require("path");
const root = path.resolve(__dirname, "..");
const { resolveRepoPython } = require("./ecosystem.runtime.cjs");
const python = resolveRepoPython(root);
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
    {
      name: "DuckClaw-Heartbeat",
      script: python,
      args: "services/heartbeat/main.py",
      cwd: root,
      env_file: envFile,
      interpreter: "none",
      autorestart: true,
      watch: false,
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
        DUCKCLAW_REPO_ROOT: root,
        DUCKCLAW_PM2_PROCESS_NAME: "DuckClaw-Heartbeat",
        DUCKCLAW_PROCESS_ROLE: "heartbeat",
      },
    },
  ],
};
