"""Verificación e instalación de prerequisitos del stack local (macOS / Linux)."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

PrintFn = Callable[[str], None]

_DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/0"


@dataclass(frozen=True)
class ToolCheck:
    name: str
    ok: bool
    version: str
    detail: str


def platform_label() -> str:
    system = platform.system()
    if system == "Darwin":
        return "macOS"
    if system == "Linux":
        return "Linux"
    return system


def redis_start_hint() -> str:
    """Ejemplos concretos para arrancar Redis (mensajes orientados al usuario)."""
    system = platform.system()
    if system == "Darwin":
        return "En macOS: brew services start redis"
    if system == "Linux":
        return (
            "En Linux: sudo systemctl start redis "
            "(Fedora: sudo dnf install -y redis && sudo systemctl enable --now redis)"
        )
    return "Arranca Redis en localhost:6379"


def _default_print(msg: str) -> None:
    print(msg, flush=True)


def _run(
    cmd: list[str],
    *,
    timeout: int = 600,
    cwd: Path | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(cwd) if cwd else None,
        check=check,
    )


def _run_interactive(cmd: list[str], *, timeout: int = 900, cwd: Path | None = None) -> int:
    """Comandos que pueden pedir sudo (apt, brew install)."""
    try:
        proc = subprocess.run(
            cmd,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
        )
        return int(proc.returncode)
    except subprocess.TimeoutExpired:
        return 124


def _version_line(proc: subprocess.CompletedProcess[str]) -> str:
    return ((proc.stdout or proc.stderr or "").strip().splitlines() or [""])[0][:120]


def check_uv() -> ToolCheck:
    uv = shutil.which("uv")
    if not uv:
        return ToolCheck("uv", False, "", "no está en PATH")
    proc = _run([uv, "--version"], timeout=15)
    if proc.returncode != 0:
        return ToolCheck("uv", False, "", _version_line(proc) or "uv --version falló")
    return ToolCheck("uv", True, _version_line(proc), uv)


def check_node() -> ToolCheck:
    node = shutil.which("node")
    if not node:
        return ToolCheck("Node.js", False, "", "no está en PATH (consola admin)")
    proc = _run([node, "--version"], timeout=15)
    ver = _version_line(proc)
    ok = proc.returncode == 0 and bool(ver)
    return ToolCheck("Node.js", ok, ver, node if ok else "node --version falló")


def check_npm() -> ToolCheck:
    npm = shutil.which("npm")
    if not npm:
        return ToolCheck("npm", False, "", "no está en PATH")
    proc = _run([npm, "--version"], timeout=15)
    ver = _version_line(proc)
    ok = proc.returncode == 0
    return ToolCheck("npm", ok, ver, npm if ok else "npm --version falló")


def check_pnpm() -> ToolCheck:
    pnpm = shutil.which("pnpm")
    if not pnpm:
        return ToolCheck("pnpm", False, "", "no está en PATH (consola admin)")
    proc = _run([pnpm, "--version"], timeout=15)
    ver = _version_line(proc)
    ok = proc.returncode == 0
    return ToolCheck("pnpm", ok, ver, pnpm if ok else "pnpm --version falló")


def check_pm2() -> ToolCheck:
    pm2 = shutil.which("pm2")
    if not pm2:
        return ToolCheck("PM2", False, "", "no está en PATH (gateway + db-writer)")
    proc = _run([pm2, "-v"], timeout=15)
    ver = _version_line(proc)
    ok = proc.returncode == 0
    return ToolCheck("PM2", ok, ver, pm2 if ok else "pm2 -v falló")


def check_redis(url: str = _DEFAULT_REDIS_URL) -> ToolCheck:
    try:
        from duckops.sovereign.validate import redis_ping_url

        ok, msg = redis_ping_url(url)
        return ToolCheck("Redis", ok, "pong" if ok else "", msg if not ok else url)
    except Exception as exc:
        return ToolCheck("Redis", False, "", str(exc)[:160])


def check_all(*, redis_url: str = _DEFAULT_REDIS_URL) -> list[ToolCheck]:
    return [
        check_uv(),
        check_redis(redis_url),
        check_node(),
        check_npm(),
        check_pnpm(),
        check_pm2(),
    ]


def _brew_path() -> str | None:
    brew = shutil.which("brew")
    if brew:
        return brew
    for candidate in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew"):
        if Path(candidate).is_file():
            return candidate
    return None


def ensure_homebrew(print_fn: PrintFn, *, assume_yes: bool) -> bool:
    if platform.system() != "Darwin":
        return True
    if _brew_path():
        return True
    if not assume_yes:
        print_fn("Homebrew no encontrado. Re-ejecuta con --yes o duckops bootstrap --yes.")
        return False
    print_fn("Instalando Homebrew (puede tardar varios minutos)...")
    script = (
        'NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL '
        'https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    )
    code = _run_interactive(["/bin/bash", "-c", script], timeout=1200)
    if code != 0:
        print_fn(f"Homebrew: instalación falló (código {code}).")
        return False
    return _brew_path() is not None


def _brew_install(packages: list[str], print_fn: PrintFn) -> bool:
    brew = _brew_path()
    if not brew:
        print_fn("Homebrew no disponible.")
        return False
    print_fn(f"brew install {' '.join(packages)} ...")
    code = _run_interactive([brew, "install", *packages], timeout=1200)
    return code == 0


def _brew_services_start(service: str, print_fn: PrintFn) -> bool:
    brew = _brew_path()
    if not brew:
        return False
    print_fn(f"brew services start {service} ...")
    code = _run_interactive([brew, "services", "start", service], timeout=120)
    return code == 0


def _linux_apt_install(packages: list[str], print_fn: PrintFn) -> bool:
    if platform.system() != "Linux":
        return False
    if not shutil.which("apt-get"):
        print_fn(
            "Linux sin apt-get: instala manualmente "
            + ", ".join(packages)
            + " (o usa Docker para Redis)."
        )
        return False
    print_fn("apt-get update (sudo puede pedir contraseña)...")
    if _run_interactive(["sudo", "apt-get", "update", "-qq"], timeout=600) != 0:
        return False
    print_fn(f"apt-get install -y {' '.join(packages)} ...")
    return _run_interactive(["sudo", "apt-get", "install", "-y", *packages], timeout=900) == 0


def install_uv(print_fn: PrintFn = _default_print) -> bool:
    if shutil.which("uv"):
        return True
    print_fn("Instalando uv (Astral)...")
    code = _run_interactive(
        ["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"],
        timeout=300,
    )
    if code != 0:
        print_fn("uv: falló el instalador. Manual: https://docs.astral.sh/uv/getting-started/installation/")
        return False
    uv = shutil.which("uv")
    if not uv:
        local_bin = Path.home() / ".local" / "bin" / "uv"
        if local_bin.is_file():
            print_fn(f"uv instalado en {local_bin} — añade ~/.local/bin al PATH y reabre la terminal.")
            os.environ["PATH"] = str(local_bin.parent) + os.pathsep + os.environ.get("PATH", "")
            return True
        return False
    return True


def install_redis(print_fn: PrintFn = _default_print, *, assume_yes: bool = False) -> bool:
    if check_redis().ok:
        return True
    system = platform.system()
    if system == "Darwin":
        if not ensure_homebrew(print_fn, assume_yes=assume_yes):
            return False
        if not _brew_install(["redis"], print_fn):
            return False
        return _brew_services_start("redis", print_fn)
    if system == "Linux":
        if not _linux_apt_install(["redis-server"], print_fn):
            return False
        for cmd in (
            ["sudo", "systemctl", "enable", "redis-server"],
            ["sudo", "systemctl", "start", "redis-server"],
        ):
            if _run_interactive(cmd, timeout=120) != 0:
                alt = ["sudo", "systemctl", "enable", "--now", "redis-server"]
                if _run_interactive(alt, timeout=120) != 0:
                    print_fn("Redis instalado pero systemctl falló; arranca redis-server manualmente.")
                    return False
                break
        return check_redis().ok
    print_fn(f"Redis auto-install no soportado en {system}. Usa Docker o instala Redis manualmente.")
    return False


def install_pnpm(print_fn: PrintFn = _default_print) -> bool:
    if check_pnpm().ok:
        return True
    corepack = shutil.which("corepack")
    if corepack:
        print_fn("corepack enable + pnpm@9 (packageManager del monorepo)...")
        if _run_interactive([corepack, "enable"], timeout=120) != 0:
            print_fn("corepack enable falló.")
        elif _run_interactive(
            [corepack, "prepare", "pnpm@9.15.0", "--activate"],
            timeout=300,
        ) == 0 and check_pnpm().ok:
            return True
    npm = shutil.which("npm")
    if not npm:
        return False
    print_fn("npm install -g pnpm@9 ...")
    code = _run_interactive([npm, "install", "-g", "pnpm@9"], timeout=600)
    if code != 0:
        print_fn("pnpm: prueba con sudo npm install -g pnpm@9 si falló por permisos.")
        code = _run_interactive(["sudo", npm, "install", "-g", "pnpm@9"], timeout=600)
    return code == 0 and check_pnpm().ok


def install_node(print_fn: PrintFn = _default_print, *, assume_yes: bool = False) -> bool:
    if check_node().ok and check_npm().ok and check_pnpm().ok:
        return True
    system = platform.system()
    if system == "Darwin":
        if not ensure_homebrew(print_fn, assume_yes=assume_yes):
            return False
        return _brew_install(["node"], print_fn)
    if system == "Linux":
        return _linux_apt_install(["nodejs", "npm"], print_fn)
    print_fn(f"Node auto-install no soportado en {system}.")
    return False


def install_pm2(print_fn: PrintFn = _default_print) -> bool:
    if check_pm2().ok:
        return True
    npm = shutil.which("npm")
    if not npm:
        return False
    print_fn("npm install -g pm2 ...")
    code = _run_interactive([npm, "install", "-g", "pm2"], timeout=600)
    if code != 0:
        print_fn("PM2: prueba con sudo npm install -g pm2 si falló por permisos.")
        code = _run_interactive(["sudo", npm, "install", "-g", "pm2"], timeout=600)
    return code == 0 and check_pm2().ok


def run_uv_sync(repo_root: Path, print_fn: PrintFn = _default_print) -> bool:
    uv = shutil.which("uv")
    if not uv:
        print_fn("uv no disponible; no se puede ejecutar uv sync.")
        return False
    if not (repo_root / "pyproject.toml").is_file():
        print_fn(f"No hay pyproject.toml en {repo_root}")
        return False
    print_fn(f"uv sync en {repo_root} ...")
    code = _run_interactive([uv, "sync"], cwd=repo_root, timeout=1800)
    return code == 0


def ensure_development_prerequisites(
    repo_root: Path,
    *,
    install: bool = False,
    assume_yes: bool = False,
    sync_python: bool = True,
    print_fn: PrintFn = _default_print,
    redis_url: str = _DEFAULT_REDIS_URL,
) -> bool:
    """
    Comprueba uv, Redis, Node, npm, pnpm y PM2.
    Con ``install=True`` intenta instalar lo que falte (macOS Homebrew / Linux apt).
    """
    system = platform.system()
    if system not in ("Darwin", "Linux"):
        print_fn(
            f"Sistema {platform_label()}: auto-instalación no soportada. "
            "Usa WSL2/Linux o macOS; instala uv, Redis, Node y PM2 manualmente."
        )
        return False

    if install and not check_uv().ok:
        if not install_uv(print_fn):
            return False

    checks = check_all(redis_url=redis_url)
    missing = [c for c in checks if not c.ok]

    if not install:
        for c in checks:
            mark = "OK" if c.ok else "FALTA"
            ver = f" ({c.version})" if c.version else ""
            print_fn(f"  [{mark}] {c.name}{ver} — {c.detail}")
        return len(missing) == 0

    if not assume_yes:
        for c in checks:
            mark = "OK" if c.ok else "FALTA"
            ver = f" ({c.version})" if c.version else ""
            print_fn(f"  [{mark}] {c.name}{ver} — {c.detail}")
        if missing:
            names = ", ".join(c.name for c in missing)
            print_fn(f"Faltan: {names}. Usa --yes para instalar automáticamente.")
        return len(missing) == 0

    if not check_redis(redis_url).ok:
            if not install_redis(print_fn, assume_yes=assume_yes):
                return False
    if not check_node().ok or not check_npm().ok:
        if not install_node(print_fn, assume_yes=assume_yes):
            return False
    if not check_pnpm().ok:
        if not install_pnpm(print_fn):
            return False
    if not check_pm2().ok:
        if not install_pm2(print_fn):
            return False

    if sync_python and shutil.which("uv"):
        if not run_uv_sync(repo_root, print_fn):
            print_fn("uv sync falló; revisa el log arriba.")
            return False

    final = check_all(redis_url=redis_url)
    all_ok = all(c.ok for c in final)
    for c in final:
        mark = "OK" if c.ok else "FALTA"
        ver = f" ({c.version})" if c.version else ""
        print_fn(f"  [{mark}] {c.name}{ver} — {c.detail}")
    return all_ok


def format_prerequisite_hint() -> str:
    return (
        "Prerequisitos: uv, Redis, Node.js, npm, pnpm, PM2. "
        "Instálalos con: uv run duckops bootstrap --yes"
    )
