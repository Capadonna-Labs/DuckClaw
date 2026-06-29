/**
 * Runtime compartido PM2 — NO editar a mano.
 * Regenerar: uv run duckops stack codegen
 */
"use strict";

const path = require("path");
const fs = require("fs");

function resolveRepoPython(root) {
  const fromEnv = (process.env.DUCKCLAW_PM2_PYTHON || "").trim();
  if (fromEnv) {
    if (fs.existsSync(fromEnv)) return fromEnv;
    throw new Error("DUCKCLAW_PM2_PYTHON no existe: " + fromEnv);
  }
  const candidates = [
    path.join(root, ".venv", "Scripts", "pythonw.exe"),
    path.join(root, ".venv", "Scripts", "python.exe"),
    path.join(root, ".venv", "bin", "python3"),
    path.join(root, ".venv", "bin", "python"),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  throw new Error(
    "No hay Python en .venv bajo " + root + ". Ejecuta: uv sync"
  );
}

module.exports = { resolveRepoPython };
