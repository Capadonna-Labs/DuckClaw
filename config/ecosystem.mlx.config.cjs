/**
 * PM2 — MLX-Inference (mlx_lm texto). Variables en .env; start_mlx.sh las carga.
 *
 *   pm2 start config/ecosystem.mlx.config.cjs
 */
const path = require("path");

const root = path.resolve(__dirname, "..");
const startMlx = path.join(root, "packages/agents/train/scripts/start_mlx.sh");

module.exports = {
  apps: [
    {
      name: "MLX-Inference",
      script: startMlx,
      interpreter: "bash",
      cwd: root,
      env_file: path.join(root, ".env"),
      autorestart: true,
      watch: false,
      max_restarts: 10,
      min_uptime: "5s",
    },
  ],
};
