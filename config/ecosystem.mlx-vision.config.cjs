/**
 * PM2 — MLX-Vision (VLM). Variables MLX_* en .env; start_mlx_vision.sh las carga.
 *
 *   pm2 start config/ecosystem.mlx-vision.config.cjs
 *   pm2 restart MLX-Vision --update-env
 */
const path = require("path");

const root = path.resolve(__dirname, "..");
const startMlxVision = path.join(
  root,
  "packages/agents/train/scripts/start_mlx_vision.sh",
);

module.exports = {
  apps: [
    {
      name: "MLX-Vision",
      script: startMlxVision,
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
