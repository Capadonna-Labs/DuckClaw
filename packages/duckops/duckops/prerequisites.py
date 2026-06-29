"""Verificación e instalación de prerequisitos del stack local (macOS / Linux / Windows)."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import time
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


def _is_windows() -> bool:
    return platform.system() == "Windows"


def platform_label() -> str:
    system = platform.system()
    if system == "Darwin":
        return "macOS"
    if system == "Linux":
        return "Linux"
    if system == "Windows":
        return "Windows"
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
    if system == "Windows":
        return (
            "En Windows: net start Redis  o  ejecuta install.cmd de nuevo "
            "(arranca redis-server desde Program Files\\Redis)"
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
    """Comandos que pueden pedir sudo (apt, brew install) o elevación en Windows."""
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


def _winget_path() -> str | None:
    return shutil.which("winget")


def _winget_install(package_id: str, print_fn: PrintFn, *, quiet: bool = False) -> bool:
    winget = _winget_path()
    if not winget:
        if not quiet:
            print_fn("winget no disponible.")
        return False
    if not quiet:
        print_fn(f"winget install --id {package_id} ...")
    code = _run_interactive(
        [
            winget,
            "install",
            "--id",
            package_id,
            "-e",
            "--accept-package-agreements",
            "--accept-source-agreements",
        ],
        timeout=1200,
    )
    if code != 0 and not quiet:
        print_fn(f"winget: paquete {package_id} no instalado (codigo {code}).")
    return code == 0


def _refresh_windows_user_path() -> None:
    if not _is_windows():
        return
    try:
        import winreg
    except ImportError:
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
            user_path = str(winreg.QueryValueEx(key, "Path")[0])
        if user_path.strip():
            os.environ["PATH"] = user_path + os.pathsep + os.environ.get("PATH", "")
    except OSError:
        pass
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ) as key:
            machine_path = str(winreg.QueryValueEx(key, "Path")[0])
        if machine_path.strip():
            os.environ["PATH"] = machine_path + os.pathsep + os.environ.get("PATH", "")
    except OSError:
        pass


def _windows_program_files() -> Path:
    return Path(os.environ.get("ProgramFiles", r"C:\Program Files"))


def _windows_redis_dirs() -> list[Path]:
    return [_windows_program_files() / "Redis"]


def _windows_node_dirs() -> list[Path]:
    return [_windows_program_files() / "nodejs"]


def _prepend_path_dirs(dirs: list[Path]) -> None:
    existing = os.environ.get("PATH", "")
    parts = [str(d) for d in dirs if d.is_dir()]
    if parts:
        os.environ["PATH"] = os.pathsep.join(parts) + os.pathsep + existing


def augment_path_for_windows_tools() -> None:
    """Tras winget, expone Node, npm y Redis en la sesion actual."""
    if not _is_windows():
        return
    _refresh_windows_user_path()
    _prepend_path_dirs(_windows_node_dirs() + _windows_redis_dirs() + _uv_bin_dirs())


def _uv_bin_dirs() -> list[Path]:
    home = Path.home()
    dirs = [home / ".local" / "bin", home / ".cargo" / "bin"]
    if _is_windows():
        local_app = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app:
            dirs.append(Path(local_app) / "Programs" / "uv")
        program_files = os.environ.get("ProgramFiles", "").strip()
        if program_files:
            dirs.append(Path(program_files) / "uv")
    return dirs


def _find_redis_server_windows() -> str | None:
    augment_path_for_windows_tools()
    found = shutil.which("redis-server")
    if found:
        return found
    for redis_dir in _windows_redis_dirs():
        for name in ("redis-server.exe", "redis-server"):
            candidate = redis_dir / name
            if candidate.is_file():
                return str(candidate)
    return None


def _wait_redis_ping(*, attempts: int = 15, delay_seconds: float = 0.5) -> bool:
    for _ in range(attempts):
        if check_redis().ok:
            return True
        time.sleep(delay_seconds)
    return False


def _start_redis_windows_service(print_fn: PrintFn) -> bool:
    for service_name in ("Redis", "redis"):
        proc = _run(["net", "start", service_name], timeout=60)
        if proc.returncode == 0:
            print_fn(f"Servicio Windows '{service_name}' iniciado.")
            return _wait_redis_ping()
    return False


def _try_start_redis_windows(print_fn: PrintFn) -> bool:
    augment_path_for_windows_tools()
    if check_redis().ok:
        return True
    if _start_redis_windows_service(print_fn):
        return True
    redis_server = _find_redis_server_windows()
    if not redis_server:
        print_fn(
            "Redis instalado pero redis-server no esta en PATH. "
            "Reinicia la terminal o ejecuta: net start Redis"
        )
        return False
    print_fn(f"Iniciando Redis en segundo plano ({redis_server})...")
    try:
        redis_dir = str(Path(redis_server).parent)
        subprocess.Popen(
            [redis_server],
            cwd=redis_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:
        print_fn(f"No se pudo arrancar redis-server: {exc}")
        return False
    if _wait_redis_ping():
        return True
    print_fn("Redis no respondio en localhost:6379 tras arrancar redis-server.")
    return False


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


def _augment_path_for_uv() -> None:
    """Tras instalar uv, añade rutas típicas al PATH de la sesión actual."""
    if _is_windows():
        augment_path_for_windows_tools()
        return
    uv_name = "uv"
    for candidate in _uv_bin_dirs():
        if (candidate / uv_name).is_file():
            os.environ["PATH"] = str(candidate) + os.pathsep + os.environ.get("PATH", "")
            return


def ensure_uv_available(print_fn: PrintFn = _default_print) -> bool:
    """Garantiza que ``uv`` está instalado y en PATH (sesión actual)."""
    if shutil.which("uv"):
        return True
    return install_uv(print_fn)


def install_uv(print_fn: PrintFn = _default_print) -> bool:
    if shutil.which("uv"):
        return True
    print_fn("Instalando uv (Astral)...")
    if _is_windows():
        if _winget_path() and _winget_install("astral-sh.uv", print_fn):
            _augment_path_for_uv()
            if shutil.which("uv"):
                return True
        code = _run_interactive(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "irm https://astral.sh/uv/install.ps1 | iex",
            ],
            timeout=300,
        )
    elif platform.system() == "Darwin" and _brew_path():
        print_fn("brew install uv ...")
        code = _run_interactive([_brew_path(), "install", "uv"], timeout=600)
        if code != 0:
            code = _run_interactive(
                ["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"],
                timeout=300,
            )
    else:
        code = _run_interactive(
            ["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"],
            timeout=300,
        )
    if code != 0:
        print_fn("uv: falló el instalador. Manual: https://docs.astral.sh/uv/getting-started/installation/")
        return False
    _augment_path_for_uv()
    if shutil.which("uv"):
        return True
    uv_name = "uv.exe" if _is_windows() else "uv"
    for candidate in _uv_bin_dirs():
        local_bin = candidate / uv_name
        if local_bin.is_file():
            print_fn(f"uv instalado en {local_bin}")
            os.environ["PATH"] = str(candidate) + os.pathsep + os.environ.get("PATH", "")
            return True
    print_fn("uv instalado pero no está en PATH — reabre la terminal y vuelve a ejecutar duckops up.")
    return False


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
    if system == "Windows":
        installed = _winget_install("Redis.Redis", print_fn)
        if not installed:
            installed = _winget_install("tporadowski.redis", print_fn, quiet=True)
        if not installed:
            print_fn(
                "ERROR Redis: winget no pudo instalar Redis.Redis. "
                "Prueba: winget install Redis.Redis  o  Docker: docker run -d -p 6379:6379 redis"
            )
            return False
        augment_path_for_windows_tools()
        if check_redis().ok:
            return True
        if _try_start_redis_windows(print_fn):
            return True
        print_fn(
            "ERROR Redis: instalado pero no responde en localhost:6379. "
            "Prueba en una ventana CMD como admin: net start Redis"
        )
        return False
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
        print_fn("ERROR pnpm: npm no esta en PATH. Instala Node.js y reinicia la terminal.")
        return False
    print_fn("npm install -g pnpm@9 ...")
    code = _run_interactive([npm, "install", "-g", "pnpm@9"], timeout=600)
    if code != 0 and not _is_windows():
        print_fn("pnpm: prueba con sudo npm install -g pnpm@9 si falló por permisos.")
        code = _run_interactive(["sudo", npm, "install", "-g", "pnpm@9"], timeout=600)
    if code != 0:
        print_fn(f"ERROR pnpm: npm install -g pnpm fallo (codigo {code}).")
        return False
    if not check_pnpm().ok:
        print_fn("ERROR pnpm: instalado pero no aparece en PATH.")
        return False
    return True


def install_node(print_fn: PrintFn = _default_print, *, assume_yes: bool = False) -> bool:
    if check_node().ok and check_npm().ok:
        return True
    system = platform.system()
    if system == "Darwin":
        if not ensure_homebrew(print_fn, assume_yes=assume_yes):
            return False
        return _brew_install(["node"], print_fn)
    if system == "Linux":
        return _linux_apt_install(["nodejs", "npm"], print_fn)
    if system == "Windows":
        if _winget_install("OpenJS.NodeJS.LTS", print_fn):
            augment_path_for_windows_tools()
            if check_node().ok and check_npm().ok:
                return True
            node_ok = check_node().ok
            npm_ok = check_npm().ok
            print_fn(
                f"ERROR Node.js: winget OK pero node={'si' if node_ok else 'NO'} npm={'si' if npm_ok else 'NO'} en PATH."
            )
            return False
        print_fn("ERROR Node.js: winget install OpenJS.NodeJS.LTS fallo.")
        return False
    print_fn(f"Node auto-install no soportado en {system}.")
    return False


def install_pm2(print_fn: PrintFn = _default_print) -> bool:
    if check_pm2().ok:
        return True
    npm = shutil.which("npm")
    if not npm:
        print_fn("ERROR PM2: npm no esta en PATH. Instala Node.js primero.")
        return False
    print_fn("npm install -g pm2 ...")
    code = _run_interactive([npm, "install", "-g", "pm2"], timeout=600)
    if code != 0 and not _is_windows():
        print_fn("PM2: prueba con sudo npm install -g pm2 si falló por permisos.")
        code = _run_interactive(["sudo", npm, "install", "-g", "pm2"], timeout=600)
    if code != 0:
        print_fn(f"ERROR PM2: npm install -g pm2 fallo (codigo {code}).")
        return False
    if not check_pm2().ok:
        print_fn("ERROR PM2: instalado pero no aparece en PATH.")
        return False
    return True


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
    if code != 0:
        print_fn(f"ERROR uv sync: fallo con codigo {code}. Revisa red o permisos de escritura.")
        return False
    return True


def _install_missing_tools(
    repo_root: Path,
    *,
    assume_yes: bool,
    sync_python: bool,
    print_fn: PrintFn,
    redis_url: str,
) -> bool:
    if _is_windows():
        augment_path_for_windows_tools()

    print_fn("  [prereq] Redis (cola de mensajes, puerto 6379)...")
    if not check_redis(redis_url).ok:
        if not install_redis(print_fn, assume_yes=assume_yes):
            return _report_prerequisite_failure("Redis", print_fn, redis_url=redis_url)
    else:
        print_fn("  [prereq] Redis OK")

    print_fn("  [prereq] Node.js + npm (consola admin)...")
    if not check_node().ok or not check_npm().ok:
        if not install_node(print_fn, assume_yes=assume_yes):
            return _report_prerequisite_failure("Node.js / npm", print_fn, redis_url=redis_url)
    else:
        print_fn("  [prereq] Node.js + npm OK")

    if _is_windows():
        augment_path_for_windows_tools()

    print_fn("  [prereq] pnpm (gestor de paquetes admin)...")
    if not check_pnpm().ok:
        if not install_pnpm(print_fn):
            return _report_prerequisite_failure("pnpm", print_fn, redis_url=redis_url)
    else:
        print_fn("  [prereq] pnpm OK")

    print_fn("  [prereq] PM2 (gateway + db-writer en segundo plano)...")
    if not check_pm2().ok:
        if not install_pm2(print_fn):
            return _report_prerequisite_failure("PM2", print_fn, redis_url=redis_url)
    else:
        print_fn("  [prereq] PM2 OK")

    if sync_python and shutil.which("uv"):
        print_fn("  [prereq] uv sync (entorno virtual Python + dependencias)...")
        if not run_uv_sync(repo_root, print_fn):
            return _report_prerequisite_failure("uv sync", print_fn, redis_url=redis_url)
    elif sync_python:
        return _report_prerequisite_failure("uv (no encontrado para uv sync)", print_fn, redis_url=redis_url)

    final = check_all(redis_url=redis_url)
    all_ok = all(c.ok for c in final)
    print_fn("")
    print_fn("  Resumen prerequisitos:")
    for c in final:
        mark = "OK" if c.ok else "FALTA"
        ver = f" ({c.version})" if c.version else ""
        print_fn(f"    [{mark}] {c.name}{ver} — {c.detail}")
    if not all_ok:
        return _report_prerequisite_failure("chequeo final", print_fn, redis_url=redis_url)
    print_fn("  Todos los prerequisitos OK.")
    return True


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
    Con ``install=True`` intenta instalar lo que falte:
    macOS (Homebrew), Linux (apt) o Windows (winget + instaladores oficiales).
    """
    system = platform.system()
    supported = system in ("Darwin", "Linux", "Windows")
    if not supported:
        print_fn(
            f"Sistema {platform_label()}: auto-instalación no soportada. "
            "Instala uv, Redis, Node y PM2 manualmente."
        )
        return False

    if install and not check_uv().ok:
        if not ensure_uv_available(print_fn):
            return _report_prerequisite_failure("uv", print_fn, redis_url=redis_url)

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

    return _install_missing_tools(
        repo_root,
        assume_yes=assume_yes,
        sync_python=sync_python,
        print_fn=print_fn,
        redis_url=redis_url,
    )


def format_prerequisite_hint() -> str:
    return (
        "Prerequisitos: uv, Redis, Node.js, npm, pnpm, PM2. "
        "Instálalos con: uv run duckops bootstrap --yes"
    )


def _remediation_hint(tool_name: str) -> str:
    system = platform.system()
    hints: dict[str, str] = {
        "uv": "winget install astral-sh.uv  o  ejecuta install.cmd / ./duckops-up.sh de nuevo",
        "Redis": redis_start_hint(),
        "Node.js": (
            "winget install OpenJS.NodeJS.LTS  y  cierra y reabre la terminal (o install.cmd otra vez)"
            if system == "Windows"
            else "brew install node  o  apt install nodejs npm"
        ),
        "npm": (
            "Viene con Node.js; en Windows cierra la ventana y ejecuta install.cmd otra vez"
            if system == "Windows"
            else "Instala Node.js (incluye npm)"
        ),
        "pnpm": "npm install -g pnpm@9  (requiere npm en PATH)",
        "PM2": "npm install -g pm2  (requiere npm en PATH)",
    }
    return hints.get(tool_name, "uv run duckops bootstrap --yes")


def explain_prerequisite_failures(
    print_fn: PrintFn = _default_print,
    *,
    redis_url: str = _DEFAULT_REDIS_URL,
    failed_step: str = "",
) -> None:
    """Resumen accionable de herramientas que siguen fallando."""
    checks = check_all(redis_url=redis_url)
    missing = [c for c in checks if not c.ok]
    print_fn("")
    print_fn("=" * 52)
    print_fn("  FALLO EN PREREQUISITOS")
    if failed_step:
        print_fn(f"  Paso que fallo: {failed_step}")
    print_fn("=" * 52)
    if missing:
        for c in missing:
            print_fn(f"  [FALTA] {c.name}")
            if c.detail:
                print_fn(f"          Detalle: {c.detail}")
            print_fn(f"          Solucion: {_remediation_hint(c.name)}")
    else:
        print_fn("  Todas las herramientas responden OK en el chequeo final.")
        print_fn("  Revisa el log anterior (uv sync, permisos o red).")
    if _is_windows():
        print_fn("")
        print_fn("  Windows: si acabas de instalar Node o Redis con winget,")
        print_fn("  cierra esta ventana y ejecuta install.cmd otra vez.")
    print_fn("=" * 52)
    print_fn("")


def _report_prerequisite_failure(
    failed_step: str,
    print_fn: PrintFn,
    *,
    redis_url: str = _DEFAULT_REDIS_URL,
) -> bool:
    print_fn(f"ERROR: fallo en prerequisito — {failed_step}")
    explain_prerequisite_failures(print_fn, redis_url=redis_url, failed_step=failed_step)
    return False
