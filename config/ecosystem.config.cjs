/**
 * PM2 config: motor de inferencia MLX para DuckClaw (API OpenAI-compatible).
 *
 * Arrancar:  pm2 start ecosystem.config.cjs
 * Parar:     pm2 stop DuckClaw-Inference
 * Logs:      pm2 logs DuckClaw-Inference
 * Persistir: pm2 save
 *
 * Requiere: mlx/start_mlx.sh y .env (opcional: MLX_PYTHON, MLX_MODEL_PATH, MLX_PORT).
 * DuckClaw usa por defecto http://127.0.0.1:8080/v1 (provider=mlx).
 */
const path = require("path");

const root = __dirname;
const startScript = path.join(root, "mlx", "start_mlx.sh");

module.exports = {
  apps: [
    {
      name: "DuckClaw-Inference",
      script: startScript,
      interpreter: "bash",
      cwd: root,
      autorestart: true,
      watch: false,
      max_restarts: 10,
      env: {
        MLX_PORT: process.env.MLX_PORT || "8080",
      },
    },
  ],
};
