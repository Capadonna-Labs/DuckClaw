/**
 * PM2 — Heartbeat daemon (crons /crons --delta, méditate, homeostasis).
 * Gateway must NOT embed the goals ticker in production.
 *
 * pm2 start config/ecosystem.heartbeat.config.cjs
 */
const path = require("path");
const root = path.resolve(__dirname, "..");
const { resolveRepoPython } = require("./ecosystem.runtime.cjs");
const python = resolveRepoPython(root);

module.exports = {
  apps: [
    {
      name: "DuckClaw-Heartbeat",
      script: python,
      args: "services/heartbeat/main.py",
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
        DUCKCLAW_PM2_PROCESS_NAME: "DuckClaw-Heartbeat",
        DUCKCLAW_PROCESS_ROLE: "heartbeat",
      },
    },
  ],
};
