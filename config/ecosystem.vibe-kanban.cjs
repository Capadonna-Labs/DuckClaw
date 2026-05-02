/**
 * PM2: planning board Vibe Kanban (solo local / Mac mini — no exponer en Cloudflare Tunnel).
 *
 * Desde la raíz del repo:
 *   pm2 start config/ecosystem.vibe-kanban.cjs
 *   pm2 logs vibe-kanban
 */
const path = require("path");

module.exports = {
  apps: [
    {
      name: "vibe-kanban",
      script: "npx",
      args: "-y vibe-kanban --port 3333",
      cwd: path.join(__dirname, ".."),
      env: {
        PORT: "3333",
        HOST: "127.0.0.1",
      },
      watch: false,
      autorestart: true,
      max_restarts: 3,
      restart_delay: 5000,
    },
  ],
};
