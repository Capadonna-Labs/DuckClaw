/**
 * PM2 — ComfyUI (generación visual, API :8188).
 *
 *   pm2 start config/ecosystem.comfyui.config.cjs
 *   pm2 restart ComfyUI --update-env
 */
const path = require("path");

const root = path.resolve(__dirname, "..");
const startComfy = path.join(root, "scripts", "start_comfyui.sh");

module.exports = {
  apps: [
    {
      name: "ComfyUI",
      script: startComfy,
      interpreter: "bash",
      cwd: root,
      env_file: path.join(root, ".env"),
      autorestart: true,
      watch: false,
      max_restarts: 10,
      min_uptime: "10s",
    },
  ],
};
