"""Codegen y runtime compartido para configs PM2 (ecosystem.*.config.cjs)."""

from __future__ import annotations

from pathlib import Path

from duckclaw.ops.toolchain import resolve_repo_python

# Compat: imports históricos desde manager / tests.
resolve_repo_pm2_python = resolve_repo_python


def render_ecosystem_runtime_cjs() -> str:
    """Genera ``config/ecosystem.runtime.cjs`` (única fuente JS para resolver Python)."""
    return '''/**
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
'''


def ensure_ecosystem_runtime(repo_root: Path) -> Path:
    """Escribe ``config/ecosystem.runtime.cjs`` si cambió el contenido canónico."""
    config_dir = repo_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / "ecosystem.runtime.cjs"
    content = render_ecosystem_runtime_cjs()
    if path.is_file() and path.read_text(encoding="utf-8") == content:
        return path
    path.write_text(content, encoding="utf-8")
    return path


def ecosystem_repo_python_js_lines() -> list[str]:
    return [
        'const { resolveRepoPython } = require("./ecosystem.runtime.cjs");',
        "const python = resolveRepoPython(root);",
    ]


def ecosystem_pm2_fork_app_options_js_lines(*, max_restarts: int | None = 10) -> list[str]:
    """Opciones PM2 para procesos Python en fork (sin ventana de consola en Windows)."""
    lines = [
        '      interpreter: "none",',
        "      autorestart: true,",
        "      watch: false,",
        "      windowsHide: true,",
    ]
    if max_restarts is not None:
        lines.append(f"      max_restarts: {max_restarts},")
    return lines
