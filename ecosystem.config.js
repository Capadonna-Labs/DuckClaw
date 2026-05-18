/**
 * PM2: Dreamer nocturno (02:00 America/Bogota).
 * Carga variables desde `.env` del repo (PM2 no las lee solo).
 */
const fs = require("fs");
const path = require("path");

function loadDotenv(filePath) {
  const out = {};
  try {
    const raw = fs.readFileSync(filePath, "utf8");
    for (const line of raw.split("\n")) {
      const t = line.trim();
      if (!t || t.startsWith("#")) continue;
      const eq = t.indexOf("=");
      if (eq <= 0) continue;
      const k = t.slice(0, eq).trim();
      let v = t.slice(eq + 1).trim();
      if (
        (v.startsWith('"') && v.endsWith('"')) ||
        (v.startsWith("'") && v.endsWith("'"))
      ) {
        v = v.slice(1, -1);
      }
      out[k] = v;
    }
  } catch (_) {
    /* sin .env: solo env explícitos abajo */
  }
  return out;
}

const repoRoot = __dirname;
const dotenv = loadDotenv(path.join(repoRoot, ".env"));

module.exports = {
  apps: [
    {
      name: "duckclaw-dreamer",
      script: "uv",
      cwd: repoRoot,
      args: [
        "run",
        "packages/agents/src/duckclaw/graphs/dreamer_job.py",
        "--tenant-id",
        "1726618406",
        "--compact",
      ],
      cron_restart: "0 2 * * *",
      autorestart: false,
      watch: false,
      env: {
        ...dotenv,
        DUCKCLAW_LLM_PROVIDER: "mlx",
        TZ: "America/Bogota",
      },
      log_file: "logs/pm2-duckclaw-dreamer.log",
      error_file: "logs/pm2-duckclaw-dreamer-error.log",
      merge_logs: true,
    },
  ],
};
