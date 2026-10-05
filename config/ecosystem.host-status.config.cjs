/**
 * PM2 — correo cada 3 horas con RAM, disco y procesos del Mac.
 * No escribe DuckDB. Secretos solo en .env.
 *
 * pm2 start config/ecosystem.host-status.config.cjs
 */
const path = require("path");
const root = path.resolve(__dirname, "..");
const { resolveRepoPython } = require("./ecosystem.runtime.cjs");
const python = resolveRepoPython(root);

module.exports = {
  apps: [
    {
      name: "DuckClaw-Host-Status",
      script: python,
      args: "packages/duckops/duckops/host_status_mail.py",
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
        HOST_STATUS_INTERVAL_SECONDS: "10800",
        DUCKCLAW_PM2_PROCESS_NAME: "DuckClaw-Host-Status",
      },
    },
  ],
};
