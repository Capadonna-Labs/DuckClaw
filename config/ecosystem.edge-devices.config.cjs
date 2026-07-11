/**
 * PM2 — Edge devices dashboard (Streamlit :8501).
 *
 *   pm2 start config/ecosystem.edge-devices.config.cjs
 *   pm2 restart Edge-Streamlit --update-env
 */
const path = require("path");

const root = path.resolve(__dirname, "..");
const startEdge = path.join(root, "scripts", "start_edge_streamlit.sh");

module.exports = {
  apps: [
    {
      name: "Edge-Streamlit",
      script: startEdge,
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
