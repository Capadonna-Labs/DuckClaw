/**
 * PM2 — Perfil genérico Spawn (Gateway + Admin UI).
 * Spec: docs/GETTING_STARTED.md
 */
const path = require("path");
const fs = require("fs");
const root = path.resolve(__dirname, "..");
const { resolveRepoPython } = require("./ecosystem.runtime.cjs");
const python = resolveRepoPython(root);
const envFile = path.join(root, ".env");
const adminDir = path.join(root, "apps/duckclaw-admin");
const nextBin = path.join(adminDir, "node_modules", "next", "dist", "bin", "next");

/** ponytail: on Windows PM2 wraps pnpm in CMD.EXE (visible black windows on crash-loop). */
function adminUiPm2App() {
  if (process.platform === "win32" && fs.existsSync(nextBin)) {
    return {
      name: "duckclaw-admin-ui",
      script: process.execPath,
      args: `"${nextBin}" start -p 3000 -H 0.0.0.0`,
      cwd: adminDir,
      env_file: envFile,
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_restarts: 10,
      min_uptime: 5000,
      windowsHide: true,
      env: {
        PORT: "3000",
        NODE_ENV: "production",
        DUCKCLAW_REPO_ROOT: root,
      },
    };
  }
  return {
    name: "duckclaw-admin-ui",
    script: "pnpm",
    args: "run start -- -p 3000 -H 0.0.0.0",
    cwd: adminDir,
    env_file: envFile,
    interpreter: "none",
    autorestart: true,
    watch: false,
    max_restarts: 10,
    min_uptime: 5000,
    windowsHide: true,
    env: {
      PORT: "3000",
      NODE_ENV: "production",
      DUCKCLAW_REPO_ROOT: root,
    },
  };
}

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
      windowsHide: true,
      env: {
        PYTHONPATH: root,
        DUCKCLAW_REPO_ROOT: root,
        DUCKCLAW_PM2_PROCESS_NAME: "duckclaw-gateway",
        NODE_ENV: "production",
      },
    },
    adminUiPm2App(),
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
