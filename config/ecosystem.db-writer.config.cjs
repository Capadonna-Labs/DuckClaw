/**
 * PM2 — DuckClaw DB-Writer. Variables: solo .env (env_file).
 * Regenerar: duckops init / stack_health.write_db_writer_ecosystem
 */
const path = require("path");
const fs = require("fs");
const root = path.resolve(__dirname, "..");
const python = fs.existsSync(path.join(root, ".venv/bin/python3"))
  ? path.join(root, ".venv/bin/python3")
  : path.join(root, ".venv/bin/python");

module.exports = {
  apps: [
    {
      name: "DuckClaw-DB-Writer",
      script: python,
      args: "main.py",
      cwd: path.join(root, "services/db-writer"),
      env_file: path.join(root, ".env"),
      interpreter: "none",
      autorestart: true,
      watch: false,
      env: {
        PYTHONPATH: root,
      },
    },
  ],
};
