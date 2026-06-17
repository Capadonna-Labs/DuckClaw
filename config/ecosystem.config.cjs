/**
 * Re-export del ecosystem PM2 MLX texto (alias de ecosystem.mlx.config.cjs).
 *
 * Arrancar:  pm2 start config/ecosystem.config.cjs
 * Parar:     pm2 stop MLX-Inference
 * Logs:      pm2 logs MLX-Inference
 * Persistir: pm2 save
 *
 * Requiere: packages/agents/train/scripts/serve/start_mlx.sh y .env (opcional: MLX_PYTHON, MLX_MODEL_PATH, MLX_PORT).
 * DuckClaw usa por defecto http://127.0.0.1:8080/v1 (provider=mlx).
 */
module.exports = require("./ecosystem.mlx.config.cjs");
