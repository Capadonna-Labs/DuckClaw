"""Import extension modules from ``DUCKCLAW_EXTENSION_ROOT`` without domain coupling."""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Optional

_log = logging.getLogger(__name__)

_MODULE_CACHE: dict[str, ModuleType] = {}
_PACKAGE_BY_ROOT: dict[str, str] = {}


def _split_roots(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    sep = os.pathsep if os.pathsep in text else ":"
    return [p.strip() for p in text.split(sep) if p.strip()]


def extension_roots() -> list[Path]:
    """Resolved directories from ``DUCKCLAW_EXTENSION_ROOT`` (``:`` or ``os.pathsep``)."""
    out: list[Path] = []
    for part in _split_roots(os.environ.get("DUCKCLAW_EXTENSION_ROOT") or ""):
        candidate = Path(part).expanduser()
        if candidate.is_dir():
            out.append(candidate.resolve())
    return out


def default_extension_lib_subpath() -> str:
    """Relative lib path under each extension root (default ``lib``)."""
    sub = (os.environ.get("DUCKCLAW_EXTENSION_LIB_PATH") or "lib").strip().strip("/\\")
    return sub or "lib"


def resolve_extension_lib_dir(
    root: Path,
    *,
    lib_path: str | None = None,
) -> Optional[Path]:
    """Return the plugin lib directory for ``root`` if it exists."""
    sub = (lib_path or default_extension_lib_subpath()).strip()
    lib = Path(sub) if Path(sub).is_absolute() else root / sub
    return lib.resolve() if lib.is_dir() else None


def _package_cache_key(root: Path, lib_path: str | None = None) -> str:
    """Unique key per extension root + lib subtree (multiple lib_path per root)."""
    sub = (lib_path or default_extension_lib_subpath()).strip()
    return f"{root.resolve()}::{sub}"


def package_name_for_root(
    root: Path,
    override: str | None = None,
    *,
    lib_path: str | None = None,
) -> str:
    """Stable synthetic package name for dynamic imports under ``root``/``lib_path``."""
    if override and str(override).strip():
        return str(override).strip()
    key = _package_cache_key(root, lib_path)
    cached = _PACKAGE_BY_ROOT.get(key)
    if cached:
        return cached
    pkg = f"duckclaw_ext_{abs(hash(key)) & 0xFFFFFFFF:08x}"
    _PACKAGE_BY_ROOT[key] = pkg
    return pkg


def ensure_extension_package(
    root: Path,
    *,
    package_name: str | None = None,
    lib_path: str | None = None,
) -> Optional[Path]:
    """
    Register a namespace package for ``root``/``lib_path`` so sibling modules import cleanly.

    Econofísica: el paquete sintético aísla el manifold de plugins del core sin acoplar dominio.
    """
    lib = resolve_extension_lib_dir(root, lib_path=lib_path)
    if lib is None:
        return None
    pkg = package_name_for_root(root, package_name, lib_path=lib_path)
    if pkg in sys.modules:
        return lib
    init = lib / "__init__.py"
    py_files = sorted(lib.glob("*.py"))
    anchor = init if init.is_file() else (py_files[0] if py_files else init)
    spec = importlib.util.spec_from_file_location(
        pkg,
        str(anchor),
        submodule_search_locations=[str(lib)],
    )
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[pkg] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(pkg, None)
        _log.debug("extension package init failed for %s", lib, exc_info=True)
        return None
    return lib


def load_extension_module(
    stem: str,
    *,
    root: Path,
    package_name: str | None = None,
    lib_path: str | None = None,
) -> Optional[ModuleType]:
    """Import ``{lib_path}/{stem}.py`` from an extension root."""
    name = (stem or "").strip().removesuffix(".py")
    if not name:
        return None
    cache_key = f"{root.resolve()}::{lib_path or default_extension_lib_subpath()}::{name}"
    if cache_key in _MODULE_CACHE:
        return _MODULE_CACHE[cache_key]
    lib = ensure_extension_package(root, package_name=package_name, lib_path=lib_path)
    if lib is None:
        return None
    path = lib / f"{name}.py"
    if not path.is_file():
        return None
    pkg = package_name_for_root(root, package_name, lib_path=lib_path)
    fq = f"{pkg}.{name}"
    if fq in sys.modules:
        mod = sys.modules[fq]
        _MODULE_CACHE[cache_key] = mod
        return mod
    spec = importlib.util.spec_from_file_location(fq, str(path), submodule_search_locations=[str(lib)])
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[fq] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(fq, None)
        _log.warning("extension module %s failed to import", path, exc_info=True)
        return None
    _MODULE_CACHE[cache_key] = mod
    return mod


def resolve_callable_entrypoint(
    entrypoint: str,
    *,
    root: Path,
    package_name: str | None = None,
    lib_path: str | None = None,
) -> Optional[Callable[..., Any]]:
    """Resolve ``module_stem:callable`` relative to the extension lib directory."""
    spec = (entrypoint or "").strip()
    if ":" not in spec:
        return None
    mod_stem, _, attr = spec.partition(":")
    mod_stem = mod_stem.strip().removesuffix(".py")
    attr = attr.strip()
    if not mod_stem or not attr:
        return None
    mod = load_extension_module(
        mod_stem,
        root=root,
        package_name=package_name,
        lib_path=lib_path,
    )
    if mod is None:
        return None
    fn = getattr(mod, attr, None)
    return fn if callable(fn) else None


def invalidate_extension_loader_cache() -> None:
    """Clear import caches (tests / hot reload)."""
    _MODULE_CACHE.clear()
    _PACKAGE_BY_ROOT.clear()
