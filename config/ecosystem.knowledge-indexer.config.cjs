/**
 * PM2 — Knowledge indexer (RAG folder ingest/sync + auto-sync poll).
 * Gateway must NOT run this work — enqueue via Redis and consume here.
 *
 * pm2 start config/ecosystem.knowledge-indexer.config.cjs
 */
const path = require("path");
const root = path.resolve(__dirname, "..");
const { resolveRepoPython } = require("./ecosystem.runtime.cjs");
const python = resolveRepoPython(root);

module.exports = {
  apps: [
    {
      name: "DuckClaw-Knowledge-Indexer",
      script: python,
      args: "services/knowledge-indexer/main.py",
      cwd: root,
      env_file: path.join(root, ".env"),
      interpreter: "none",
      autorestart: true,
      watch: false,
      windowsHide: true,
      max_restarts: 10,
      filter_env: [
        /^npm_/,
        /^NEXT_/,
        /^PNPM_/,
        /^__NEXT_/,
        "NODE_OPTIONS",
        "NODE_ENV",
        "PORT",
        "INIT_CWD",
      ],
      env: {
        PYTHONPATH: root,
        PYTHONUNBUFFERED: "1",
        DUCKCLAW_PM2_PROCESS_NAME: "DuckClaw-Knowledge-Indexer",
        DUCKCLAW_PROCESS_ROLE: "knowledge-indexer",
        DUCKCLAW_KNOWLEDGE_AUTO_SYNC: "true",
      },
    },
  ],
};
