/**
 * PM2 — Sensory Node (STT/TTS on Mac mini, Tailscale bind).
 *
 *   pm2 start config/ecosystem.sensory.config.cjs
 *   pm2 restart Sensory-Node --update-env
 *
 * Requires in .env:
 *   DUCKCLAW_SENSORY_BIND_HOST=100.x.y.z  (Tailscale IP)
 *   DUCKCLAW_SENSORY_PORT=8001
 */
const path = require("path");

const root = path.resolve(__dirname, "..");
const startSensory = path.join(
  root,
  "integrations/sensory-node/scripts/start_sensory.sh",
);

module.exports = {
  apps: [
    {
      name: "Sensory-Node",
      script: startSensory,
      interpreter: "bash",
      cwd: root,
      autorestart: true,
      watch: false,
      max_restarts: 10,
      min_uptime: "5s",
    },
  ],
};
