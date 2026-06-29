/**
 * PM2 — DuckClaw-Voice (Pipecat realtime WebRTC on Mac mini / dev host).
 *
 *   pm2 start config/ecosystem.voice.config.cjs
 *   pm2 restart DuckClaw-Voice --update-env
 *
 * Requires in .env:
 *   DUCKCLAW_VOICE_ENABLED=true
 *   DUCKCLAW_VOICE_BIND_HOST=127.0.0.1  (or Tailscale IP)
 *   DUCKCLAW_VOICE_PORT=8012
 *   DUCKCLAW_VOICE_GATEWAY_URL=http://127.0.0.1:8000
 *   DUCKCLAW_VOICE_GATEWAY_ADMIN_KEY=<same as DUCKCLAW_ADMIN_API_KEY>
 */
const path = require("path");

const root = path.resolve(__dirname, "..");
const startVoice = path.join(root, "integrations/pipecat-voice/scripts/start_voice.sh");

module.exports = {
  apps: [
    {
      name: "DuckClaw-Voice",
      script: startVoice,
      interpreter: "/bin/zsh",
      cwd: root,
      autorestart: true,
      watch: false,
      max_restarts: 10,
      min_uptime: "5s",
    },
  ],
};
