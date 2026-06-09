"""Load Capadonna-Driller worker plugins from ``$CAPADONNA_DRILLER_ROOT/workers/duckclaw/lib``."""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Optional

_log = logging.getLogger(__name__)

_PKG = "capadonna_driller_lib"
_MODULE_CACHE: dict[str, ModuleType] = {}


def capadonna_root() -> Optional[Path]:
    raw = (os.environ.get("CAPADONNA_DRILLER_ROOT") or "").strip()
    if raw:
        p = Path(raw).expanduser()
        if p.is_dir():
            return p.resolve()
    sibling = Path(__file__).resolve().parents[5] / "Capadonna-Driller"
    if sibling.is_dir():
        return sibling.resolve()
    return None


def _lib_dir() -> Optional[Path]:
    root = capadonna_root()
    if root is None:
        return None
    lib = root / "workers" / "duckclaw" / "lib"
    return lib if lib.is_dir() else None


def _ensure_package() -> Optional[Path]:
    lib = _lib_dir()
    if lib is None:
        return None
    if _PKG not in sys.modules:
        init = lib / "__init__.py"
        spec = importlib.util.spec_from_file_location(
            _PKG,
            str(init if init.is_file() else lib / "ibkr_bridge.py"),
            submodule_search_locations=[str(lib)],
        )
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[_PKG] = mod
        spec.loader.exec_module(mod)
    return lib


def require_capadonna_lib(name: str) -> ModuleType:
    mod = load_capadonna_lib(name)
    if mod is None:
        raise RuntimeError(
            f"Capadonna-Driller plugin '{name}' not found; set CAPADONNA_DRILLER_ROOT"
        )
    return mod


def load_capadonna_lib(name: str) -> Optional[ModuleType]:
    """Import ``workers/duckclaw/lib/{name}.py`` from Capadonna-Driller."""
    stem = (name or "").strip().removesuffix(".py")
    if not stem:
        return None
    if stem in _MODULE_CACHE:
        return _MODULE_CACHE[stem]
    lib = _ensure_package()
    if lib is None:
        return None
    path = lib / f"{stem}.py"
    if not path.is_file():
        return None
    fq = f"{_PKG}.{stem}"
    if fq in sys.modules:
        mod = sys.modules[fq]
        _MODULE_CACHE[stem] = mod
        return mod
    spec = importlib.util.spec_from_file_location(fq, str(path), submodule_search_locations=[str(lib)])
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[fq] = mod
    spec.loader.exec_module(mod)
    _MODULE_CACHE[stem] = mod
    return mod


def dispatch_capadonna_fly_command(name: str, *args: Any, **kwargs: Any) -> Optional[str]:
    mod = load_capadonna_lib("fly_commands")
    if mod is None:
        return None
    dispatch = getattr(mod, "dispatch", None)
    if not callable(dispatch):
        return None
    try:
        return dispatch(name, *args, **kwargs)
    except Exception:
        _log.debug("capadonna fly command %s failed", name, exc_info=True)
        return None


def register_ibkr_skills(
    tools: list[Any],
    ibkr_config: Optional[dict],
    *,
    worker_path: str,
    logical_worker_id: str,
    is_finanz_worker: bool,
) -> None:
    if ibkr_config is None:
        return
    mod = load_capadonna_lib("ibkr_bridge")
    if mod is None:
        return
    try:
        mod.register_ibkr_skill(tools, ibkr_config)
        if is_finanz_worker:
            mod.replace_get_ibkr_portfolio_with_finanz_live_variant(tools, str(worker_path))
    except Exception:
        _log.debug("capadonna ibkr skill registration skipped", exc_info=True)


def register_quant_skills(
    *,
    db: Any,
    spec: Any,
    tools: list[Any],
    llm: Any,
    logical_worker_id: str,
    is_finanz_worker: bool,
    is_quant_trader_worker: bool,
) -> None:
    qcfg = getattr(spec, "quant_config", None)
    if not isinstance(qcfg, dict) or not qcfg.get("enabled"):
        return
    try:
        if is_finanz_worker:
            market = load_capadonna_lib("quant_market_bridge")
            trade = load_capadonna_lib("quant_trade_bridge")
            if market is not None:
                market.register_quant_market_skill(db, tools, spec)
            if trade is not None:
                trade.register_quant_trade_skills(db, spec, tools)
            if qcfg.get("cfd"):
                cfd = load_capadonna_lib("quant_cfd_bridge")
                if cfd is not None:
                    cfd.register_quant_cfd_skill(db, spec, tools)
        elif is_quant_trader_worker and llm is not None:
            trader = load_capadonna_lib("quant_trader_bridge")
            if trader is not None:
                trader.register_quant_trader_skills(db, llm, tools)
    except Exception:
        _log.debug("capadonna quant skill registration skipped", exc_info=True)
