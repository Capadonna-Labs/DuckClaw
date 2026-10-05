/**
 * PM2 — admin Next standalone en el puerto que Tailscale Serve ya publica.
 * Requiere `pnpm admin:build` antes (apps/duckclaw-admin/.next/standalone).
 *
 * pm2 start config/ecosystem.admin-ui.config.cjs
 */
const path = require("path");
const root = path.resolve(__dirname, "..");

module.exports = {
  apps: [
    {
      name: "duckclaw-admin-ui",
      script: "/bin/bash",
      args: "scripts/pm2-start-admin-ui.sh",
      cwd: root,
      interpreter: "none",
      autorestart: true,
      watch: false,
      windowsHide: true,
      max_restarts: 10,
      min_uptime: 5000,
      env: {
        PORT: "3001",
        NODE_ENV: "production",
        DUCKCLAW_ADMIN_BIND_HOST: "127.0.0.1",
        DUCKCLAW_REPO_ROOT: root,
      },
    },
  ],
};
