"""Gateway FastAPI lifespan: startup readiness, Redis, background warmers, shutdown."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import redis.asyncio as redis
from fastapi import FastAPI

_log = logging.getLogger("duckclaw.gateway")
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def _uvicorn_listen_port() -> int:
    try:
        for i, x in enumerate(sys.argv):
            if x == "--port" and i + 1 < len(sys.argv):
                return int(sys.argv[i + 1])
    except (ValueError, IndexError):
        pass
    from duckclaw.gateway_port import resolve_gateway_port

    return resolve_gateway_port()


def _warn_if_loopback_gateway_port_steals_telegram_funnel() -> None:
    """
    Funnel suele hacer proxy a ``127.0.0.1:<DUCKCLAW_GATEWAY_PORT>``. Si otro proceso
    (p.ej. discord_mcp) enlaza ese loopback, Telegram recibe 404 del proceso equivocado.
    """
    port = _uvicorn_listen_port()
    loopback = f"127.0.0.1:{port}"
    lsof_bin = shutil.which("lsof")
    if not lsof_bin:
        return
    try:
        proc = subprocess.run(
            [lsof_bin, "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        return
    out = (proc.stdout or "").strip()
    if loopback not in out:
        return
    low = out.lower()
    condensed = " | ".join(out.splitlines()[:10])
    if "discord_mcp" in low or "-m discord_mcp.main" in low:
        _log.error(
            "Conflicto Telegram/Funnel: hay LISTEN en %s relacionado con discord_mcp; "
            "las peticiones a %s no llegarán a este gateway. Ejecuta "
            "`bash scripts/telegram/stop_discord_mcp_port_8000.sh` o arranca MCP con HOST=127.0.0.1 "
            "PORT=8010. lsof (recorte): %s",
            loopback,
            loopback,
            condensed,
        )
        return
    listen_hits = [ln for ln in out.splitlines() if "LISTEN" in ln]
    if len(listen_hits) >= 2:
        _log.warning(
            "Puerto %s: múltiples LISTEN; curl/Funnel a 127.0.0.1 pueden no ser DuckClaw. "
            "lsof (recorte): %s",
            port,
            condensed,
        )


def _normalize_local_artifacts_to_db() -> None:
    """Mueve artefactos locales conocidos a `db/` si aparecen en la raíz."""
    try:
        db_dir = _REPO_ROOT / "db"
        db_dir.mkdir(parents=True, exist_ok=True)
        for filename in ("SELECT", "dump.rdb"):
            src = _REPO_ROOT / filename
            dst = db_dir / filename
            if src.exists():
                try:
                    if dst.exists():
                        src.unlink(missing_ok=True)
                    else:
                        src.replace(dst)
                except Exception:
                    pass
    except Exception:
        pass


async def _run_deferred_gateway_startup() -> None:
    """Warmups pesados fuera del camino crítico: uvicorn debe aceptar /health de inmediato."""
    try:
        from duckclaw.forge.skills.comfyui_bridge import (
            clear_all_comfy_generations,
            reset_comfyui_runtime,
        )

        stale = await asyncio.to_thread(clear_all_comfy_generations)
        reset_result = await asyncio.to_thread(reset_comfyui_runtime)
        if stale or reset_result.get("interrupt") or reset_result.get("deleted_pending"):
            _log.info(
                "ComfyUI startup hygiene: stale_jobs=%s reset=%s",
                len(stale),
                reset_result,
            )
    except Exception as exc:  # noqa: BLE001
        _log.debug("ComfyUI startup hygiene skipped: %s", exc)

    try:
        from duckclaw.graphs.graph_server import get_db
        from duckclaw.llm_usage_log import ensure_llm_usage_log_table
        from duckclaw.media_usage_log import ensure_media_usage_log_table

        await asyncio.to_thread(ensure_llm_usage_log_table, get_db())
        await asyncio.to_thread(ensure_media_usage_log_table, get_db())
        _log.info("llm_usage_log: tabla asegurada en gateway DuckDB")
    except Exception as exc:  # noqa: BLE001
        _log.warning("llm_usage_log: no se pudo asegurar tabla al arranque: %s", exc)

    try:
        from duckclaw.catalog_seed import seed_catalog_if_empty
        from duckclaw.graphs.graph_server import get_db

        await asyncio.to_thread(seed_catalog_if_empty, get_db())
        _log.info("catalog: templates importados desde filesystem")
    except Exception as exc:  # noqa: BLE001
        _log.debug("catalog seed skipped: %s", exc)

    try:
        from duckclaw.sandbox_artifacts import purge_expired_runs

        purge_result = await asyncio.to_thread(purge_expired_runs)
        if purge_result.get("purged"):
            _log.info(
                "sandbox artifacts: purged %s expired run(s)",
                purge_result.get("purged"),
            )
    except Exception as exc:  # noqa: BLE001
        _log.warning("sandbox artifacts: purge at startup failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from duckclaw.gateway.settings import get_gateway_settings
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.infra.readiness import assert_gateway_startup_ready

    gw_settings = get_gateway_settings()
    gw_settings.require_production_secrets()
    gateway_db_path = get_gateway_db_path()
    await assert_gateway_startup_ready(
        redis_url=gw_settings.resolved_redis_url(),
        gateway_db_path=gateway_db_path,
    )

    _warn_if_loopback_gateway_port_steals_telegram_funnel()
    app.state.redis = redis.from_url(str(gw_settings.resolved_redis_url()), decode_responses=True)
    app.state.goals_ticker_task = None
    app.state.knowledge_auto_sync_task = None
    _normalize_local_artifacts_to_db()
    # DDL en runtime desactivado: ejecutar duckclaw-migrate / bootstrap_dbs antes de PM2.
    app.state.telegram_mcp = None

    async def _start_telegram_mcp() -> None:
        try:
            from duckclaw.forge.skills.telegram_mcp_bridge import (
                infer_repo_root,
                start_telegram_mcp_gateway_session,
            )

            _mcp_repo = infer_repo_root()
            _mcp_sess = await start_telegram_mcp_gateway_session(_mcp_repo)
            if _mcp_sess is not None:
                app.state.telegram_mcp = _mcp_sess
                _log.info("Telegram MCP: sesión stdio activa para egress")
        except Exception as exc:  # noqa: BLE001
            _log.warning("Telegram MCP: no se pudo iniciar (se usa Bot API directa): %s", exc)

    asyncio.create_task(_start_telegram_mcp(), name="telegram-mcp-warm")

    try:
        from duckclaw.forge.skills.reddit_bridge import (
            _reddit_env_ready,
            reddit_mcp_using_prefetch,
            warm_reddit_mcp_pool,
        )

        if _reddit_env_ready():
            if not reddit_mcp_using_prefetch():
                _log.warning(
                    "Reddit MCP: sin prefetch local (npx puede tardar 2–5 min). "
                    "Ejecuta: bash scripts/prefetch_mcp_reddit.sh"
                )
            else:
                _log.info("Reddit MCP: usando cache local (.mcp-cache/reddit)")
            import threading

            def _warm_reddit_mcp() -> None:
                warm_reddit_mcp_pool()

            threading.Thread(
                target=_warm_reddit_mcp,
                name="reddit-mcp-warm",
                daemon=True,
            ).start()
            _log.info("Reddit MCP: warm iniciado en background")
    except Exception as exc:  # noqa: BLE001
        _log.warning("Reddit MCP: warm no iniciado: %s", exc)

    _embed_goals_ticker = (
        os.environ.get("DUCKCLAW_EMBED_GOALS_TICKER", "true").strip().lower()
        in ("1", "true", "yes", "on")
    )
    if _embed_goals_ticker:
        try:
            from services.heartbeat.main import GOALS_TICKER_POLL_SECONDS, _run_goals_proactive_tick

            _poll_s = max(5, int(GOALS_TICKER_POLL_SECONDS))

            from services.heartbeat.main import _run_meditate_proactive_tick

            async def _goals_ticker_loop() -> None:
                while True:
                    try:
                        await _run_goals_proactive_tick()
                    except Exception as _loop_exc:  # noqa: BLE001
                        _log.warning("embedded crons ticker loop error: %s", _loop_exc)
                    try:
                        await _run_meditate_proactive_tick()
                    except Exception as _med_exc:  # noqa: BLE001
                        _log.warning("embedded meditate ticker loop error: %s", _med_exc)
                    await asyncio.sleep(_poll_s)

            app.state.goals_ticker_task = asyncio.create_task(_goals_ticker_loop())
            _log.info(
                "embedded crons+méditate ticker enabled (poll=%ss, source=services.heartbeat)",
                _poll_s,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning("embedded crons ticker no disponible: %s", exc)

    try:
        from duckclaw.forge.rag.knowledge_auto_sync import auto_sync_enabled, auto_sync_poll_seconds, run_auto_sync_poll

        if auto_sync_enabled():
            _knowledge_poll_s = auto_sync_poll_seconds()

            async def _knowledge_auto_sync_loop() -> None:
                while True:
                    try:
                        await asyncio.to_thread(run_auto_sync_poll)
                    except Exception as _ks_exc:  # noqa: BLE001
                        _log.warning("knowledge auto-sync loop error: %s", _ks_exc)
                    await asyncio.sleep(_knowledge_poll_s)

            app.state.knowledge_auto_sync_task = asyncio.create_task(
                _knowledge_auto_sync_loop(),
                name="knowledge-auto-sync",
            )
            _log.info(
                "knowledge auto-sync enabled (poll=%ss, vault/Obsidian folder sources)",
                _knowledge_poll_s,
            )
    except Exception as exc:  # noqa: BLE001
        _log.warning("knowledge auto-sync no disponible: %s", exc)

    app.state.deferred_startup_task = asyncio.create_task(
        _run_deferred_gateway_startup(),
        name="gateway-deferred-startup",
    )

    yield

    _dst = getattr(app.state, "deferred_startup_task", None)
    if _dst is not None:
        _dst.cancel()
        try:
            await _dst
        except BaseException:
            pass
        app.state.deferred_startup_task = None

    _gt = getattr(app.state, "goals_ticker_task", None)
    if _gt is not None:
        _gt.cancel()
        try:
            await _gt
        except BaseException:
            pass
        app.state.goals_ticker_task = None

    _ks = getattr(app.state, "knowledge_auto_sync_task", None)
    if _ks is not None:
        _ks.cancel()
        try:
            await _ks
        except BaseException:
            pass
        app.state.knowledge_auto_sync_task = None

    _tg_mcp = getattr(app.state, "telegram_mcp", None)
    if _tg_mcp is not None:
        try:
            await _tg_mcp.aclose()
        except Exception as exc:  # noqa: BLE001
            _log.warning("Telegram MCP: error al cerrar sesión: %s", exc)
        app.state.telegram_mcp = None

    await app.state.redis.aclose()
