"""Resolución cross-platform de herramientas locales (uv, Python venv, npm, PM2).

Un solo punto para prerequisitos, subprocess y configs PM2. Funciona en CMD,
PowerShell, bash y zsh porque opera sobre ``os.environ`` del proceso Python
(``uv run duckops …``), no sobre el shell padre.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


class ToolchainError(RuntimeError):
    """Herramienta requerida ausente o comando PM2 fallido."""


@dataclass(frozen=True)
class ResolvedTool:
    name: str
    path: str
    version: str = ""


def _uv_bin_dirs() -> list[Path]:
    home = Path.home()
    dirs = [home / ".local" / "bin", home / ".cargo" / "bin"]
    if platform.system() == "Windows":
        local_app = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app:
            dirs.append(Path(local_app) / "Programs" / "uv")
        program_files = os.environ.get("ProgramFiles", "").strip()
        if program_files:
            dirs.append(Path(program_files) / "uv")
    return dirs


def _windows_program_files() -> Path:
    return Path(os.environ.get("ProgramFiles", r"C:\Program Files"))


def _path_candidate_dirs(*, repo_root: Path | None) -> list[Path]:
    dirs: list[Path] = []
    if platform.system() == "Windows":
        dirs.append(_windows_program_files() / "nodejs")
        dirs.append(_windows_program_files() / "Redis")
        appdata = os.environ.get("APPDATA", "").strip()
        if appdata:
            dirs.append(Path(appdata) / "npm")
    dirs.extend(_uv_bin_dirs())
    _ = repo_root
    return dirs


def _refresh_windows_registry_path() -> None:
    if platform.system() != "Windows":
        return
    try:
        import winreg
    except ImportError:
        return
    chunks: list[str] = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
            user_path = str(winreg.QueryValueEx(key, "Path")[0])
            if user_path.strip():
                chunks.append(user_path)
    except OSError:
        pass
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ) as key:
            machine_path = str(winreg.QueryValueEx(key, "Path")[0])
            if machine_path.strip():
                chunks.append(machine_path)
    except OSError:
        pass
    if chunks:
        os.environ["PATH"] = os.pathsep.join(chunks) + os.pathsep + os.environ.get("PATH", "")


def _prepend_path_dirs(dirs: Sequence[Path]) -> None:
    existing = os.environ.get("PATH", "")
    parts = [str(d) for d in dirs if d.is_dir()]
    if parts:
        os.environ["PATH"] = os.pathsep.join(parts) + os.pathsep + existing


def _npm_query_path(npm: str, flag: str) -> Path | None:
    try:
        proc = subprocess.run(
            [npm, flag, "-g"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    raw = (proc.stdout or "").strip().strip('"')
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def _npm_global_bin_dirs() -> list[Path]:
    """Directorios donde ``npm install -g`` coloca ejecutables (pnpm, pm2, …)."""
    dirs: list[Path] = []
    seen: set[str] = set()

    def _add(path: Path | None) -> None:
        if path is None or not path.is_dir():
            return
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path)
        if key in seen:
            return
        seen.add(key)
        dirs.append(path)

    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA", "").strip()
        if appdata:
            _add(Path(appdata) / "npm")
        _add(_windows_program_files() / "nodejs")

    npm = shutil.which("npm")
    if npm:
        _add(_npm_query_path(npm, "bin"))
        _add(_npm_query_path(npm, "prefix"))

    return dirs


def _resolve_windows_npm_shim(tool_name: str) -> str | None:
    """Resuelve pnpm.cmd / pm2.cmd aunque el directorio no esté aún en PATH."""
    for directory in _npm_global_bin_dirs():
        for name in (f"{tool_name}.cmd", f"{tool_name}.exe", tool_name):
            path = directory / name
            if not path.is_file():
                continue
            if path.suffix.lower() in (".cmd", ".exe"):
                return str(path)
            cmd_sibling = path.with_suffix(".cmd")
            if cmd_sibling.is_file():
                return str(cmd_sibling)
    for name in (f"{tool_name}.cmd", f"{tool_name}.exe", tool_name):
        found = shutil.which(name)
        if found:
            return found
    return None


def prepend_executable_dir(executable: str | None) -> None:
    """Añade al PATH el directorio de un ejecutable ya resuelto (p. ej. tras npm install -g)."""
    if not executable:
        return
    try:
        bin_dir = Path(executable).resolve().parent
    except OSError:
        bin_dir = Path(executable).parent
    if bin_dir.is_dir():
        _prepend_path_dirs([bin_dir])


def refresh_session_path(*, repo_root: Path | None = None) -> None:
    """Actualiza PATH de la sesión actual (idempotente, seguro en cualquier OS)."""
    _refresh_windows_registry_path()
    ordered: list[Path] = []
    seen: set[str] = set()
    for candidate in (*_npm_global_bin_dirs(), *_path_candidate_dirs(repo_root=repo_root)):
        if not candidate.is_dir():
            continue
        try:
            key = str(candidate.resolve())
        except OSError:
            key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(candidate)
    _prepend_path_dirs(ordered)


def dot_venv_python_candidates(root: Path) -> list[Path]:
    root = root.resolve()
    return [
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python3",
        root / ".venv" / "bin" / "python",
    ]


def resolve_repo_python(repo_root: str | Path) -> str:
    """Intérprete del monorepo para PM2 (override env → .venv → sys.executable)."""
    override = (os.environ.get("DUCKCLAW_PM2_PYTHON") or "").strip()
    if override:
        p = Path(override).expanduser()
        if p.is_file():
            return str(p.resolve())
        raise ToolchainError(
            f"DUCKCLAW_PM2_PYTHON apunta a un archivo inexistente: {override}"
        )

    root = Path(repo_root).resolve()
    for cand in dot_venv_python_candidates(root):
        try:
            if not cand.is_file():
                continue
            if cand.suffix.lower() == ".exe":
                return str(cand.resolve())
            if os.access(cand, os.X_OK):
                return str(cand.resolve())
        except OSError:
            continue
    return str(Path(sys.executable).resolve())


def resolve_pm2_executable() -> str | None:
    refresh_session_path()
    if platform.system() == "Windows":
        return _resolve_windows_npm_shim("pm2")
    found = shutil.which("pm2")
    return found if found else None


def pm2_argv(*args: str) -> list[str]:
    exe = resolve_pm2_executable()
    if not exe:
        return ["pm2", *args]
    return [exe, *args]


def is_pm2_available() -> bool:
    return resolve_pm2_executable() is not None


def run_pm2(
    *args: str,
    timeout: int | None = 120,
    cwd: str | Path | None = None,
    check: bool = False,
    capture_output: bool = True,
    text: bool = True,
) -> subprocess.CompletedProcess[str]:
    refresh_session_path()
    exe = resolve_pm2_executable()
    if not exe:
        raise ToolchainError(
            "PM2 no está en PATH. Instálalo con: npm install -g pm2 "
            "(luego cierra y reabre la terminal o ejecuta install.cmd)."
        )
    argv = [exe, *args]
    try:
        return subprocess.run(
            argv,
            capture_output=capture_output,
            text=text,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
            check=check,
        )
    except FileNotFoundError as exc:
        raise ToolchainError(f"No se pudo ejecutar PM2 ({exe}): {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolchainError(f"PM2 excedió el tiempo de espera: {' '.join(argv)}") from exc


def run_pm2_checked(
    *args: str,
    timeout: int | None = 120,
    cwd: str | Path | None = None,
) -> subprocess.CompletedProcess[str]:
    proc = run_pm2(*args, timeout=timeout, cwd=cwd, check=False)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise ToolchainError(
            f"PM2 falló (código {proc.returncode}): pm2 {' '.join(args)}"
            + (f"\n{detail}" if detail else "")
        )
    return proc


def resolve_uv() -> str | None:
    refresh_session_path()
    return shutil.which("uv")


def resolve_node() -> str | None:
    refresh_session_path()
    return shutil.which("node")


def resolve_npm() -> str | None:
    refresh_session_path()
    return shutil.which("npm")


def resolve_pnpm_executable() -> str | None:
    refresh_session_path()
    if platform.system() == "Windows":
        return _resolve_windows_npm_shim("pnpm")
    found = shutil.which("pnpm")
    return found if found else None


def resolve_pnpm() -> str | None:
    return resolve_pnpm_executable()


def tool_version(argv: list[str]) -> str:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=15, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""
    if proc.returncode != 0:
        return ""
    return ((proc.stdout or proc.stderr or "").strip().splitlines() or [""])[0][:120]
