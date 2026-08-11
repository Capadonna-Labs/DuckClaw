/**
 * PM2 — Android MCP server (streamable HTTP local).
 *
 *   pm2 start config/ecosystem.android-mcp.config.cjs --update-env
 *   pm2 restart Android-MCP --update-env
 *
 * Requires ANDROID_MCP_COMMAND in repo .env (see docs/operations/ANDROID_ADB.md).
 */
const path = require("path");

const root = path.resolve(__dirname, "..");
const startScript = path.join(root, "scripts", "start_android_mcp.sh");

module.exports = {
  apps: [
    {
      name: "Android-MCP",
      script: startScript,
      interpreter: "bash",
      cwd: root,
      autorestart: true,
      watch: false,
      max_restarts: 10,
      min_uptime: "10s",
    },
  ],
};
