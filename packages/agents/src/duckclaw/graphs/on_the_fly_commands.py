"""
On-the-Fly CLI: comandos de Telegram que mutan estado del grafo sin reiniciar.

Spec: specs/interfaz_de_comandos_dinamicos_On-the-Fly_CLI.md
"""

from __future__ import annotations

import base64
import json
import logging
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Callable, Literal, Optional, Tuple
from pydantic import BaseModel, ConfigDict, ValidationError
from duckclaw.vaults import (
    create_vault as _vault_create,
    list_vaults as _vault_list,
    remove_vault as _vault_remove,
    resolve_active_vault as _vault_resolve_active,
    switch_vault as _vault_switch,
    validate_user_db_path,
    vault_scope_id_for_tenant,
)

from duckclaw.guardrails.loader import format_guardrail, load_guardrail, load_guardrail_pipe_table
from duckclaw.forge.atoms.cron_wall_schedule import (
    format_cron_wall_human,
    parse_cron_wall_tokens,
)
from duckclaw.graphs.proactive_review_markers import (
    GOALS_PROACTIVE_REVIEW_PHRASE_CRONS,
    GOALS_PROACTIVE_REVIEW_PHRASE_LEGACY,
    proactive_review_event_phrase_in_text,
)
from duckclaw.graphs.trading_hours_cot import COT_TZ_NAME, quant_event_horario_line
from duckclaw.utils.logger import format_chat_log_identity, get_obs_logger, log_fly, structured_log_context
from duckclaw.utils.telegram_markdown_v2 import TELEGRAM_MARKDOWN_V2_SPECIAL

_PREFIX = "chat_"


# Revisión proactiva /crons --delta (agent_config; claves internas goals_* sin cambiar)
_GOALS_DELTA_SECONDS_KEY = "goals_delta_seconds"
_GOALS_PROACTIVE_LAST_FIRE_KEY = "goals_proactive_last_fire_epoch"
_GOALS_PROACTIVE_ANCHOR_KEY = "goals_proactive_schedule_anchor_epoch"
_GOALS_PROACTIVE_TENANT_KEY = "goals_proactive_tenant_id"
_GOALS_DELTA_ANCHOR_LEGACY_KEY = "goals_delta_anchor"
_GOALS_DELTA_META_KEY = "goals_delta_meta"
_GOALS_CRON_WALL_KEY = "goals_cron_wall"
GOALS_DELTA_MIN_SECONDS = 60
GOALS_DELTA_MAX_SECONDS = 7 * 24 * 3600

# IDs mostrados en /crons para quitar un schedule con /crons --rm <cron-id>
CRON_SCHEDULE_ID_DELTA = "delta"
CRON_SCHEDULE_ID_WALL = "wall"


def _normalize_cron_rm_id(token: str) -> Optional[str]:
    """``delta`` / ``interval`` → intervalo; ``wall`` / ``timestamp`` → reloj."""
    t = (token or "").strip().lower()
    if t in (CRON_SCHEDULE_ID_DELTA, "interval"):
        return CRON_SCHEDULE_ID_DELTA
    if t in (CRON_SCHEDULE_ID_WALL, "timestamp"):
        return CRON_SCHEDULE_ID_WALL
    return None

# Cola FIFO de PNG base64 por chat: api-gateway hace pop_all y sendPhoto en orden (p. ej. PnL + torta).
_FLY_OUTBOUND_CHART_B64: dict[str, list[str]] = {}


def _debug_log_model_config(
    *,
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict[str, Any],
    run_id: str = "gemini_cfg_debug_v1",
) -> None:
    """Reserved for optional NDJSON debug (no-op)."""
    del hypothesis_id, location, message, data, run_id


def register_fly_outbound_chart_b64(session_id: Any, b64: str) -> None:
    s = (b64 or "").strip()
    if not s:
        return
    k = str(session_id).strip()
    _FLY_OUTBOUND_CHART_B64.setdefault(k, []).append(s)


def pop_all_fly_outbound_charts_b64(session_id: Any) -> list[str]:
    """Devuelve y vacía todas las figuras encoladas para este chat (orden FIFO)."""
    k = str(session_id).strip()
    return _FLY_OUTBOUND_CHART_B64.pop(k, [])


def pop_fly_outbound_chart_b64(session_id: Any) -> str | None:
    """Compat: saca solo el primer PNG de la cola; preferir pop_all en el gateway."""
    k = str(session_id).strip()
    q = _FLY_OUTBOUND_CHART_B64.get(k)
    if not q:
        return None
    first = q.pop(0)
    if not q:
        del _FLY_OUTBOUND_CHART_B64[k]
    return first


def parse_goals_delta_arg(fragment: str) -> tuple[Optional[int], Optional[str]]:
    """
    Convierte texto tras --delta en segundos. (0, None) = desactivar.
    (None, err) = error. Requiere mínimo GOALS_DELTA_MIN_SECONDS si > 0.
    """
    s = (fragment or "").strip().lower()
    if not s:
        return None, "Falta valor tras --delta (ej. 20min, 1h, off)."
    if s in ("off", "0", "false", "no", "disable"):
        return 0, None
    collapsed = re.sub(r"\s+", "", s)
    m = re.match(r"^(\d+(?:\.\d+)?)([a-z]*)$", collapsed, re.I)
    if not m:
        return None, f"No reconozco el intervalo `{fragment}`. Usa ej. 20min, 1h, 45s o off."
    val = float(m.group(1))
    unit = (m.group(2) or "m").lower()
    if unit in ("", "m", "min", "mins", "minute", "minutes"):
        secs = int(val * 60)
    elif unit in ("h", "hr", "hrs", "hour", "hours"):
        secs = int(val * 3600)
    elif unit in ("s", "sec", "secs", "second", "seconds"):
        secs = int(val)
    else:
        return None, f"Unidad no válida en `{fragment}`."
    if secs <= 0:
        return None, "El intervalo debe ser positivo (o usa off)."
    if secs < GOALS_DELTA_MIN_SECONDS:
        return None, f"El mínimo es {GOALS_DELTA_MIN_SECONDS}s (~1 min)."
    if secs > GOALS_DELTA_MAX_SECONDS:
        return None, "El máximo es 7 días."
    return secs, None


def format_goals_delta_interval_human(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds % 3600 == 0 and seconds >= 3600:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0:
        return f"{seconds // 60} min"
    return f"{seconds // 3600}h {(seconds % 3600) // 60}m"


def format_goals_countdown_human(seconds: int) -> str:
    """Texto breve para tiempo restante hasta el próximo tick programado."""
    s = max(0, int(seconds))
    if s <= 0:
        return "menos de 1 s"
    if s >= 3600:
        h, r = divmod(s, 3600)
        m, _ = divmod(r, 60)
        return f"{h}h {m}m" if m else f"{h}h"
    if s >= 60:
        m, sec = divmod(s, 60)
        return f"{m} min {sec}s" if sec else f"{m} min"
    return f"{s}s"


def _goals_proactive_interval_countdown_parts(
    db: Any, chat_id: Any, ds_list: int
) -> tuple[str, str, str]:
    """interval_h, countdown_part, last_bit para mensajes de revisión proactiva."""
    last_raw = (get_chat_state(db, chat_id, _GOALS_PROACTIVE_LAST_FIRE_KEY) or "").strip()
    anchor_raw = (get_chat_state(db, chat_id, _GOALS_PROACTIVE_ANCHOR_KEY) or "").strip()
    now = time.time()
    last_f: Optional[float] = None
    if last_raw:
        try:
            last_f = float(last_raw)
        except (TypeError, ValueError):
            last_f = None
    anchor_f: Optional[float] = None
    if anchor_raw:
        try:
            anchor_f = float(anchor_raw)
        except (TypeError, ValueError):
            anchor_f = None
    interval_h = format_goals_delta_interval_human(ds_list)
    if last_f and last_f > 0:
        remaining = max(0, int(last_f + float(ds_list) - now + 0.999))
        countdown_part = f" · próximo en ~{format_goals_countdown_human(remaining)}"
    elif anchor_f and anchor_f > 0:
        remaining = max(0, int(anchor_f + float(ds_list) - now + 0.999))
        countdown_part = f" · próximo en ~{format_goals_countdown_human(remaining)}"
    else:
        countdown_part = (
            f" · próximo en hasta ~{format_goals_countdown_human(max(0, int(ds_list)))} "
            "(aprox.; vuelve a ejecutar /crons --delta para anclar la hora)"
        )
    last_bit = ""
    if last_f and last_f > 0:
        try:
            from datetime import datetime, timezone

            last_bit = (
                f" · último tick UTC ~{datetime.fromtimestamp(last_f, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')}"
            )
        except Exception:
            pass

    return interval_h, countdown_part, last_bit


def format_platform_cron_summary() -> str:
    """Resumen de crons de infraestructura (heartbeat / gateway). Sin nombres de variables en el texto principal."""
    def _int_env(name: str, default: str) -> int:
        try:
            return max(1, int((os.getenv(name) or default).strip() or default))
        except (TypeError, ValueError):
            return max(1, int(default))

    poll_s = _int_env("GOALS_TICKER_POLL_SECONDS", "45")
    hb_s = _int_env("HEARTBEAT_INTERVAL_SECONDS", "3600")
    embed_raw = (os.getenv("DUCKCLAW_EMBED_GOALS_TICKER") or "true").strip().lower()
    embed_on = embed_raw in ("1", "true", "yes", "on")
    lines = [
        "Del bot (infraestructura)",
        f"· Escaneo de bases para tus revisiones programadas: cada ~{poll_s} s.",
        f"· Homeostasis global (daemon): cada ~{hb_s} s.",
    ]
    if embed_on:
        lines.append("· El API Gateway puede ejecutar el mismo escaneo embebido (si está activo en esta instalación).")
    lines.append("(Intervalos ajustables por operador en el host.)")
    return "\n".join(lines)


def _short_session_uid_for_crons(uid: str) -> str:
    u = (uid or "").strip()
    if len(u) <= 12:
        return u if u else "(sin session_uid en meta)"
    return u[:8] + "…"


def _crons_goals_delta_meta_dict(db: Any, chat_id: Any) -> Optional[dict[str, Any]]:
    raw = (get_chat_state(db, chat_id, _GOALS_DELTA_META_KEY) or "").strip()
    if not raw:
        return None
    try:
        meta = json.loads(raw)
    except Exception:
        return None
    return meta if isinstance(meta, dict) else None


def _crons_goals_delta_listing_section(db: Any, chat_id: Any) -> str:
    """
    Bloque único tras «Manager» en el listado /crons: intervalo delta, cuenta atrás, meta sesión Quant.
    Vacío si no hay intervalo activo ni meta trigger=trading_session.
    """
    try:
        ds_list = int((get_chat_state(db, chat_id, _GOALS_DELTA_SECONDS_KEY) or "0").strip() or "0")
    except ValueError:
        ds_list = 0
    if ds_list < 0:
        ds_list = 0

    meta = _crons_goals_delta_meta_dict(db, chat_id)
    trigger_l = str((meta or {}).get("trigger") or "").strip().lower()
    meta_trading = trigger_l == "trading_session"
    uid_full = str((meta or {}).get("session_uid") or "").strip() if meta_trading else ""

    if ds_list <= 0 and not meta_trading:
        return ""

    title = "Revisión proactiva (TRADING_TICK)" if meta_trading else "Revisión proactiva"
    lines_body: list[str] = []

    if ds_list > 0:
        interval_h, countdown_part, last_bit = _goals_proactive_interval_countdown_parts(db, chat_id, ds_list)
        lines_body.append(
            f"- Intervalo (cron-id {CRON_SCHEDULE_ID_DELTA}): cada ~{interval_h}{countdown_part}{last_bit} "
            f"(/crons --delta off o /crons --rm {CRON_SCHEDULE_ID_DELTA})."
        )
    else:
        lines_body.append(
            "- Intervalo: no activo (goals_delta_seconds=0). Meta indica sesión Quant; "
            "reactiva con /crons --delta … o la tool schedule_quant_trading_proactive_ticks en Quant-Trader."
        )

    if meta_trading:
        uid_disp = _short_session_uid_for_crons(uid_full)
        lines_body.append(
            "- Sesión Quant: session_uid="
            + uid_disp
            + " · origen: schedule_quant_trading_proactive_ticks o /trading-session (trigger trading_session)."
        )

    return f"\n\n{title}\n" + "\n".join(lines_body)


def chat_id_from_goals_delta_config_key(key: str) -> Optional[str]:
    """Extrae chat_id desde fila agent_config con sufijo _goals_delta_seconds."""
    suf = f"_{_GOALS_DELTA_SECONDS_KEY}"
    if not key.startswith(_PREFIX) or not key.endswith(suf):
        return None
    return key[len(_PREFIX) : -len(suf)] or None


def chat_id_from_goals_cron_wall_key(key: str) -> Optional[str]:
    """Extrae chat_id desde fila agent_config con sufijo _goals_cron_wall."""
    suf = f"_{_GOALS_CRON_WALL_KEY}"
    if not key.startswith(_PREFIX) or not key.endswith(suf):
        return None
    return key[len(_PREFIX) : -len(suf)] or None


def _apply_interval_only_clear(conn: Any, chat_id: Any) -> None:
    """Quita solo programación por intervalo (--delta); no toca ``goals_cron_wall`` ni last_fire."""
    set_chat_state(conn, chat_id, _GOALS_DELTA_SECONDS_KEY, "0")
    set_chat_state(conn, chat_id, _GOALS_PROACTIVE_ANCHOR_KEY, "")
    set_chat_state(conn, chat_id, _GOALS_DELTA_ANCHOR_LEGACY_KEY, "")
    try:
        raw_m = (get_chat_state(conn, chat_id, _GOALS_DELTA_META_KEY) or "").strip()
        if not raw_m:
            return
        m = json.loads(raw_m)
        if isinstance(m, dict) and str(m.get("trigger") or "").lower() == "goals_cli":
            set_chat_state(conn, chat_id, _GOALS_DELTA_META_KEY, "")
    except Exception:
        pass


def clear_interval_schedule_only(db: Any, chat_id: Any) -> None:
    """``/crons --delta off``: intervalo y meta goals_cli; conserva horario de reloj y tenant."""
    _apply_interval_only_clear(db, chat_id)

    primary_resolved = ""
    try:
        raw_p = str(getattr(db, "_path", "") or "").strip()
        if raw_p:
            primary_resolved = str(Path(raw_p).expanduser().resolve())
    except Exception:
        primary_resolved = str(getattr(db, "_path", "") or "").strip()

    from duckclaw import DuckClaw as _DuckClaw
    from duckclaw.db_write_queue import enqueue_duckdb_write_sync
    from duckclaw.gateway_db import iter_goals_delta_clear_duckdb_paths

    _upsert_q = (
        "INSERT INTO agent_config (key, value) VALUES (?, ?) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()"
    )

    def _enqueue_interval_clear_remote(_db_path: str) -> None:
        for _sk, _sv in (
            (_GOALS_DELTA_SECONDS_KEY, "0"),
            (_GOALS_PROACTIVE_ANCHOR_KEY, ""),
            (_GOALS_DELTA_ANCHOR_LEGACY_KEY, ""),
        ):
            _ck = _chat_key(chat_id, _sk)
            enqueue_duckdb_write_sync(
                db_path=str(Path(_db_path).expanduser().resolve()),
                query=_upsert_q,
                params=[_ck, str(_sv)[:16384]],
                user_id=str(chat_id),
                tenant_id="default",
            )

    for _p in iter_goals_delta_clear_duckdb_paths(primary_fly_db_path=primary_resolved):
        _rp = ""
        try:
            _rp = str(Path(_p).expanduser().resolve())
        except OSError:
            _rp = str(_p)
        if primary_resolved and _rp == primary_resolved:
            continue
        try:
            with _DuckClaw(_p, read_only=False, engine="python") as _d2:
                _apply_interval_only_clear(_d2)
        except Exception:
            try:
                _enqueue_interval_clear_remote(_p)
            except Exception:
                continue


def _goals_cron_wall_listing_note(db: Any, chat_id: Any) -> str:
    raw = (get_chat_state(db, chat_id, _GOALS_CRON_WALL_KEY) or "").strip()
    if not raw:
        return ""
    try:
        spec = json.loads(raw)
    except Exception:
        return ""
    if not isinstance(spec, dict):
        return ""
    return (
        "\n"
        + format_cron_wall_human(spec)
        + f" · cron-id: {CRON_SCHEDULE_ID_WALL} (/crons --rm {CRON_SCHEDULE_ID_WALL})"
    )


def clear_goals_cron_wall_storage(db: Any, chat_id: Any) -> None:
    """Borra horario de reloj en esta conexión y bóvedas hermanas (misma lógica que clear delta)."""
    set_chat_state(db, chat_id, _GOALS_CRON_WALL_KEY, "")

    primary_resolved = ""
    try:
        raw_p = str(getattr(db, "_path", "") or "").strip()
        if raw_p:
            primary_resolved = str(Path(raw_p).expanduser().resolve())
    except Exception:
        primary_resolved = str(getattr(db, "_path", "") or "").strip()

    from duckclaw import DuckClaw as _DuckClaw
    from duckclaw.db_write_queue import enqueue_duckdb_write_sync
    from duckclaw.gateway_db import iter_goals_delta_clear_duckdb_paths

    _upsert_q = (
        "INSERT INTO agent_config (key, value) VALUES (?, ?) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()"
    )

    def _enqueue_wall_clear_remote(_db_path: str) -> None:
        _ck = _chat_key(chat_id, _GOALS_CRON_WALL_KEY)
        enqueue_duckdb_write_sync(
            db_path=str(Path(_db_path).expanduser().resolve()),
            query=_upsert_q,
            params=[_ck, ""],
            user_id=str(chat_id),
            tenant_id="default",
        )

    for _p in iter_goals_delta_clear_duckdb_paths(primary_fly_db_path=primary_resolved):
        _rp = ""
        try:
            _rp = str(Path(_p).expanduser().resolve())
        except OSError:
            _rp = str(_p)
        if primary_resolved and _rp == primary_resolved:
            continue
        try:
            with _DuckClaw(_p, read_only=False, engine="python") as _d2:
                set_chat_state(_d2, chat_id, _GOALS_CRON_WALL_KEY, "")
        except Exception:
            try:
                _enqueue_wall_clear_remote(_p)
            except Exception:
                continue


def clear_goals_proactive_schedule(db: Any, chat_id: Any) -> None:
    """
    Apaga el ticker ``/crons --delta`` en el hub y en las bóvedas del **mismo** usuario que
    ``db._path`` (``.../private/<uid>/*.duckdb``), más el hub vía ``get_gateway_db_path``. El
    heartbeat puede seguir escaneando más archivos para *descubrir* ticks; abrir en RW todas las
    DuckDB del árbol ``private`` al hacer ``off`` competía por bloqueos con db-writer.
    """

    def _apply_clear(conn: Any) -> None:
        set_chat_state(conn, chat_id, _GOALS_DELTA_SECONDS_KEY, "0")
        set_chat_state(conn, chat_id, _GOALS_PROACTIVE_LAST_FIRE_KEY, "")
        set_chat_state(conn, chat_id, _GOALS_PROACTIVE_ANCHOR_KEY, "")
        set_chat_state(conn, chat_id, _GOALS_PROACTIVE_TENANT_KEY, "")
        set_chat_state(conn, chat_id, _GOALS_DELTA_ANCHOR_LEGACY_KEY, "")
        set_chat_state(conn, chat_id, _GOALS_DELTA_META_KEY, "")
        set_chat_state(conn, chat_id, _GOALS_CRON_WALL_KEY, "")

    _apply_clear(db)

    primary_resolved = ""
    try:
        raw_p = str(getattr(db, "_path", "") or "").strip()
        if raw_p:
            primary_resolved = str(Path(raw_p).expanduser().resolve())
    except Exception:
        primary_resolved = str(getattr(db, "_path", "") or "").strip()

    paths_touched: list[str] = []
    if primary_resolved:
        paths_touched.append(primary_resolved)

    from duckclaw import DuckClaw as _DuckClaw
    from duckclaw.db_write_queue import enqueue_duckdb_write_sync
    from duckclaw.gateway_db import iter_goals_delta_clear_duckdb_paths

    _upsert_q = (
        "INSERT INTO agent_config (key, value) VALUES (?, ?) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()"
    )

    def _enqueue_clear_remote(_db_path: str) -> None:
        for _sk, _sv in (
            (_GOALS_DELTA_SECONDS_KEY, "0"),
            (_GOALS_PROACTIVE_LAST_FIRE_KEY, ""),
            (_GOALS_PROACTIVE_ANCHOR_KEY, ""),
            (_GOALS_PROACTIVE_TENANT_KEY, ""),
            (_GOALS_DELTA_ANCHOR_LEGACY_KEY, ""),
            (_GOALS_DELTA_META_KEY, ""),
            (_GOALS_CRON_WALL_KEY, ""),
        ):
            _ck = _chat_key(chat_id, _sk)
            enqueue_duckdb_write_sync(
                db_path=str(Path(_db_path).expanduser().resolve()),
                query=_upsert_q,
                params=[_ck, str(_sv)[:16384]],
                user_id=str(chat_id),
                tenant_id="default",
            )

    for _p in iter_goals_delta_clear_duckdb_paths(primary_fly_db_path=primary_resolved):
        _rp = ""
        try:
            _rp = str(Path(_p).expanduser().resolve())
        except OSError:
            _rp = str(_p)
        if primary_resolved and _rp == primary_resolved:
            continue
        try:
            with _DuckClaw(_p, read_only=False, engine="python") as _d2:
                _apply_clear(_d2)
            paths_touched.append(_rp or _p)
        except Exception:
            try:
                _enqueue_clear_remote(_p)
                paths_touched.append(f"enqueued:{_rp or _p}")
            except Exception:
                continue

def _skip_runtime_ddl(db: Any) -> bool:
    """Si True, no ejecutar CREATE/ALTER en runtime (asumir scripts/bootstrap_dbs.py)."""
    return bool(getattr(db, "_read_only", False))


def unescape_telegram_markdown_v2_layers(text: str, max_layers: int = 4) -> str:
    """
    Quita hasta ``max_layers`` capas de escape estilo MarkdownV2 (mismo juego de
    caracteres que ``escape_telegram_markdown_v2``). Sirve para:

    - Historial que reinyecta la respuesta HTTP ya escapada (cliente / gateway).
    - Salidas del modelo que copian ``\\.``, ``\\!``, ``\\*`` del contexto.

    Sin esto, el escape MDV2 vuelve a escapar las barras y el texto crece
    (p. ej. ``\\!`` → ``\\\\!`` → ``\\\\\\!``).
    """
    if not text:
        return ""
    esc = frozenset(TELEGRAM_MARKDOWN_V2_SPECIAL)
    t = str(text)
    for _ in range(max(1, int(max_layers))):
        out: list[str] = []
        i = 0
        while i < len(t):
            if t[i] == "\\" and i + 1 < len(t) and t[i + 1] in esc:
                out.append(t[i + 1])
                i += 2
            else:
                out.append(t[i])
                i += 1
        t_new = "".join(out)
        if t_new == t:
            return t_new
        t = t_new
    return t


def _chat_key(chat_id: Any, suffix: str) -> str:
    """Key for agent_config; supports numeric (Telegram) and string (API session_id)."""
    try:
        cid = int(chat_id)
        return f"{_PREFIX}{cid}_{suffix}"
    except (TypeError, ValueError):
        return f"{_PREFIX}{str(chat_id)[:64]}_{suffix}"


_AGENT_CONFIG_TABLE = "agent_config"

# Telegram Guard whitelist persistence (DuckDB table in schema `main`)
_AUTHORIZED_USERS_TABLE = "authorized_users"
_AUTHORIZED_USERS_DDL = f"""
CREATE TABLE IF NOT EXISTS main.{_AUTHORIZED_USERS_TABLE} (
    tenant_id VARCHAR,
    user_id VARCHAR,
    username VARCHAR,
    role VARCHAR DEFAULT 'user',
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, user_id)
);
"""


def _sql_escape_literal(v: Any, max_len: int = 256) -> str:
    s = "" if v is None else str(v)
    return s.replace("'", "''")[:max_len]


def _ensure_authorized_users_table(db: Any) -> None:
    try:
        db.execute(_AUTHORIZED_USERS_DDL)
    except Exception:
        # Best-effort: si falla, la whitelist mutación/consulta se comportará como “no autorizado”.
        pass


def _is_gateway_owner_user(user_id: str) -> bool:
    """Coincide con el bypass del API Gateway (DUCKCLAW_OWNER_ID / DUCKCLAW_ADMIN_CHAT_ID)."""
    uid = str(user_id or "").strip()
    if not uid:
        return False
    owner = (os.environ.get("DUCKCLAW_OWNER_ID") or os.environ.get("DUCKCLAW_ADMIN_CHAT_ID") or "").strip()
    return bool(owner and uid == owner)


def _is_team_admin(db: Any, *, tenant_id: str, requester_id: str) -> bool:
    if _is_gateway_owner_user(requester_id):
        return True
    rid = str(requester_id or "").strip()
    # Consola admin (playground): requester_id suele ser "admin-ui" sin user_id Telegram numérico.
    if rid == "admin-ui":
        return True
    return _get_authorized_role(db, tenant_id=tenant_id, user_id=rid) == "admin"


def _get_authorized_role(db: Any, *, tenant_id: str, user_id: str) -> str:
    _ensure_authorized_users_table(db)
    tid = _sql_escape_literal(tenant_id, max_len=128)
    uid = _sql_escape_literal(user_id, max_len=128)
    try:
        raw = db.query(
            f"SELECT role FROM main.{_AUTHORIZED_USERS_TABLE} "
            f"WHERE lower(tenant_id)=lower('{tid}') AND user_id='{uid}' LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if rows and isinstance(rows[0], dict):
            return (rows[0].get("role") or "").strip().lower()
    except Exception:
        pass
    return ""


def _list_authorized_users(db: Any, *, tenant_id: str) -> list[dict[str, str]]:
    _ensure_authorized_users_table(db)
    tid = _sql_escape_literal(tenant_id, max_len=128)
    try:
        raw = db.query(
            f"SELECT user_id, username, role FROM main.{_AUTHORIZED_USERS_TABLE} "
            f"WHERE lower(tenant_id)=lower('{tid}') ORDER BY user_id"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if isinstance(rows, list):
            out: list[dict[str, str]] = []
            for r in rows:
                if isinstance(r, dict):
                    out.append(
                        {
                            "user_id": str(r.get("user_id") or "").strip(),
                            "username": str(r.get("username") or "").strip(),
                            "role": str(r.get("role") or "").strip(),
                        }
                    )
            return out
    except Exception as exc:
        logging.getLogger("duckclaw.team_whitelist").warning(
            "authorized_users list query failed tenant_id=%r: %s", tenant_id, exc
        )
    return []


def _team_username_by_user_id(db: Any, tenant_id: str | None, user_id: Any) -> str:
    tid = str(tenant_id or "default").strip() or "default"
    uid = str(user_id or "").strip()
    if not uid:
        return ""
    for u in _list_authorized_users(db, tenant_id=tid):
        if str(u.get("user_id") or "").strip() == uid:
            return str(u.get("username") or "").strip()
    return ""


def _player_label(
    username: Any,
    chat_id: Any,
    *,
    db: Any | None = None,
    tenant_id: str | None = None,
) -> str:
    """Etiqueta legible para /team (Telegram mention o @alias)."""
    uname = str(username or "").strip()
    cid = str(chat_id or "").strip() or "unknown"
    if not uname and db is not None:
        uname = _team_username_by_user_id(db, tenant_id, chat_id)
    if uname:
        if cid.isdigit():
            return f"[@{uname}](tg://user?id={cid})"
        return f"@{uname}"
    if cid.isdigit():
        return f"[{cid}](tg://user?id={cid})"
    return cid


def _player_label_log(
    username: Any,
    chat_id: Any,
    *,
    db: Any | None = None,
    tenant_id: str | None = None,
) -> str:
    """Formato para logs PM2: @alias (user_id)."""
    uname = str(username or "").strip()
    if not uname and db is not None:
        uname = _team_username_by_user_id(db, tenant_id, chat_id)
    cid = str(chat_id or "").strip() or "unknown"
    return f"@{uname} ({cid})" if uname else cid


def _resolve_team_add_uid_and_username(tokens: list[str]) -> tuple[str, str]:
    """
    ``/team --add``: el orden documentado es ``<user_id> [nombre]``, pero en Telegram
    es habitual escribir ``<nombre> <user_id> [user|admin]``. Si hay exactamente un token
    con aspecto de Telegram user id (solo dígitos, longitud razonable), se usa como
    ``user_id`` y el resto como nombre para mostrar.
    """
    tks = [t.strip() for t in tokens if t.strip()]
    if not tks:
        return "", "Usuario"
    # Telegram user_id es numérico; en tests se usan ids cortos (p. ej. 999).
    digit_indices = [i for i, x in enumerate(tks) if x.isdigit() and 3 <= len(x) <= 20]
    if len(digit_indices) == 1:
        i = digit_indices[0]
        uid = tks[i]
        name_parts = [tks[j] for j in range(len(tks)) if j != i]
        uname = " ".join(name_parts).strip() or "Usuario"
        return uid, uname
    if len(digit_indices) >= 2:
        i = digit_indices[-1]
        uid = tks[i]
        name_parts = [tks[j] for j in range(len(tks)) if j != i]
        uname = " ".join(name_parts).strip() or "Usuario"
        return uid, uname
    uid0 = tks[0]
    uname = (" ".join(tks[1:]).strip() if len(tks) > 1 else "Usuario") or "Usuario"
    return uid0, uname


def _dedupe_authorized_users_by_user_id(users: list[dict[str, str]]) -> list[dict[str, str]]:
    """
    Unifica filas por ``user_id`` (p. ej. duplicados legacy por distinto casing de ``tenant_id`` en PK).
    Si hay varias filas, se prioriza la que tenga rol ``admin``.
    """
    rank = {"admin": 3, "user": 2, "operator": 2, "observer": 1}

    def _score(u: dict[str, str]) -> int:
        r = (u.get("role") or "").strip().lower()
        return int(rank.get(r, 2))

    best: dict[str, dict[str, str]] = {}
    for u in users:
        uid = str(u.get("user_id") or "").strip()
        if not uid:
            continue
        if uid not in best or _score(u) > _score(best[uid]):
            best[uid] = u
    out = list(best.values())
    out.sort(key=lambda x: str(x.get("user_id") or ""))
    return out


def _upsert_authorized_user(db: Any, *, tenant_id: str, user_id: str, username: str, role: str = "user") -> None:
    _ensure_authorized_users_table(db)
    tid = _sql_escape_literal(tenant_id, max_len=128)
    uid = _sql_escape_literal(user_id, max_len=128)
    un = _sql_escape_literal(username or "Usuario", max_len=128)
    rl = _sql_escape_literal(role or "user", max_len=16)
    db.execute(
        f"""
        INSERT INTO main.{_AUTHORIZED_USERS_TABLE} (tenant_id, user_id, username, role)
        VALUES ('{tid}', '{uid}', '{un}', '{rl}')
        ON CONFLICT (tenant_id, user_id) DO UPDATE SET
          username = EXCLUDED.username,
          role = EXCLUDED.role,
          added_at = now()
        """
    )


def _delete_authorized_user(db: Any, *, tenant_id: str, user_id: str) -> None:
    _ensure_authorized_users_table(db)
    tid = _sql_escape_literal(tenant_id, max_len=128)
    uid = _sql_escape_literal(user_id, max_len=128)
    db.execute(
        f"DELETE FROM main.{_AUTHORIZED_USERS_TABLE} "
        f"WHERE lower(tenant_id)=lower('{tid}') AND user_id='{uid}'"
    )


def _is_wr_tenant(tenant_id: str | None) -> bool:
    return str(tenant_id or "").strip().lower().startswith("wr_")


def _ensure_war_room_tables(db: Any) -> None:
    try:
        db.execute("CREATE SCHEMA IF NOT EXISTS war_room_core;")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS war_room_core.wr_members (
                tenant_id VARCHAR,
                user_id VARCHAR,
                username VARCHAR,
                clearance_level VARCHAR,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (tenant_id, user_id)
            );
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS war_room_core.wr_audit_log (
                event_id VARCHAR PRIMARY KEY,
                tenant_id VARCHAR,
                sender_id VARCHAR,
                target_agent VARCHAR,
                event_type VARCHAR,
                payload TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
    except Exception:
        pass


def _wr_member_clearance(db: Any, *, tenant_id: str, user_id: str) -> str:
    _ensure_war_room_tables(db)
    tid = _sql_escape_literal(tenant_id, max_len=128)
    uid = _sql_escape_literal(user_id, max_len=128)
    try:
        raw = db.query(
            "SELECT clearance_level FROM war_room_core.wr_members "
            f"WHERE lower(tenant_id)=lower('{tid}') AND user_id='{uid}' LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if rows and isinstance(rows[0], dict):
            return str(rows[0].get("clearance_level") or "").strip().lower()
    except Exception:
        pass
    return ""


def _wr_append_audit(
    db: Any,
    *,
    tenant_id: str,
    sender_id: str,
    target_agent: str,
    event_type: str,
    payload: str,
) -> None:
    import uuid

    _ensure_war_room_tables(db)
    db.execute(
        "INSERT INTO war_room_core.wr_audit_log (event_id, tenant_id, sender_id, target_agent, event_type, payload) "
        f"VALUES ('{uuid.uuid4()}', '{_sql_escape_literal(tenant_id, 128)}', "
        f"'{_sql_escape_literal(sender_id, 128)}', '{_sql_escape_literal(target_agent, 64)}', "
        f"'{_sql_escape_literal(event_type, 64)}', '{_sql_escape_literal(payload, 8000)}')"
    )


def register_wr_member(db: Any, tenant_id: Any, requester_id: Any, args: str) -> str:
    tid = str(tenant_id or "default").strip() or "default"
    rid = str(requester_id or "").strip()
    if not _is_wr_tenant(tid):
        return "register_wr_member solo aplica en tenants War Room (wr_<group_id>)."
    _ensure_war_room_tables(db)
    clearance = _wr_member_clearance(db, tenant_id=tid, user_id=rid)
    if not (_is_gateway_owner_user(rid) or clearance == "admin"):
        return "❌ Acceso denegado: solo admin WR puede registrar miembros."
    tokens = [x for x in (args or "").split() if x.strip()]
    if len(tokens) < 2:
        return "Uso: /register_wr_member <user_id> <clearance> [username]"
    uid = tokens[0].strip()
    clr = tokens[1].strip().lower()
    uname = " ".join(tokens[2:]).strip() or "Usuario"
    if clr not in ("admin", "operator", "observer"):
        return "clearance inválido. Usa: admin | operator | observer"
    db.execute(
        "INSERT INTO war_room_core.wr_members (tenant_id, user_id, username, clearance_level) "
        f"VALUES ('{_sql_escape_literal(tid, 128)}', '{_sql_escape_literal(uid, 128)}', "
        f"'{_sql_escape_literal(uname, 128)}', '{_sql_escape_literal(clr, 32)}') "
        "ON CONFLICT (tenant_id, user_id) DO UPDATE SET username=EXCLUDED.username, clearance_level=EXCLUDED.clearance_level, added_at=now()"
    )
    _wr_append_audit(
        db,
        tenant_id=tid,
        sender_id=rid,
        target_agent="manager",
        event_type="REGISTER_WR_MEMBER",
        payload=f"user_id={uid} clearance={clr}",
    )
    return f"✅ Miembro WR registrado: {uid} ({clr})."


def get_wr_context(db: Any, tenant_id: Any, args: str) -> str:
    tid = str(tenant_id or "default").strip() or "default"
    if not _is_wr_tenant(tid):
        return "get_wr_context solo aplica en tenants War Room (wr_<group_id>)."
    _ensure_war_room_tables(db)
    minutes = 60
    try:
        if (args or "").strip():
            minutes = max(1, min(1440, int((args or "").strip())))
    except ValueError:
        minutes = 60
    raw = db.query(
        "SELECT sender_id, target_agent, event_type, payload, timestamp "
        "FROM war_room_core.wr_audit_log "
        f"WHERE lower(tenant_id)=lower('{_sql_escape_literal(tid, 128)}') "
        f"AND timestamp >= now() - INTERVAL '{minutes} minutes' "
        "ORDER BY timestamp DESC LIMIT 10"
    )
    rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    if not rows:
        return "Sin eventos recientes en wr_audit_log."
    lines = ["🧭 War Room Context (últimos eventos):"]
    for r in rows:
        if not isinstance(r, dict):
            continue
        lines.append(
            f"- [{r.get('timestamp')}] {r.get('event_type')} by {r.get('sender_id')} -> {r.get('target_agent')}: {str(r.get('payload') or '')[:120]}"
        )
    return "\n".join(lines)


def broadcast_alert(db: Any, tenant_id: Any, requester_id: Any, args: str) -> str:
    tid = str(tenant_id or "default").strip() or "default"
    rid = str(requester_id or "").strip()
    if not _is_wr_tenant(tid):
        return "broadcast_alert solo aplica en tenants War Room (wr_<group_id>)."
    parts = [x.strip() for x in (args or "").split(None, 1) if x.strip()]
    if len(parts) < 2:
        return "Uso: /broadcast_alert <level> <message>"
    level, message = parts[0].lower(), parts[1]
    if level not in ("info", "warn", "critical"):
        return "level inválido. Usa: info | warn | critical"
    _wr_append_audit(
        db,
        tenant_id=tid,
        sender_id=rid or "system",
        target_agent="group",
        event_type="BROADCAST_ALERT",
        payload=f"[{level}] {message}",
    )
    return f"🚨 WR alert ({level}) registrada."


def _invalidate_whitelist_redis_cache(*, tenant_id: str, user_id: str) -> None:
    """
    El Gateway cachea roles en Redis (TTL ~1h). Tras /team --rm o --add, hay que borrar la clave
    o los usuarios revocados siguen pasando _lookup_whitelist_role hasta que expire el TTL.
    Misma convención que services/api-gateway/main.py: whitelist:{tenant_lower}:{user_id}
    """
    tid = str(tenant_id or "default").strip().lower() or "default"
    uid = str(user_id or "").strip()
    if not uid:
        return
    url = (os.environ.get("REDIS_URL") or os.environ.get("DUCKCLAW_REDIS_URL") or "").strip()
    if not url:
        return
    key = f"whitelist:{tid}:{uid}"
    try:
        import redis as redis_sync  # noqa: PLC0415

        client = redis_sync.Redis.from_url(url, decode_responses=True)
        client.delete(key)
    except Exception:
        pass


def _invalidate_wr_clearance_redis_cache(*, tenant_id: str, user_id: str) -> None:
    """Invalidar cache de clearance WR (services/api-gateway/main.py::_lookup_wr_clearance)."""
    tid = str(tenant_id or "default").strip().lower() or "default"
    uid = str(user_id or "").strip()
    if not uid:
        return
    url = (os.environ.get("REDIS_URL") or os.environ.get("DUCKCLAW_REDIS_URL") or "").strip()
    if not url:
        return
    key = f"wr_clearance:{tid}:{uid}"
    try:
        import redis as redis_sync  # noqa: PLC0415

        client = redis_sync.Redis.from_url(url, decode_responses=True)
        client.delete(key)
    except Exception:
        pass


def _ensure_agent_config(db: Any) -> None:
    if _skip_runtime_ddl(db):
        return
    db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_AGENT_CONFIG_TABLE} (
            key VARCHAR PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def get_chat_state(db: Any, chat_id: Any, key: str) -> str:
    """Read a chat-scoped config key from agent_config."""
    _ensure_agent_config(db)
    k = _chat_key(chat_id, key).replace("'", "''")[:200]
    try:
        r = db.query(f"SELECT value FROM {_AGENT_CONFIG_TABLE} WHERE key = '{k}' LIMIT 1")
        rows = json.loads(r) if isinstance(r, str) else (r or [])
        if rows and isinstance(rows[0], dict):
            return (rows[0].get("value") or "").strip()
    except Exception:
        pass
    return ""


def set_chat_state(db: Any, chat_id: Any, key: str, value: str) -> None:
    """Write a chat-scoped config key to agent_config."""
    _ensure_agent_config(db)
    k = _chat_key(chat_id, key).replace("'", "''")[:128]
    v = str(value).replace("'", "''")[:16384]
    db.execute(
        f"""
        INSERT INTO {_AGENT_CONFIG_TABLE} (key, value) VALUES ('{k}', '{v}')
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """
    )


def parse_command(text: str) -> Tuple[str, str]:
    """Parse /command or /command args. Returns (name, args)."""
    if not text or not text.strip().startswith("/"):
        return "", ""
    parts = text.strip().split(maxsplit=1)
    name = (parts[0] or "").lstrip("/").lower()
    if "@" in name:
        name = name.split("@", 1)[0]
    args = (parts[1] if len(parts) > 1 else "").strip()
    return name, args


def get_team_templates(db: Any, chat_id: Any) -> list:
    """Templates disponibles en el equipo para este chat. Vacío = todos los de list_workers()."""
    raw = get_chat_state(db, chat_id, "team_templates")
    if not raw:
        return []
    try:
        out = json.loads(raw)
        return out if isinstance(out, list) else []
    except Exception:
        return []


def set_team_templates(db: Any, chat_id: Any, template_ids: list) -> None:
    """Define los templates del equipo para este chat. Lista vacía = usar todos (list_workers). Guarda ids canónicos (case del filesystem)."""
    set_chat_state(db, chat_id, "team_templates", json.dumps([str(x).strip() for x in template_ids]))


_TENANT_TEAM_KEY_PREFIX = "tenant_team:"


def _tenant_team_config_key(tenant_id: Any) -> str:
    tid = str(tenant_id or "default").strip() or "default"
    return f"{_TENANT_TEAM_KEY_PREFIX}{tid}"


def get_tenant_team_templates(db: Any, tenant_id: Any) -> list:
    """Equipo por defecto para todo el tenant (misma DuckDB compartida). Vacío = no hay override a nivel tenant."""
    raw = _get_global_config(db, _tenant_team_config_key(tenant_id))
    if not raw:
        return []
    try:
        out = json.loads(raw)
        return out if isinstance(out, list) else []
    except Exception:
        return []


def set_tenant_team_templates(db: Any, tenant_id: Any, template_ids: list) -> None:
    """Persiste el equipo default del tenant en agent_config (clave global)."""
    _set_global_config(
        db,
        _tenant_team_config_key(tenant_id),
        json.dumps([str(x).strip() for x in template_ids]),
    )


def _canonicalize_team_template_ids(ids: list, templates_root: Any = None) -> list:
    """Resuelve alias de manifest y descarta ids sin carpeta en forge/templates."""
    from duckclaw.workers.template_registry import list_template_ids, resolve_template_id

    all_t = list_template_ids(templates_root)
    out: list[str] = []
    seen: set[str] = set()
    for raw in ids or []:
        w = str(raw or "").strip()
        if not w:
            continue
        canonical = resolve_template_id(all_t, w)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        out.append(canonical)
    return out


def get_effective_team_templates(
    db: Any, chat_id: Any, tenant_id: Any, templates_root: Any = None
) -> list:
    """
    Equipo que ve el manager para delegar, en orden:
    1) team_templates del chat
    2) team_templates del tenant (admin vía /workers)
    3) DUCKCLAW_TEAM_MEMBERS
    4) todos los templates (list_workers)
    """
    from duckclaw.workers.factory import list_workers

    chat_team = get_team_templates(db, chat_id)
    if chat_team:
        return _canonicalize_team_template_ids(chat_team, templates_root)
    tid = str(tenant_id or "default").strip() or "default"
    tenant_team = get_tenant_team_templates(db, tid)
    if tenant_team:
        return _canonicalize_team_template_ids(tenant_team, templates_root)
    env_raw = (os.environ.get("DUCKCLAW_TEAM_MEMBERS") or "").strip()
    if env_raw:
        all_t = list_workers(templates_root)
        out: list[str] = []
        for part in env_raw.split(","):
            p = part.strip()
            if not p:
                continue
            c = _resolve_template_id(all_t, p)
            if c:
                out.append(c)
        if out:
            return out
    return list_workers(templates_root)


def _sync_tenant_team_if_admin(
    db: Any,
    *,
    tenant_id: Any,
    requester_id: Any,
    template_ids: list,
) -> None:
    """Si el requester es admin del tenant, replica el equipo del chat como default del tenant."""
    tid = str(tenant_id or "").strip()
    rid = str(requester_id or "").strip()
    if not tid or not rid:
        return
    if not _is_team_admin(db, tenant_id=tid, requester_id=rid):
        return
    set_tenant_team_templates(db, tid, template_ids)


def _resolve_template_id(available: list, user_input: str) -> Optional[str]:
    """Resuelve alias de manifest al id canónico de carpeta en forge/templates."""
    from duckclaw.workers.template_registry import resolve_template_id

    return resolve_template_id(available, user_input)


def execute_team(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    tenant_id: Any = None,
    requester_id: Any = None,
) -> str:
    """/workers [id1 id2 ...] [--add id...] [--rm worker_id]: equipo del chat. Sin args: lista. Con ids: reemplaza. --add: añade; --rm: quita uno. Admin: también actualiza el equipo default del tenant."""
    from duckclaw.workers.factory import list_workers
    all_templates = list_workers()
    tid = str(tenant_id or "default").strip() or "default"
    team = get_team_templates(db, chat_id)
    if not args or not args.strip():
        effective = get_effective_team_templates(db, chat_id, tid, None)
        if not effective:
            return "No hay templates en forge/templates. Añade al menos uno."
        if team:
            label = "Equipo (este chat):"
        elif get_tenant_team_templates(db, tid):
            label = "Equipo del tenant (todos los chats sin override):"
        elif (os.environ.get("DUCKCLAW_TEAM_MEMBERS") or "").strip():
            label = "Equipo (.env):"
        else:
            label = "Equipo: todos los templates"
        lines = "\n".join(f"- {w}" for w in effective)
        hint = load_guardrail("fly_commands", "workers_list_hint")
        return f"🦆 {label}\n{lines}\n\n{hint}"
    raw = args.strip()
    # --rm <worker_id>
    if raw.startswith("--rm "):
        wid_raw = raw[5:].strip().split()[0]
        canonical = _resolve_template_id(all_templates, wid_raw)
        if not canonical:
            return f"'{wid_raw}' no es un template. Equipo actual: {', '.join(team or all_templates) or 'todos'}"
        current = team if team else list(all_templates)
        new_team = [x for x in current if (x or "").strip().lower() != canonical.lower()]
        if len(new_team) == len(current):
            return f"'{canonical}' no está en el equipo. Equipo actual: {', '.join(current) or 'todos'}"
        set_team_templates(db, chat_id, new_team)
        _sync_tenant_team_if_admin(
            db, tenant_id=tid, requester_id=requester_id, template_ids=new_team
        )
        return f"✅ Quitado {canonical} del equipo. Quedan: {', '.join(new_team) or 'ninguno (el manager usará todos)'}."
    # --add id1 id2 ... (insert/appendix al equipo actual)
    if raw.startswith("--add ") or raw.strip() == "--add":
        ids_str = raw[6:].strip() if raw.startswith("--add ") else ""
        ids_raw = [x.strip() for x in ids_str.split() if x.strip()]
        valid = []
        invalid = []
        for i in ids_raw:
            c = _resolve_template_id(all_templates, i)
            if c:
                valid.append(c)
            else:
                invalid.append(i)
        if invalid:
            return f"Templates no encontrados: {', '.join(invalid)}. Disponibles: {', '.join(all_templates)}"
        current = list(team) if team else list(all_templates)
        for c in valid:
            if not any((x or "").strip().lower() == c.lower() for x in current):
                current.append(c)
        set_team_templates(db, chat_id, current)
        _sync_tenant_team_if_admin(
            db, tenant_id=tid, requester_id=requester_id, template_ids=current
        )
        return f"✅ Añadidos al equipo: {', '.join(valid)}. Equipo: {', '.join(current)}."
    # id1 id2 ... → reemplazar equipo
    ids_raw = [x.strip() for x in raw.split() if x.strip()]
    valid = []
    invalid = []
    for i in ids_raw:
        c = _resolve_template_id(all_templates, i)
        if c:
            valid.append(c)
        else:
            invalid.append(i)
    if invalid:
        return f"Templates no encontrados: {', '.join(invalid)}. Disponibles: {', '.join(all_templates)}"
    set_team_templates(db, chat_id, valid)
    _sync_tenant_team_if_admin(db, tenant_id=tid, requester_id=requester_id, template_ids=valid)
    return f"✅ Equipo de este chat: {', '.join(valid)}. El manager delegará solo a estos."


def _dedicated_gateway_db_path_for_vault() -> str | None:
    """
    Misma regla que el API Gateway: api_gateways_pm2.json + claves multiplex / DUCKDB_PATH
    (evita /vault y fly mostrando finanzdb1 del registry en gateways dedicados).
    """
    from duckclaw.pm2_gateway_db import dedicated_gateway_db_path_resolved

    return dedicated_gateway_db_path_resolved()


def _session_duckdb_path_for_fly(db: Any) -> str | None:
    """Ruta del ``DuckClaw``/sesión que abrió el gateway para el turno (multiplex por bot)."""
    p = getattr(db, "_path", None)
    if p is None:
        return None
    s = str(p).strip()
    if not s or s == ":memory:":
        return None
    try:
        from pathlib import Path as _P

        return str(_P(s).expanduser().resolve())
    except Exception:
        return None


def _fly_vault_label_for_tenant(tenant_id: Any) -> str:
    tid = str(tenant_id or "").strip()
    if not tid or tid.lower() == "default":
        return _dedicated_gateway_vault_label()
    pretty = {
        "Finanzas": "Finanz",
        "SIATA": "SIATA Analyst",
        "Trabajo": "Job Hunter",
    }
    return pretty.get(tid, tid)


def _dedicated_gateway_vault_label() -> str:
    proc = (os.environ.get("DUCKCLAW_PM2_PROCESS_NAME") or "").strip()
    matched = (os.environ.get("DUCKCLAW_PM2_MATCHED_APP_NAME") or "").strip()
    pretty = {
        "BI-Analyst-Gateway": "BI Analyst",
        "SIATA-Gateway": "SIATA Analyst",
        "Finanz-Gateway": "Finanz",
    }
    for key in (proc, matched):
        if key in pretty:
            return pretty[key]
    fallback = proc or matched
    if fallback:
        return fallback.replace("-Gateway", "").replace("-", " ").strip() or "este gateway"
    return "este gateway"


def _format_vault_size_mb(size_bytes: int | float) -> str:
    """Tamaño para mensajes /vault (1 MB = 1024² bytes, dos decimales)."""
    try:
        b = max(0, int(size_bytes))
    except (TypeError, ValueError):
        b = 0
    mb = b / (1024 * 1024)
    return f"{mb:.2f} MB"


def _template_bound_vault_path(worker_id: str | None, vault_user_id: Any) -> str | None:
    """Ruta absoluta si la plantilla declara ``forge_context.vault_binding``."""
    wid = (worker_id or "").strip()
    if not wid or wid.lower() in ("manager", "default", "entry_router", "manager_router"):
        return None
    try:
        from duckclaw.vaults import resolve_template_vault_path
        from duckclaw.workers.manifest import load_manifest

        spec = load_manifest(wid)
        return resolve_template_vault_path(spec.forge_vault_binding, vault_user_id)
    except Exception:
        return None


def execute_vault(
    args: str,
    *,
    vault_user_id: Any,
    tenant_id: Any = None,
    db: Any | None = None,
    entry_worker_id: str | None = None,
    chat_id: Any | None = None,
) -> str:
    user_id = (str(vault_user_id or "").strip() or "default")
    vault_scope = vault_scope_id_for_tenant(tenant_id)
    raw = (args or "").strip()
    session_db_path = _session_duckdb_path_for_fly(db) if db is not None else None
    template_db: str | None = None
    template_worker = ""
    if not session_db_path:
        wid = (entry_worker_id or "").strip()
        if not wid and db is not None and chat_id is not None:
            wid = (get_worker_id_for_chat(db, chat_id) or "").strip()
        template_db = _template_bound_vault_path(wid, user_id)
        if template_db:
            template_worker = wid
    fixed_db = session_db_path or template_db or _dedicated_gateway_db_path_for_vault()
    if fixed_db:
        from pathlib import Path as _P

        fp = _P(fixed_db).expanduser().resolve()
        if session_db_path:
            label = _fly_vault_label_for_tenant(tenant_id)
        elif template_db:
            label = f"plantilla {template_worker}" if template_worker else "plantilla"
        else:
            label = _dedicated_gateway_vault_label()
        if not raw:
            size = 0
            try:
                size = fp.stat().st_size if fp.exists() else 0
            except Exception:
                pass
            tid_req = str(tenant_id or "").strip()
            if tid_req and tid_req.lower() != "default":
                gtid = tid_req
            else:
                gtid = (os.environ.get("DUCKCLAW_GATEWAY_TENANT_ID") or "").strip()
            extra = f"\nTenant: {gtid}" if gtid else ""
            return (
                f"🗄 BD de este gateway ({label}): {fp.name}\n"
                f"Ruta: {fp}\nTamaño: {_format_vault_size_mb(size)}{extra}"
            )
        tokens = raw.split()
        cmd = (tokens[0] or "").strip().lower()
        if cmd.startswith("--"):
            cmd = cmd[2:]
        if cmd in ("list", "new", "use", "rm"):
            hint = (
                "Los comandos /vault list|new|use|rm son del registry multi-bóveda en Finanz; "
                "aquí no aplican. Usa /vault sin argumentos para ver la ruta."
            )
            if template_db:
                hint = (
                    "La bóveda está fijada en manifest.yaml (forge_context.vault_binding). "
                    "Cámbiala en Plantillas → Bóveda DuckDB. " + hint
                )
            return f"En este contexto ({label}) solo aplica la BD anterior. {hint}"
        return (
            f"Usa /vault sin argumentos para ver la BD de {label}. "
            "Comandos adicionales del registry no aplican en este gateway."
        )
    if not raw:
        active_id, active_path = _vault_resolve_active(user_id, vault_scope)
        size = 0
        try:
            from pathlib import Path as _P
            p = _P(active_path)
            size = p.stat().st_size if p.exists() else 0
        except Exception:
            pass
        return (
            f"🗄 Bóveda activa: {active_id}\nRuta: {active_path}\nTamaño: {_format_vault_size_mb(size)}\n\n"
            "Comandos: /vault list | /vault --list | /vault new <name> | /vault --new <name> | "
            "/vault use <id> | /vault --use <id> | /vault rm <id> | /vault --rm <id>"
        
        )
    tokens = raw.split()
    cmd = (tokens[0] or "").strip().lower()
    # Compatibilidad: permitir flags estilo --list/--use/--new/--rm
    if cmd.startswith("--"):
        cmd = cmd[2:]
    if cmd == "list":
        rows = _vault_list(user_id, vault_scope)
        if not rows:
            return "No hay bóvedas."
        lines = []
        for r in rows:
            mark = "✅" if r.get("is_active") else "•"
            sz = int(r.get("size_bytes", 0) or 0)
            lines.append(
                f"{mark} {r.get('vault_id')} ({r.get('vault_name')}) - {_format_vault_size_mb(sz)}"
            )
        return "🗄 Bóvedas:\n" + "\n".join(lines)
    if cmd == "new":
        name = " ".join(tokens[1:]).strip()
        if not name:
            return "Uso: /vault new <name> | /vault --new <name>"
        created = _vault_create(user_id, name, vault_scope)
        return f"✅ Bóveda creada: {created.get('vault_id')} ({created.get('vault_name')})"
    if cmd == "use":
        vid = " ".join(tokens[1:]).strip()
        if not vid:
            return "Uso: /vault use <vault_id> | /vault --use <vault_id>"
        ok = _vault_switch(user_id, vid, vault_scope)
        if not ok:
            return f"No existe la bóveda '{vid}'. Usa /vault list."
        active_id, _ = _vault_resolve_active(user_id, vault_scope)
        return f"✅ Bóveda activa actual: {active_id}"
    if cmd == "rm":
        vid = " ".join(tokens[1:]).strip()
        if not vid:
            return "Uso: /vault rm <vault_id> | /vault --rm <vault_id>"
        ok = _vault_remove(user_id, vid, vault_scope)
        if not ok:
            return f"No existe la bóveda '{vid}'."
        active_id, _ = _vault_resolve_active(user_id, vault_scope)
        return f"🗑 Bóveda eliminada: {vid}. Activa actual: {active_id}"
    return (
        "Uso: /vault | /vault list | /vault --list | /vault new <name> | /vault --new <name> | "
        "/vault use <vault_id> | /vault --use <vault_id> | /vault rm <vault_id> | /vault --rm <vault_id>"
    


    )
def _team_whitelist_audit_enabled() -> bool:
    v = (os.environ.get("DUCKCLAW_TEAM_WHITELIST_DEBUG") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _audit_team_whitelist_rw(message: str, **data: Any) -> None:
    if not _team_whitelist_audit_enabled():
        return
    logging.getLogger("duckclaw.team_whitelist").info("%s %s", message, data)


def _paths_same_duckdb_file(a: str, b: str) -> bool:
    if not (a or "").strip() or not (b or "").strip():
        return False
    pa = Path(str(a).strip()).expanduser().resolve()
    pb = Path(str(b).strip()).expanduser().resolve()
    if str(pa) == str(pb):
        return True
    try:
        return bool(pa.samefile(pb))
    except OSError:
        return False


def _try_duckdb_checkpoint_rw(db: Any) -> None:
    if getattr(db, "_read_only", True):
        return
    try:
        db.execute("CHECKPOINT")
    except Exception:
        pass


def _team_whitelist_db(fly_db: Any) -> Any:
    """
    Whitelist ``main.authorized_users`` se lee de la misma DuckDB que el hub
    (``get_gateway_db_path()``), vía ``get_db()`` (conexión RO efímera).

    Excepción: en el API Gateway el bloque fly ya abrió ``fly_db`` en RW sobre ese
    archivo; abrir un segundo ``duckdb.connect(..., read_only=True)`` en paralelo
    puede lanzar ``ConnectionException``. En ese caso reutilizamos ``fly_db``.
    """
    try:
        from duckclaw.gateway_db import get_gateway_db_path  # noqa: PLC0415
        from duckclaw.graphs.graph_server import get_db as _gw_acl_db  # noqa: PLC0415

        gw = str(Path(get_gateway_db_path()).resolve())
        fp = ""
        try:
            fpraw = getattr(fly_db, "_path", "") or ""
            if fpraw and str(fpraw).strip() not in ("", ":memory:"):
                fp = str(Path(str(fpraw)).expanduser().resolve())
        except Exception:
            fp = ""
        same = _paths_same_duckdb_file(fp, gw) if fp else False
        fly_rw = getattr(fly_db, "_read_only", True) is False
        if same and fly_rw and hasattr(fly_db, "query"):
            return fly_db
        return _gw_acl_db()
    except Exception:
        return fly_db


def _authorized_users_rw_connection(fly_db: Any) -> tuple[Any, Callable[[], None]]:
    """
    ``graph_server.get_db()`` es RO efímero: ``execute`` no persiste. Las mutaciones
    de whitelist deben usar DuckClaw RW sobre ``get_gateway_db_path()`` o reutilizar
    ``fly_db`` si ya apunta al mismo archivo en modo RW (p. ej. bot Finanz).
    """
    from duckclaw import DuckClaw
    from duckclaw.gateway_db import GatewayDbEphemeralReadonly, get_gateway_db_path

    acl_ro = _team_whitelist_db(fly_db)
    if not isinstance(acl_ro, GatewayDbEphemeralReadonly):
        _audit_team_whitelist_rw(
            "rw_connection",
            branch="direct_acl_not_ephemeral",
            acl_type=type(acl_ro).__name__,
        )

        def _noop() -> None:
            return None

        return acl_ro, _noop

    gw = str(Path(get_gateway_db_path()).resolve())
    fly_resolved = ""
    try:
        fp = getattr(fly_db, "_path", "") or ""
        if fp and str(fp).strip() not in ("", ":memory:"):
            fly_resolved = str(Path(str(fp)).expanduser().resolve())
    except Exception:
        fly_resolved = ""

    reuse_fly = _paths_same_duckdb_file(fly_resolved, gw) and getattr(fly_db, "_read_only", True) is False

    _audit_team_whitelist_rw(
        "rw_connection",
        branch="gateway_ephemeral_acl",
        reuse_fly=reuse_fly,
        gw_tail=gw[-64:] if gw else "",
        fly_tail=fly_resolved[-64:] if fly_resolved else "",
        fly_read_only=getattr(fly_db, "_read_only", None),
    )

    if reuse_fly:

        def _noop_fly() -> None:
            return None

        return fly_db, _noop_fly

    # Mismo motor que GatewayDbEphemeralReadonly (duckdb Python). Si usamos C++ nativo en RW,
    # /team --add puede persistir pero /team (lectura RO Python) no ve las filas.
    _audit_team_whitelist_rw("rw_connection", branch="duckclaw_gw_python_engine", gw_tail=gw[-64:] if gw else "")
    rw = DuckClaw(gw, read_only=False, engine="python")

    def _close_rw() -> None:
        try:
            rw.close()
        except Exception:
            pass

    return rw, _close_rw


def execute_team_whitelist(db: Any, tenant_id: Any, requester_id: Any, args: str) -> str:
    """
    Telegram Guard spec: /team lista y muta authorized_users por tenant.
    - /team                           -> lista autorizados (para tenant)
    - /team --add <user_id> [nombre] [admin|user] (también nombre primero si el id es numérico)
    - /team --rm <user_id>            (admin u owner)
    """
    acl = _team_whitelist_db(db)
    tid = str(tenant_id or "default").strip() or "default"
    rid = str(requester_id or "").strip()

    raw = (args or "").strip()
    if _is_wr_tenant(tid):
        _ensure_war_room_tables(acl)
        requester_clearance = _wr_member_clearance(acl, tenant_id=tid, user_id=rid)

        if not raw:
            rows_raw = acl.query(
                "SELECT user_id, username, clearance_level FROM war_room_core.wr_members "
                f"WHERE lower(tenant_id)=lower('{_sql_escape_literal(tid, 128)}') ORDER BY user_id"
            )
            rows = json.loads(rows_raw) if isinstance(rows_raw, str) else (rows_raw or [])
            if not rows:
                return f"No hay miembros WR para tenant '{tid}'."
            lines_wr: list[str] = []
            seen_wr: set[str] = set()
            for r in rows:
                if not isinstance(r, dict):
                    continue
                uid = str(r.get("user_id") or "").strip()
                if not uid or uid in seen_wr:
                    continue
                seen_wr.add(uid)
                uname = str(r.get("username") or "").strip()
                clr = str(r.get("clearance_level") or "").strip().lower() or "observer"
                label = _player_label(uname, uid, db=acl, tenant_id=tid)
                lines_wr.append(f"- {label} ({uid}) · clearance: {clr}")
            body_wr = "\n".join(lines_wr)
            return f"🛡 Miembros War Room (tenant '{tid}'):\n{body_wr}"

        if raw.startswith("--rm "):
            if not (_is_gateway_owner_user(rid) or requester_clearance == "admin"):
                return "❌ Acceso denegado: solo admin WR puede eliminar miembros."
            tokens = [t for t in raw[5:].strip().split() if t.strip()]
            if not tokens:
                return "Uso WR: /team --rm <user_id>"
            target_uid = tokens[0]
            acl.execute(
                "DELETE FROM war_room_core.wr_members "
                f"WHERE lower(tenant_id)=lower('{_sql_escape_literal(tid, 128)}') "
                f"AND user_id='{_sql_escape_literal(target_uid, 128)}'"
            )
            _invalidate_wr_clearance_redis_cache(tenant_id=tid, user_id=target_uid)
            _wr_append_audit(
                acl,
                tenant_id=tid,
                sender_id=rid or "system",
                target_agent="manager",
                event_type="REMOVE_WR_MEMBER",
                payload=f"user_id={target_uid}",
            )
            target_label = _player_label("", target_uid, db=acl, tenant_id=tid)
            return f"✅ Miembro WR eliminado: {target_label}."

        if raw.startswith("--add ") or raw.strip() == "--add":
            if not (_is_gateway_owner_user(rid) or requester_clearance == "admin"):
                return "❌ Acceso denegado: solo admin WR puede agregar miembros."
            ids_part = raw[6:].strip() if raw.startswith("--add ") else ""
            tokens = [t for t in ids_part.split() if t.strip()]
            if not tokens:
                return "Uso WR: /team --add <user_id> [username] [admin|operator|observer]"
            target_uid = tokens[0]
            clearance = "observer"
            if len(tokens) >= 2 and tokens[-1].lower() in ("admin", "operator", "observer"):
                clearance = tokens[-1].lower()
                tokens = tokens[:-1]
            username = " ".join(tokens[1:]).strip() if len(tokens) > 1 else "Usuario"
            acl.execute(
                "INSERT INTO war_room_core.wr_members (tenant_id, user_id, username, clearance_level) "
                f"VALUES ('{_sql_escape_literal(tid, 128)}', '{_sql_escape_literal(target_uid, 128)}', "
                f"'{_sql_escape_literal(username or 'Usuario', 128)}', '{_sql_escape_literal(clearance, 32)}') "
                "ON CONFLICT (tenant_id, user_id) DO UPDATE SET "
                "username=EXCLUDED.username, clearance_level=EXCLUDED.clearance_level, added_at=now()"
            )
            _invalidate_wr_clearance_redis_cache(tenant_id=tid, user_id=target_uid)
            _wr_append_audit(
                acl,
                tenant_id=tid,
                sender_id=rid or "system",
                target_agent="manager",
                event_type="REGISTER_WR_MEMBER",
                payload=f"user_id={target_uid} clearance={clearance}",
            )
            target_label = _player_label(username, target_uid, db=acl, tenant_id=tid)
            return f"✅ Miembro WR registrado: {target_label} ({clearance})."

        return (
            "Uso WR: /team | /team --add <user_id> [username] [admin|operator|observer] | /team --rm <user_id>"
        )

    if not raw:
        users = _dedupe_authorized_users_by_user_id(_list_authorized_users(acl, tenant_id=tid))
        if not users:
            hint = ""
            if _is_gateway_owner_user(rid):
                hint = (
                    " Como eres el owner del gateway (DUCKCLAW_OWNER_ID o DUCKCLAW_ADMIN_CHAT_ID), puedes ejecutar "
                    "`/team --add <user_id> [nombre] [admin]` para dar de alta."
                )
            return f"No hay usuarios autorizados para tenant '{tid}'.{hint}"
        body_lines: list[str] = []
        for u in users:
            uid = str(u.get("user_id") or "").strip()
            uname = str(u.get("username") or "").strip()
            role = (u.get("role") or "user").strip().lower() or "user"
            label = _player_label(uname, uid, db=acl, tenant_id=tid)
            body_lines.append(f"- {label} ({uid}) · rol: {role}")
        return f"🦆 Usuarios autorizados (tenant '{tid}'):\n" + "\n".join(body_lines)

    if raw.startswith("--rm "):
        if not rid:
            return "❌ Acceso denegado."
        if not _is_team_admin(acl, tenant_id=tid, requester_id=rid):
            return "❌ Acceso denegado: solo administradores pueden eliminar usuarios."
        target_uid = raw[5:].strip().split()[0]
        if not target_uid:
            return "Uso: /team --rm <user_id>"
        mut_db, mut_close = _authorized_users_rw_connection(db)
        try:
            _delete_authorized_user(mut_db, tenant_id=tid, user_id=target_uid)
            _try_duckdb_checkpoint_rw(mut_db)
        finally:
            mut_close()
        _invalidate_whitelist_redis_cache(tenant_id=tid, user_id=target_uid)
        target_label = _player_label("", target_uid, db=acl, tenant_id=tid)
        return f"✅ Eliminado {target_label} del tenant '{tid}'."

    if raw.startswith("--add ") or raw.strip() == "--add":
        if not rid:
            return "❌ Acceso denegado."
        if not _is_team_admin(acl, tenant_id=tid, requester_id=rid):
            return "❌ Acceso denegado: solo administradores pueden agregar usuarios."
        ids_part = raw[6:].strip() if raw.startswith("--add ") else ""
        tokens = [t for t in ids_part.split() if t.strip()]
        if not tokens:
            return "Uso: /team --add <user_id> [nombre] [admin|user]"
        role_out = "user"
        if len(tokens) >= 2 and tokens[-1].lower() == "admin":
            role_out = "admin"
            tokens = tokens[:-1]
        if len(tokens) >= 2 and tokens[-1].lower() == "user":
            tokens = tokens[:-1]
        if not tokens:
            return "Uso: /team --add <user_id> [nombre] [admin|user]"
        target_uid, uname = _resolve_team_add_uid_and_username(tokens)
        if not (target_uid or "").strip():
            return "Uso: /team --add <user_id> [nombre] [admin|user]"
        mut_db, mut_close = _authorized_users_rw_connection(db)
        try:
            _upsert_authorized_user(mut_db, tenant_id=tid, user_id=target_uid, username=uname, role=role_out)
            _try_duckdb_checkpoint_rw(mut_db)
        finally:
            mut_close()
        _invalidate_whitelist_redis_cache(tenant_id=tid, user_id=target_uid)
        target_label = _player_label(uname, target_uid, db=acl, tenant_id=tid)
        return f"✅ Añadido {target_label} (role={role_out}) al tenant '{tid}'."

    if raw == "--shared-list" or raw.startswith("--shared-list"):
        if not rid:
            return "❌ Acceso denegado."
        if not _is_team_admin(acl, tenant_id=tid, requester_id=rid):
            return "❌ Acceso denegado: solo administradores pueden listar permisos de bases compartidas."
        from duckclaw.shared_db_grants import list_shared_grants_for_tenant

        grants = list_shared_grants_for_tenant(acl, tenant_id=tid)
        if not grants:
            return (
                f"🗂 No hay filas en user_shared_db_access para tenant '{tid}'. "
                "Sin filas, cualquier usuario whitelist puede usar rutas shared válidas (compat). "
                "Admin: /team --shared-grant <user_id> <resource_key> (ej. default o *)."
            )
        grant_lines: list[str] = []
        for g in grants:
            grant_lines.append(
                f"- user={g.get('user_id')} key={g.get('resource_key')} at={g.get('created_at')}"
            )
        return f"🗂 Bases compartidas permitidas (tenant '{tid}'):\n\n" + "\n".join(grant_lines)

    if raw.startswith("--shared-grant "):
        if not rid:
            return "❌ Acceso denegado."
        if not _is_team_admin(acl, tenant_id=tid, requester_id=rid):
            return "❌ Acceso denegado: solo administradores."
        rest = raw[len("--shared-grant ") :].strip().split(None, 1)
        if len(rest) < 2:
            return (
                "Uso: /team --shared-grant <user_id> <resource_key>\n"
                "resource_key: default, * (todas), o slug (env DUCKCLAW_SHARED_RESOURCE_<SLUG>)."
            )
        target_uid, rkey = rest[0], rest[1].strip()
        from duckclaw.shared_db_grants import upsert_shared_grant, validate_resource_key

        if not validate_resource_key(rkey):
            return "resource_key inválido (usa default, * o slug alfanumérico)."
        upsert_shared_grant(acl, tenant_id=tid, user_id=target_uid, resource_key=rkey)
        return f"✅ Grant shared '{rkey}' → user {target_uid} (tenant '{tid}')."

    if raw.startswith("--shared-revoke "):
        if not rid:
            return "❌ Acceso denegado."
        if not _is_team_admin(acl, tenant_id=tid, requester_id=rid):
            return "❌ Acceso denegado: solo administradores."
        rest = raw[len("--shared-revoke ") :].strip().split(None, 1)
        if len(rest) < 2:
            return "Uso: /team --shared-revoke <user_id> <resource_key>"
        target_uid, rkey = rest[0], rest[1].strip()
        from duckclaw.shared_db_grants import delete_shared_grant, validate_resource_key

        if not validate_resource_key(rkey):
            return "resource_key inválido."
        delete_shared_grant(acl, tenant_id=tid, user_id=target_uid, resource_key=rkey)
        return f"✅ Revocado shared '{rkey}' para user {target_uid}."

    return (
        "Uso: /team | /team --add ... | /team --rm ... | /team --shared-list | "
        "/team --shared-grant <user_id> <resource_key> | /team --shared-revoke <user_id> <resource_key>"
    )


def execute_roles(db: Any, chat_id: Any) -> str:
    """/roles: lista todos los trabajadores virtuales (templates) disponibles. El manager solo delegará a los que estén en /workers."""
    from duckclaw.workers.factory import list_workers
    all_templates = list_workers()
    if not all_templates:
        return "No hay templates en forge/templates. Añade al menos uno."
    lines = "\n".join(f"- {w}" for w in all_templates)
    return format_guardrail("fly_commands", "roles_list_intro", lines=lines)


# Worker por defecto: el manager orquesta y delega a los trabajadores en forge/templates
_DEFAULT_WORKER = "manager"


def execute_role_switch(db: Any, chat_id: Any, worker_id: str) -> str:
    """/role <worker_id>: cambia el rol. Por defecto 'manager' delega a los templates. Sin args: muestra rol actual y disponibles."""
    from duckclaw.workers.factory import list_workers
    available = list_workers()  # solo templates (finanz, research_worker, etc.)
    wid_raw = (worker_id or "").strip()
    if not wid_raw:
        current = get_chat_state(db, chat_id, "worker_id") or _DEFAULT_WORKER
        if current == "manager":
            current_display = "Manager (delega a trabajadores en templates)"
        else:
            try:
                from duckclaw.workers.manifest import load_manifest
                spec = load_manifest(current)
                current_display = f"{spec.name} ({current})"
            except Exception:
                current_display = current
        avail_str = "\n".join(f"- {w}" for w in available) if available else "ninguna"
        return (
            f"🦆 Rol: {current_display}\n\n"
            f"Disponibles: manager (por defecto)\n{avail_str}\n/role <id>"
        )
    if wid_raw.lower() == "manager":
        set_chat_state(db, chat_id, "worker_id", "manager")
        return "✅ Manager. Delega a los trabajadores en templates."
    canonical = _resolve_template_id(available, wid_raw)
    if not canonical:
        avail_str = "\n".join(f"- {w}" for w in available) if available else "ninguna"
        return f"Rol '{wid_raw}' no existe.\nDisponibles:\n{avail_str}"
    try:
        from duckclaw.workers.manifest import load_manifest
        spec = load_manifest(canonical)
        set_chat_state(db, chat_id, "worker_id", canonical)
        skills = ", ".join(spec.skills_list or []) or "read_sql, admin_sql"
        return f"✅ {spec.name} ({canonical}). Herramientas: {skills}"
    except Exception as e:
        return f"Error al cargar rol: {e}."


def execute_skills_list(db: Any, chat_id: Any, args: str) -> str:
    """/skills <worker_id>: lista herramientas del template. worker_id debe ser uno de /roles."""
    from duckclaw.workers.factory import list_workers
    available = list_workers()
    wid_raw = (args or "").strip()
    if not wid_raw:
        return "Uso: /skills <worker_id>. Ver templates: /roles"
    if wid_raw.startswith("--"):
        return "Indica un worker_id (ej. finanz, research_worker). Ver templates: /roles"
    canonical = _resolve_template_id(available, wid_raw)
    if not canonical:
        return f"Template '{wid_raw}' no encontrado. Disponibles (usa /roles): {', '.join(available)}"
    try:
        from duckclaw.workers.manifest import load_manifest
        spec = load_manifest(canonical)
        skill_lines = [f"- {s}" for s in (spec.skills_list or [])]
        skill_lines.append("- read_sql (solo lectura)")
        skill_lines.append("- admin_sql (lectura + escrituras)")
        return f"🔧 {spec.name} ({canonical})\n" + "\n".join(skill_lines)
    except Exception as e:
        return f"Error: {e}."


def execute_forget(db: Any, chat_id: Any) -> str:
    """/forget: borra historial de la conversación y reinicia estado."""
    try:
        cid = int(chat_id)
        # Telegram: chat_id is numeric, use telegram_conversation
        db.execute(f"DELETE FROM telegram_conversation WHERE chat_id = {cid}")
    except (TypeError, ValueError):
        # API gateway: session_id is string (e.g. "default"), use api_conversation
        sid = str(chat_id).replace("'", "''")[:256]
        try:
            db.execute(f"DELETE FROM api_conversation WHERE session_id = '{sid}'")
        except Exception:
            pass  # Table may not exist if only Telegram used
    try:
        set_chat_state(db, chat_id, "last_audit", "")
    except Exception:
        pass
    if os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true":
        try:
            import langsmith
            # Log evento Habeas Data (opcional: run_id no disponible aquí)
            pass
        except Exception:
            pass
    return "✅ Historial borrado."



def execute_context_toggle(db: Any, chat_id: Any, on_off: str) -> str:
    """/context on|off: activa o desactiva inyección de memoria a largo plazo."""
    v = (on_off or "").strip().lower()
    if v in ("on", "1", "true", "sí", "si"):
        set_chat_state(db, chat_id, "use_rag", "true")
        return "✅ Contexto largo activado (más mensajes en historial)."
    if v in ("off", "0", "false"):
        set_chat_state(db, chat_id, "use_rag", "false")
        return "✅ Contexto largo desactivado (solo historial reciente)."
    current = get_chat_state(db, chat_id, "use_rag")
    return (
        "Uso: `/context on` | `/context off` | `/context --add` [texto o pie de foto en imagen/álbum] | "
        "`/context --summary` (`--summarize`)\n"
        f"Estado actual (historial largo): {'on' if current != 'false' else 'off'}."
    )


def execute_sandbox_toggle(db: Any, chat_id: Any, on_off: str) -> str:
    """/sandbox on|off: habilita/deshabilita ejecución de código para este chat (por `agent_config`)."""
    v = (on_off or "").strip().lower()

    def _parse(v_: str) -> Optional[bool]:
        vv = (v_ or "").strip().lower()
        if vv in ("on", "1", "true", "sí", "si"):
            return True
        if vv in ("off", "0", "false"):
            return False
        return None

    parsed = _parse(v)
    if parsed is True:
        set_chat_state(db, chat_id, "sandbox_enabled", "true")
        db_path = getattr(db, "_path", None) or getattr(db, "path", None) or "(unknown_db_path)"
        # Warning para asegurar que aparezca en logs de pm2.
        import logging
        logging.getLogger(__name__).warning(
            "[sandbox-toggle] db_path=%r chat_id=%r sandbox_enabled=%r",
            db_path,
            chat_id,
            "true",
        )
        return "Entendido. He habilitado mis capacidades de ejecución de código para esta sesión."
    if parsed is False:
        set_chat_state(db, chat_id, "sandbox_enabled", "false")
        db_path = getattr(db, "_path", None) or getattr(db, "path", None) or "(unknown_db_path)"
        import logging
        logging.getLogger(__name__).warning(
            "[sandbox-toggle] db_path=%r chat_id=%r sandbox_enabled=%r",
            db_path,
            chat_id,
            "false",
        )
        return "Entendido. He desactivado mis capacidades de ejecución de código para esta sesión."

    # Sin args válidos: mostrar estado actual.
    current = _parse(get_chat_state(db, chat_id, "sandbox_enabled"))
    status = "habilitado" if current is True else "desactivado"  # default OFF
    return f"Uso: /sandbox on|off\nEstado actual: {status}."


def _parse_ibkr_toggle_args(args: str) -> tuple[Optional[bool], Optional[str], Optional[str]]:
    """
    ``/ibkr on --mode paper|live`` | ``/ibkr off``.
    Retorna (on|off|None, mode|None, error|None).
    """
    tokens = (args or "").strip().split()
    if not tokens:
        return None, None, None
    head = tokens[0].strip().lower()
    on_off: Optional[bool]
    if head in ("on", "1", "true", "sí", "si"):
        on_off = True
    elif head in ("off", "0", "false"):
        on_off = False
    else:
        return None, None, "Uso: /ibkr on --mode paper|live | /ibkr off"
    mode: Optional[str] = None
    i = 1
    while i < len(tokens):
        if tokens[i] == "--mode" and i + 1 < len(tokens):
            mode = tokens[i + 1].strip().lower()
            i += 2
            continue
        i += 1
    if on_off is True:
        if mode not in ("paper", "live"):
            return True, None, "Con /ibkr on debes indicar --mode paper o --mode live."
    return on_off, mode, None


def execute_ibkr_toggle(db: Any, chat_id: Any, args: str) -> str:
    """/ibkr on --mode paper|live | /ibkr off: portfolio IBKR por sesión (Finanz)."""
    on_off, mode, err = _parse_ibkr_toggle_args(args)
    if err:
        return err
    if on_off is True:
        set_chat_state(db, chat_id, "ibkr_enabled", "true")
        set_chat_state(db, chat_id, "ibkr_portfolio_mode", str(mode or "paper"))
        label = "paper" if mode == "paper" else "live"
        return (
            f"IBKR portfolio activado para esta sesión (modo {label}). "
            "Finanz puede usar get_ibkr_portfolio en este chat."
        )
    if on_off is False:
        set_chat_state(db, chat_id, "ibkr_enabled", "false")
        return "IBKR portfolio desactivado para esta sesión. Finanz no llamará get_ibkr_portfolio hasta /ibkr on."
    enabled = (get_chat_state(db, chat_id, "ibkr_enabled") or "").strip().lower() in (
        "true",
        "1",
        "on",
        "sí",
        "si",
    )
    cur_mode = (get_chat_state(db, chat_id, "ibkr_portfolio_mode") or "—").strip() or "—"
    status = f"on ({cur_mode})" if enabled else "off"
    return (
        "Uso: /ibkr on --mode paper|live | /ibkr off\n"
        f"Estado actual: {status}."
    )


def execute_internet_toggle(
    db: Any,
    chat_id: Any,
    on_off: str,
    *,
    worker_id: str = "",
    tenant_id: str = "default",
) -> str:
    """/internet on|off: red del sandbox Strix por chat (solo si el worker permite red en YAML)."""
    from duckclaw.forge.schema import resolve_sandbox_network_policy

    v = (on_off or "").strip().lower()
    wid = (worker_id or "").strip()
    if not wid:
        try:
            team = get_effective_team_templates(db, chat_id, str(tenant_id or "default").strip() or "default", None)
            wid = (team[0] if team else "").strip()
        except Exception:
            wid = ""
    if not wid:
        wid = "default"

    _, meta = resolve_sandbox_network_policy(
        wid, get_chat_state(db, chat_id, "sandbox_network_enabled")
    )
    if not meta.get("toggle_available"):
        return (
            f"Este worker («{wid}») tiene red sandbox denegada en security_policy.yaml. "
            "No se puede activar internet desde el chat. Usa tavily_search o un worker con browser_sandbox "
            "(finanz, Job-Hunter)."
        )

    def _parse(v_: str) -> bool | None:
        vv = (v_ or "").strip().lower()
        if vv in ("on", "1", "true", "sí", "si"):
            return True
        if vv in ("off", "0", "false"):
            return False
        return None

    parsed = _parse(v)
    if parsed is True:
        ok, err = set_chat_state_via_vault(db, chat_id, "sandbox_network_enabled", "true", tenant_id=tenant_id)
        if not ok:
            return f"No se pudo guardar: {err}"
        try:
            from duckclaw.graphs.sandbox import cleanup_sandbox_session_for_chat

            cleanup_sandbox_session_for_chat(str(chat_id))
        except Exception:
            pass
        return (
            "Internet en sandbox activado para esta sesión. "
            "El próximo run_sandbox/run_browser_sandbox usará red bridge."
        )
    if parsed is False:
        ok, err = set_chat_state_via_vault(db, chat_id, "sandbox_network_enabled", "false", tenant_id=tenant_id)
        if not ok:
            return f"No se pudo guardar: {err}"
        try:
            from duckclaw.graphs.sandbox import cleanup_sandbox_session_for_chat

            cleanup_sandbox_session_for_chat(str(chat_id))
        except Exception:
            pass
        return "Internet en sandbox desactivado (network_mode=none) para esta sesión."

    eff = meta.get("effective") or "deny"
    return f"Uso: /internet on|off\nRed sandbox efectiva: {eff} (worker {wid})."


def execute_heartbeat(db: Any, chat_id: Any, on_off: str, *, tenant_id: Any = None) -> str:
    """/heartbeat on|off — DM proactivos (Bot API nativa o webhook) mientras el agente usa herramientas."""
    from duckclaw.graphs.chat_heartbeat import (
        heartbeat_outbound_configured,
        heartbeat_redis_configured,
        is_admin_ui_chat_session,
        is_chat_heartbeat_enabled,
        set_chat_heartbeat_enabled,
    )

    tid = str(tenant_id or "default").strip() or "default"
    cid = str(chat_id if chat_id is not None else "unknown").strip() or "unknown"
    v = (on_off or "").strip().lower()

    if not heartbeat_redis_configured():
        return (
            "Heartbeat requiere Redis (REDIS_URL o DUCKCLAW_REDIS_URL). Sin eso no se puede guardar el estado."
        

        )
    if v in ("on", "1", "true", "sí", "si"):
        if is_chat_heartbeat_enabled(tid, cid):
            return "✅ Heartbeat ya estaba activado."
        ok, err = set_chat_heartbeat_enabled(tid, cid, True)
        if not ok:
            return f"No se pudo activar heartbeat: {err}"
        if is_admin_ui_chat_session(cid):
            return "✅ Heartbeat activado. Verás plan y herramientas en este chat mientras trabajo."
        if not heartbeat_outbound_configured():
            return (
                "Heartbeat activado en Redis, pero falta TELEGRAM_BOT_TOKEN (recomendado) o un webhook "
                "(TELEGRAM_BOT_TOKEN o DUCKCLAW_HEARTBEAT_WEBHOOK_URL); no se enviarán DMs."
            )
        return "✅ Heartbeat activado. Te avisaré por DM mientras uso herramientas."
    if v in ("off", "0", "false"):
        if not is_chat_heartbeat_enabled(tid, cid):
            return "Heartbeat ya estaba desactivado."
        ok, err = set_chat_heartbeat_enabled(tid, cid, False)
        if not ok:
            return f"No se pudo desactivar heartbeat: {err}"
        return "✅ Heartbeat desactivado."

    st = "on" if is_chat_heartbeat_enabled(tid, cid) else "off"
    return f"Heartbeat: {st}\nUso: /heartbeat on | /heartbeat off"


def execute_audit(db: Any, chat_id: Any) -> str:
    """/audit: evidencia de la última ejecución (SQL, latencia, run_id)."""
    raw = get_chat_state(db, chat_id, "last_audit")
    if not raw:
        return "No hay evidencia de última ejecución. Envía un mensaje y vuelve a usar /audit."
    try:
        data = json.loads(raw)
        sql = data.get("sql") or "(no registrado)"
        latency_ms = data.get("latency_ms") or "—"
        tokens = data.get("tokens") or "—"
        run_id = data.get("run_id") or "—"
        return (
            f"📋 Última ejecución\nSQL: {str(sql)[:300]}\nLatencia: {latency_ms} ms\nTokens: {tokens}\nLangSmith run_id: {run_id}"
        
        )
    except Exception:
        return "Datos de auditoría no válidos."


def execute_health(db: Any) -> str:
    """/health: estado de infraestructura (MLX, DuckDB, latencia)."""
    lines = []
    # DuckDB
    try:
        db.query("SELECT 1")
        lines.append("✅ DuckDB: conectado")
    except Exception as e:
        lines.append(f"❌ DuckDB: {e}")
    # MLX / inference
    base_url = os.environ.get("DUCKCLAW_LLM_BASE_URL", "").strip() or "http://127.0.0.1:8080"
    if base_url:
        base = base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        url = base + "/health"
        try:
            import urllib.request
            t0 = time.perf_counter()
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                elapsed = int((time.perf_counter() - t0) * 1000)
                lines.append(f"✅ Inferencia ({url[:40]}...): {elapsed} ms")
        except Exception as e:
            lines.append(f"⚠️ Inferencia: {e}")
    return "\n".join(lines) or "Sin comprobaciones."


def execute_approve_reject(db: Any, chat_id: Any, approved: bool) -> str:
    """/approve o /reject: HITL (grafo en interrupt). Sin interrupt implementado: mensaje informativo."""
    return "No hay operación pendiente de aprobación. (El grafo no está en estado interrupt en esta versión.)"


def _normalize_belief_key(key: str) -> str:
    """Normaliza key para DB: alfanumérico y guión bajo."""
    return "".join(c if c.isalnum() or c == "_" else "_" for c in (key or "").strip())


def _get_goals_registry_fallback_first() -> Optional[Any]:
    """Primer template con homeostasis (orden del FS); solo como fallback."""
    try:
        from duckclaw.workers.factory import list_workers
        from duckclaw.workers.manifest import load_manifest
        from duckclaw.forge.homeostasis.belief_registry import BeliefRegistry

        for wid in list_workers():
            try:
                spec = load_manifest(wid)
                config = getattr(spec, "homeostasis_config", None) or {}
                registry = BeliefRegistry.from_config(config)
                if registry.beliefs:
                    return registry
            except Exception:
                continue
    except Exception:
        pass
    return None


def _get_goals_registry_for_chat(db: Any, chat_id: Any) -> Optional[Any]:
    """Registro homeostasis del worker activo del chat; fallback al primer template con YAML."""
    from duckclaw.forge.homeostasis.belief_registry import BeliefRegistry
    from duckclaw.workers.manifest import load_manifest

    wid = (get_chat_state(db, chat_id, "worker_id") or "").strip()
    if wid and wid.lower() != "manager":
        try:
            spec = load_manifest(wid)
            config = getattr(spec, "homeostasis_config", None) or {}
            registry = BeliefRegistry.from_config(config)
            if registry.beliefs:
                return registry
        except Exception:
            pass
    return _get_goals_registry_fallback_first()


def get_manager_goals(db: Any, chat_id: Any) -> list:
    """Goals del chat guardados por el manager. Por defecto vacío."""
    raw = get_chat_state(db, chat_id, "goals")
    if not raw:
        return []
    try:
        out = json.loads(raw)
        return out if isinstance(out, list) else []
    except Exception:
        return []


def set_manager_goals(db: Any, chat_id: Any, goals: list) -> None:
    """Guarda la lista de goals del chat (manager). Cada item: belief_key, target_value, threshold, observed_value opcional, title (resumen)."""
    set_chat_state(db, chat_id, "goals", json.dumps(goals))


def _goal_title(goal: dict, fallback_key: str) -> str:
    """Título resumen del goal para listar en /crons."""
    t = (goal.get("title") or "").strip()
    if t:
        return t[:80] + ("…" if len((goal.get("title") or "").strip()) > 80 else "")
    return (goal.get("belief_key") or fallback_key or "").strip()


def build_goals_proactive_system_event_message(
    goals: list,
    *,
    trading_session_objective: str | None = None,
) -> str:
    titles: list[str] = []
    for g in goals:
        if not isinstance(g, dict):
            continue
        k = (g.get("belief_key") or "").strip()
        titles.append(_goal_title(g, k))
    summary = "; ".join(titles[:12]) if titles else "(sin títulos)"
    obj = (trading_session_objective or "").strip().lower()
    extra = ""
    if obj == "overnight_gap_squeeze":
        extra = (
            " **MISIÓN: OVERNIGHT GAP SQUEEZE — PREP + MOC (HRP + MOC Proxy):** "
            "Durante 08:30–15:00 COT lun–vie: recolectar contexto (CFD/OHLCV/portfolio/sandbox/read_sql). "
            "Sin catalizador intradía claro → **`accumulate_moc_intraday_state`** (postura explícita: watchlist, sizing 0/HOLD, régimen) "
            "en lugar de solo «sin setup». **`propose_trade_signal`** puede crearse cuando haya evidencia del turno y riesgo lo permita "
            "(Ledger `PENDING_HITL` en cualquier horario por defecto); la **auto-ejecución** encadenada con "
            "`DUCKCLAW_QUANT_AUTO_EXECUTE_SIGNALS`: **RTH** lun–vie 08:30–15:00 COT salvo `strategy_name` en "
            "`DUCKCLAW_QUANT_AUTO_EXECUTE_MOC_STRATEGY_NAMES` (default `overnight_gap_moc` → ventana **MOC** "
            "~14:40–14:59:30 COT, `DUCKCLAW_QUANT_AUTO_EXECUTE_MOC_WINDOW`). "
            "Opt-in `DUCKCLAW_QUANT_BLOCK_NON_MOC_LEDGER=1` restaura bloqueo fuera de MOC (`OUTSIDE_MOC_PREP_WINDOW`). "
            "Pipeline PM2 `moc_pipeline.py` (moc_hrp_cfd) no lo sustituyes; batch MOC `/execute_all_moc`. "
            "1) OHLCV 1m vía `fetch_market_data`. "
            "2) Portfolio vía `get_ibkr_portfolio`. "
            "3) Sandbox script `overnight_squeeze_standalone.py`. "
            "4) Script: Kalman 1m, MOC Proxy (volumen direccional 15m), HRP tope 35%. "
            "5) Si MOC Proxy > 0 + Kalman alcista y procede playbook, una señal hacia HRP; "
            "si MOC Proxy < 0 → postura defensiva documentada (accumulate) antes de forzar narrativa sin Ledger."
        )
    elif obj == "rebalance_hrp":
        extra = (
            " **Sesión `quant_core.trading_sessions` (session_goal.objective=rebalance_hrp):** el veredicto "
            "debe **priorizar** alineación cartera IBKR vs **pesos HRP** del sandbox (desviación por ticker, "
            "HITL); no basta con constatar PnL>0. "
        )
    elif obj == "maximize_pnl":
        extra = (
            " **Sesión (session_goal.objective=maximize_pnl):** puedes anclar el cierre a PnL/riesgo según "
            "sesión; si además hiciste HRP en sandbox, cita desviación vs cartera. "
        )
    _cot_ctx = ""
    if obj == "overnight_gap_squeeze":
        try:
            _cot_ctx = quant_event_horario_line() + " "
        except Exception:
            _cot_ctx = ""
    return (
        "[SYSTEM_EVENT: "
        + _cot_ctx
        + "Revisión periódica de /crons. Objetivos: "
        f"{summary}.{extra}Evalúa con herramientas si hace falta qué tan alineado está el "
        "contexto actual (portfolio, sesión de trading, etc.) con cumplir cada meta. "
        "Responde al usuario con un breve análisis o propuesta concreta (mensaje útil; "
        "si el worker lo permite, señal u orden solo si procede).]"
    )


class TradingTickEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["TRADING_TICK"] = "TRADING_TICK"
    trigger: str = "trading_session"
    session_uid: str
    tickers: list[str]
    mode: str = "paper"
    signal_threshold: str = "GAS"
    objective: str = "maximize_pnl"
    directive: str


def build_trading_tick_system_event_message(
    *,
    session_uid: str,
    tickers: list[str],
    mode: str,
    signal_threshold: str,
    objective: str = "maximize_pnl",
) -> str:
    _obj = str(objective or "maximize_pnl").strip().lower() or "maximize_pnl"
    if _obj not in ("maximize_pnl", "rebalance_hrp", "overnight_gap_squeeze"):
        _obj = "maximize_pnl"
    _directive = (
        "TRADING TICK AUTÓNOMO (HITL): 1) validar sesión ACTIVE; 2) ejecutar evaluate_cfd_state "
        "con session_uid+tickers; 3) si outcome=ERROR o all_data_failed, reportar ceguera sensorial; "
        "4) si outcome=MISALIGNED y no hay pending por ticker, `propose_trade_signal` como mucho 1 por ticker "
        "cuando haya evidencia OHLCV del turno y riesgo lo permita (propuesta Ledger permitida fuera de ventana MOC por defecto); "
        "la **auto-ejecución** encadenada (`DUCKCLAW_QUANT_AUTO_EXECUTE_SIGNALS`): **RTH** lun–vie 08:30–15:00 COT salvo "
        "`strategy_name` en `DUCKCLAW_QUANT_AUTO_EXECUTE_MOC_STRATEGY_NAMES` (default overnight_gap_moc → ventana MOC "
        "~14:40–14:59:30); fuera de la compuerta que aplique no hay cadena auto grant+execute; "
        "opt-in `DUCKCLAW_QUANT_BLOCK_NON_MOC_LEDGER=1` bloquea propuesta fuera de MOC (`OUTSIDE_MOC_PREP_WINDOW`; excepción job `moc_hrp_cfd`); "
        "NO ejecutar en tick; 5) si mode=live agregar warning de capital real; "
        "6) si ALIGNED, no enviar resumen al usuario."
    )
    if _obj == "rebalance_hrp":
        _directive += (
            " 7) REBALANCEO HRP: mismos tickers de sesión, OHLCV suficiente (fetch_ib_gateway_ohlcv o read_sql "
            "sobre quant_core.ohlcv_data), luego execute_sandbox_script: **preferir PyPortfolioOpt** "
            "(import pypfopt; pypfopt.hierarchical_portfolio.HRPOpt + risk_models.sample_cov sobre DataFrame de retornos; "
            "optimize() → pesos que suman 1). Solo si pypfopt falla, HRP manual con pandas/scipy. "
            "Comparar vs get_ibkr_portfolio; si desviación relevante y sin HITL pendiente por ticker, máximo 1 "
            "`propose_trade_signal` de rebalanceo por ticker cuando proceda (Ledger fuera de MOC permitido por defecto; "
            "con auto-exec activo usar `strategy_name=rebalance_hrp` para compuerta **RTH** 08:30–15:00 COT)."
        )
    elif _obj == "overnight_gap_squeeze":
        _directive += (
            " 7) OVERNIGHT GAP SQUEEZE: en 08:30–15:00 COT lun–vie recolectar contexto "
            "(evaluate_cfd_state, fetch_ib_gateway_ohlcv/fetch_market_data, read_sql, get_ibkr_portfolio, sandbox según playbook). "
            "Sin setup claro → `accumulate_moc_intraday_state`; con evidencia y playbook alineado → como mucho 1 `propose_trade_signal` por ticker "
            "(fuera de ventana MOC permitido por defecto; auto-exec: RTH salvo `overnight_gap_moc` → MOC). "
            "Señales batch `moc_hrp_cfd` = solo PM2. Opt-in `DUCKCLAW_QUANT_BLOCK_NON_MOC_LEDGER` → `OUTSIDE_MOC_PREP_WINDOW` fuera de MOC."
        )
    event = TradingTickEvent.model_validate(
        {
            "session_uid": str(session_uid or "").strip(),
            "tickers": [str(t or "").strip().upper() for t in (tickers or []) if str(t or "").strip()],
            "mode": str(mode or "paper").strip().lower() or "paper",
            "signal_threshold": str(signal_threshold or "GAS").strip().upper() or "GAS",
            "objective": _obj,
            "directive": _directive,
        }
    )
    _cot_line = ""
    try:
        _cot_line = quant_event_horario_line() + " "
    except Exception:
        _cot_line = ""
    return "[SYSTEM_EVENT: " + _cot_line + event.model_dump_json(ensure_ascii=False) + "]"


def _natural_language_goal_to_params(db: Any, chat_id: Any, text: str) -> Optional[dict]:
    """Convierte un objetivo en lenguaje natural a parámetros homeostasis (belief_key, target_value, threshold, title). Usa LLM del manager."""
    text = (text or "").strip()[:500]
    if not text:
        return None
    try:
        from langchain_core.messages import HumanMessage
        provider, model, base_url = _effective_llm_triplet_for_chat_ui(db, chat_id)
        from duckclaw.integrations.llm_providers import build_llm
        llm = build_llm(provider, model, base_url, prefer_env_provider=False)
        if llm is None:
            return None
        prompt = (
            "Convierte este objetivo en lenguaje natural a parámetros para homeostasis (Active Inference). "
            "Responde ÚNICAMENTE un JSON válido con estas claves: belief_key (slug en snake_case, inglés o español), "
            "target_value (número; 0 si el objetivo es minimizar o cualitativo), threshold (número >= 0, tolerancia), "
            "title (resumen corto en español, máx 60 caracteres). Sin explicación, solo el JSON.\n\nObjetivo: "
        ) + text
        resp = llm.invoke([HumanMessage(content=prompt)])
        content = (getattr(resp, "content", None) or "").strip()
        if not content:
            return None
        # Extraer JSON si viene envuelto en ```json ... ```
        if "```" in content:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                content = content[start:end]
        data = json.loads(content)
        if not isinstance(data, dict):
            return None
        key = (data.get("belief_key") or "").strip() or _normalize_belief_key(text)
        key = _normalize_belief_key(key) or "objetivo"
        target = float(data.get("target_value", 0))
        thresh = max(0.0, float(data.get("threshold", 0)))
        title = (data.get("title") or text)[:120].strip()
        return {"belief_key": key, "target_value": target, "threshold": thresh, "title": title}
    except Exception:
        return None


def execute_goals(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    tenant_id: Any = None,
    vault_user_id: Any = None,
) -> str:
    """/crons [--reset] [--delta …] [--timestamp …] [--rm …] | /crons <goal>: listar, programar o quitar schedules, resetear o añadir objetivo. Alias: /goals."""
    _ = vault_user_id
    from duckclaw.forge.homeostasis.surprise import compute_surprise

    registry = _get_goals_registry_for_chat(db, chat_id)
    goals = get_manager_goals(db, chat_id)
    tid = str(tenant_id or "default").strip() or "default"
    active_wid = (get_chat_state(db, chat_id, "worker_id") or "").strip()

    raw = (args or "").strip()
    toks = raw.split()

    if toks and toks[0] == "--delta":
        if len(toks) < 2:
            return (
                "Uso: /crons --delta 20min (o 1h, 90s) · /crons --delta off\n"
                "El ticker (heartbeat o embebido en el gateway) escanea el hub y las bóvedas "
                f"en db/private/*/*.duckdb. Intervalo permitido: {GOALS_DELTA_MIN_SECONDS}s … 7d."
            )
        dur_parts: list[str] = []
        i = 1
        while i < len(toks) and not toks[i].startswith("--"):
            dur_parts.append(toks[i])
            i += 1
        dur_str = "".join(dur_parts)
        secs, err = parse_goals_delta_arg(dur_str)
        if err:
            return err
        if secs == 0:
            clear_interval_schedule_only(db, chat_id)
            return "Intervalo de revisión desactivado (/crons --delta off). Horario de reloj (--timestamp) no se modifica."
        clear_goals_cron_wall_storage(db, chat_id)
        set_chat_state(db, chat_id, _GOALS_DELTA_SECONDS_KEY, str(secs))
        set_chat_state(db, chat_id, _GOALS_PROACTIVE_TENANT_KEY, tid)
        # Cooldown starts now so the first tick waits ~secs (not the next 45s gateway poll).
        _fire_anchor = str(time.time())
        set_chat_state(db, chat_id, _GOALS_PROACTIVE_LAST_FIRE_KEY, _fire_anchor)
        _anchor_now = _fire_anchor
        set_chat_state(db, chat_id, _GOALS_PROACTIVE_ANCHOR_KEY, _anchor_now)
        set_chat_state(db, chat_id, _GOALS_DELTA_ANCHOR_LEGACY_KEY, _anchor_now)
        # Explicit `/crons --delta` is always a lightweight goals review (heartbeat uses
        # build_goals_proactive_system_event_message). Full TRADING_TICK scheduling stays
        # in `_ensure_trading_session_goals_delta` when a Quant session starts.
        meta_obj: dict[str, Any] = {"trigger": "goals_cli"}
        set_chat_state(
            db,
            chat_id,
            _GOALS_DELTA_META_KEY,
            json.dumps(meta_obj, ensure_ascii=False),
        )
        human = format_goals_delta_interval_human(secs)
        return (
            f"Revisión proactiva cada ~{human}. "
            "El ticker del heartbeat disparará un SYSTEM_EVENT para revisar tus objetivos (/crons). "
            "Usa /crons para listar. /crons --delta off para cancelar."
        )

    if toks and toks[0] == "--timestamp":
        rest = toks[1:]
        if not rest:
            return (
                "Uso: /crons --timestamp once 2026-05-12T14:45 · "
                "/crons --timestamp every 14:45 [weekdays|lun mar …] · /crons --timestamp off\n"
                "Zona: America/Bogota por defecto (env DUCKCLAW_CRONS_WALL_TZ). "
                "Exclusivo con /crons --delta: al activar uno se desactiva el otro."
            )
        if rest[0].lower() == "off":
            clear_goals_cron_wall_storage(db, chat_id)
            return "Horario de reloj desactivado (/crons --timestamp off)."
        spec, terr = parse_cron_wall_tokens(rest)
        if terr or not spec:
            return terr or "No se pudo interpretar --timestamp."
        clear_interval_schedule_only(db, chat_id)
        set_chat_state(db, chat_id, _GOALS_CRON_WALL_KEY, json.dumps(spec, ensure_ascii=False))
        set_chat_state(db, chat_id, _GOALS_PROACTIVE_TENANT_KEY, tid)
        mraw = (get_chat_state(db, chat_id, _GOALS_DELTA_META_KEY) or "").strip()
        try:
            if not mraw:
                set_chat_state(
                    db,
                    chat_id,
                    _GOALS_DELTA_META_KEY,
                    json.dumps({"trigger": "goals_wall"}, ensure_ascii=False),
                )
            else:
                mobj = json.loads(mraw)
                if not isinstance(mobj, dict) or str(mobj.get("trigger") or "").lower() != "trading_session":
                    set_chat_state(
                        db,
                        chat_id,
                        _GOALS_DELTA_META_KEY,
                        json.dumps({"trigger": "goals_wall"}, ensure_ascii=False),
                    )
        except Exception:
            set_chat_state(
                db,
                chat_id,
                _GOALS_DELTA_META_KEY,
                json.dumps({"trigger": "goals_wall"}, ensure_ascii=False),
            )
        return (
            f"Programación por reloj guardada. {format_cron_wall_human(spec)} "
            "Usa /crons para listar. /crons --timestamp off para cancelar."
        )

    if toks and toks[0] == "--rm":
        if len(toks) < 2:
            return (
                "Uso: /crons --rm delta · /crons --rm wall\n"
                "Equivale a /crons --delta off (intervalo) o /crons --timestamp off (reloj). "
                "Los cron-id salen en /crons junto a cada programación (alias: interval, timestamp)."
            )
        cid = _normalize_cron_rm_id(toks[1])
        if cid is None:
            return (
                f"Cron-id desconocido `{toks[1]}`. Usa `{CRON_SCHEDULE_ID_DELTA}` (intervalo) o "
                f"`{CRON_SCHEDULE_ID_WALL}` (horario de reloj); alias: interval, timestamp."
            )
        if cid == CRON_SCHEDULE_ID_DELTA:
            try:
                ds_rm = int((get_chat_state(db, chat_id, _GOALS_DELTA_SECONDS_KEY) or "0").strip() or "0")
            except ValueError:
                ds_rm = 0
            if ds_rm <= 0:
                return (
                    f"No hay revisión por intervalo activa (cron-id `{CRON_SCHEDULE_ID_DELTA}`). "
                    "Ejecuta /crons para ver el listado."
                )
            clear_interval_schedule_only(db, chat_id)
            return (
                "Programación por intervalo eliminada (/crons --rm "
                f"{CRON_SCHEDULE_ID_DELTA}). Horario de reloj (--timestamp) no se modifica."
            )
        raw_wm = (get_chat_state(db, chat_id, _GOALS_CRON_WALL_KEY) or "").strip()
        if not raw_wm:
            return (
                f"No hay horario de reloj activo (cron-id `{CRON_SCHEDULE_ID_WALL}`). "
                "Ejecuta /crons para ver el listado."
            )
        clear_goals_cron_wall_storage(db, chat_id)
        return (
            f"Horario de reloj eliminado (/crons --rm {CRON_SCHEDULE_ID_WALL}). "
            "El intervalo (/crons --delta) no se modifica."
        )

    do_reset = raw.lower() == "--reset"

    if do_reset:
        clear_goals_proactive_schedule(db, chat_id)
        set_manager_goals(db, chat_id, [])
        if active_wid == _QUANT_TRADER_TEMPLATE_ID:
            ok_r, det_r = _quant_clear_risk_constraints_vault(db, tenant_id=tid)
            if not ok_r:
                return (
                    "✅ Objetivos reiniciados (aviso: no se limpió riesgo en bóveda: "
                    f"{det_r}). Crea con /crons <objetivo>."
                )
        return "✅ Objetivos reiniciados. Crea con /crons <objetivo en lenguaje natural o clave>."

    # Añadir: /crons <clave o lenguaje natural>
    if raw and not raw.startswith("--"):
        key_norm = _normalize_belief_key(raw)
        belief = None
        if registry:
            belief = registry.get_belief(raw.strip())
            if not belief:
                for b in registry.beliefs:
                    if _normalize_belief_key(b.key) == key_norm:
                        belief = b
                        break
        if belief:
            new_goal = {
                "belief_key": belief.key,
                "target_value": belief.target,
                "threshold": belief.threshold,
                "observed_value": None,
                "title": belief.key,
            }
        else:
            # Lenguaje natural: manager convierte a parámetros homeostasis vía LLM
            params = _natural_language_goal_to_params(db, chat_id, raw)
            if params:
                new_goal = {
                    "belief_key": params["belief_key"],
                    "target_value": params["target_value"],
                    "threshold": params["threshold"],
                    "observed_value": None,
                    "title": params["title"],
                }
            else:
                new_goal = {
                    "belief_key": key_norm or "objetivo",
                    "target_value": 0.0,
                    "threshold": 0.0,
                    "observed_value": None,
                    "title": raw[:120].strip(),
                }
        low_raw = raw.lower()
        if active_wid == _QUANT_TRADER_TEMPLATE_ID and (
            "drawdown" in low_raw
            or "draw down" in low_raw
            or " max dd" in low_raw
            or low_raw.strip().startswith("dd ")
        ):
            _quant_normalize_drawdown_goal(new_goal)
        if active_wid == _QUANT_TRADER_TEMPLATE_ID and _quant_is_drawdown_goal(new_goal):
            _quant_normalize_drawdown_goal(new_goal)
        existing = [g for g in goals if (g.get("belief_key") or "").strip() == new_goal["belief_key"]]
        if existing:
            goals = [g for g in goals if (g.get("belief_key") or "").strip() != new_goal["belief_key"]]
        goals.append(new_goal)
        set_manager_goals(db, chat_id, goals)
        title_display = new_goal.get("title") or new_goal["belief_key"]
        if (
            active_wid == _QUANT_TRADER_TEMPLATE_ID
            and (new_goal.get("belief_key") or "").strip() == "max_portfolio_drawdown_pct"
        ):
            try:
                cap = float(new_goal.get("target_value") or 0.0)
            except (TypeError, ValueError):
                cap = 0.0
            ok_m, det_m = _quant_mirror_max_drawdown_to_vault(db, tenant_id=tid, max_dd=cap)
            if not ok_m:
                return f"✅ Objetivo añadido (aviso: riesgo no guardado en bóveda: {det_m})"
        return f"✅ Objetivo añadido: {title_display}"

    # Listar (por defecto vacío): bloque «Tus crons» + «Del bot (infraestructura)»
    platform = format_platform_cron_summary()
    proactive_section = _crons_goals_delta_listing_section(db, chat_id)
    user_intro = "Tus crons\n\n\U0001f3af Manager"

    if not goals:
        user_body = (
            f"{user_intro}\n"
            "No hay goals. Crea con /crons <objetivo>, ej. /crons disminuir gasto en recreación."
        )
        user_body += proactive_section
        user_body += _goals_cron_wall_listing_note(db, chat_id)
        return f"{user_body}\n\n{platform}\n\n/crons --reset"

    lines = [user_intro]
    try:
        key_to_belief = {b.key.strip(): b for b in (registry.beliefs if registry else [])}
        for g in goals:
            key = (g.get("belief_key") or "").strip()
            b = key_to_belief.get(key)
            target = float(g.get("target_value")) if g.get("target_value") is not None else None
            thresh = float(g.get("threshold")) if g.get("threshold") is not None else None
            if b is not None:
                target = target if target is not None else b.target
                thresh = thresh if thresh is not None else b.threshold
            try:
                observed = float(g.get("observed_value")) if g.get("observed_value") is not None else None
            except (TypeError, ValueError):
                observed = None
            title = _goal_title(g, key)
            comp = "symmetric"
            if b is not None:
                comp = getattr(b, "comparison", "symmetric") or "symmetric"
            elif key == "max_portfolio_drawdown_pct":
                comp = "ceiling"
            if observed is not None and target is not None and thresh is not None and (target != 0 or thresh != 0):
                res = compute_surprise(observed, target, thresh, comparison=comp)
                st = "⚠️" if res.is_anomaly else "✓"
                lines.append(f"- {title}: target={target} (obs: {observed}) {st}")
            elif target is not None and thresh is not None:
                lines.append(f"- {title}: target={target}, thresh={thresh} (sin dato)")
            else:
                lines.append(f"- {title}")
    except Exception as e:
        return f"Error: {e}."
    wall_note = _goals_cron_wall_listing_note(db, chat_id)
    goals_block = "\n".join(lines) + proactive_section + wall_note
    return f"{goals_block}\n\n{platform}\n\n/crons --reset"


def execute_tasks(db: Any, chat_id: Any) -> str:
    """/tasks: estado del ActivityManager (Redis): IDLE, BUSY, subagente, tarea actual, tiempo en ejecución."""
    from duckclaw.graphs.activity import get_activity
    data = get_activity(chat_id)
    if data is None:
        return "⏸ IDLE (Redis no configurado)."
    status = data.get("status", "IDLE")
    task = data.get("task", "")
    worker_id = data.get("worker_id", "") or ""
    started_at = data.get("started_at", 0)
    elapsed_s = ""
    if started_at and status == "BUSY":
        try:
            elapsed_s = f" · {int(time.time()) - int(started_at)}s"
        except Exception:
            pass
    # Guión en worker_id (p. ej. SIATA-Analyst) obliga a \- en MarkdownV2; muchos clientes muestran el \ literal.
    # Mismo criterio que label de gateway: espacio en lugar de guion para etiqueta legible sin escapes.
    worker_display = (worker_id or "").replace("-", " ").strip()
    worker_s = f" · {worker_display}" if worker_display else ""
    # Segunda línea: solo el título del plan (task), precedido por un bullet grande
    task_preview = f"• {str(task)[:60]}" if task else "—"
    icon = "▶" if status == "BUSY" else "⏸"
    return f"{icon} {status}{elapsed_s}{worker_s}\n" + task_preview


def _get_global_config(db: Any, key: str) -> str:
    """Read a global config key from agent_config (e.g. system_prompt)."""
    _ensure_agent_config(db)
    k = str(key).replace("'", "''")[:128]
    try:
        r = db.query(f"SELECT value FROM {_AGENT_CONFIG_TABLE} WHERE key = '{k}' LIMIT 1")
        rows = json.loads(r) if isinstance(r, str) else (r or [])
        if rows and isinstance(rows[0], dict):
            return (rows[0].get("value") or "").strip()
    except Exception:
        pass
    return ""


def _set_global_config(db: Any, key: str, value: str) -> None:
    """Write a global config key to agent_config."""
    _ensure_agent_config(db)
    k = str(key).replace("'", "''")[:128]
    v = str(value).replace("'", "''")[:16384]
    db.execute(
        f"""
        INSERT INTO {_AGENT_CONFIG_TABLE} (key, value) VALUES ('{k}', '{v}')
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """
    )


def get_effective_system_prompt(db: Any, worker_id: Optional[str] = None) -> str:
    """
    Devuelve el system prompt efectivo para un worker:
    - Si worker_id está definido: 1) override system_prompt_<worker_id>, 2) soul.md + system_prompt.md del template (ver load_system_prompt). No usa global.
    - Si worker_id vacío: global system_prompt o "".
    """
    wid = (worker_id or "").strip()
    if wid:
        override = _get_global_config(db, f"system_prompt_{wid}")
        if override:
            return override
        try:
            from duckclaw.workers.manifest import load_manifest
            from duckclaw.workers.loader import load_system_prompt
            spec = load_manifest(wid)
            return (load_system_prompt(spec) or "").strip()
        except Exception:
            pass
        return ""
    current = _get_global_config(db, "system_prompt")
    return current if current else ""


_PROVIDERS = ("mlx", "ollama", "openai", "anthropic", "deepseek", "groq", "gemini", "openrouter", "or")

# Modelo por defecto al cambiar provider (evita "Model Not Exist" al pasar de MLX a cloud)
_DEFAULT_MODEL_BY_PROVIDER = {
    "deepseek": "deepseek-chat",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-20241022",
    "groq": "llama-3.3-70b-versatile",
    "gemini": "gemini-2.0-flash",
    "openrouter": "anthropic/claude-sonnet-4-5",
    "mlx": "",  # usa MLX_MODEL_ID o /v1/models
    "ollama": "llama3.2",
}

# Base URL por defecto al cambiar provider (evita mezclar host global PM2 con otro proveedor).
_DEFAULT_BASE_URL_BY_PROVIDER = {
    "deepseek": "https://api.deepseek.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "",
    "anthropic": "",
    "gemini": "",
    "mlx": "",
    "ollama": "http://127.0.0.1:11434",
}


def _effective_llm_triplet_for_chat_ui(db: Any, chat_id: Any) -> tuple[str, str, str]:
    """provider/model/base_url efectivos (chat > global agent_config > env), con MLX forzado a host local."""
    from duckclaw.integrations.llm_providers import (
        _ensure_duckclaw_llm_env_from_legacy_llm_vars,
        mlx_openai_compatible_base_url,
    )

    _ensure_duckclaw_llm_env_from_legacy_llm_vars()
    p_chat = (get_chat_state(db, chat_id, "llm_provider") or "").strip()
    p_global = (_get_global_config(db, "llm_provider") or "").strip()
    p_env = (os.environ.get("DUCKCLAW_LLM_PROVIDER", "mlx") or "").strip()
    p = (p_chat or p_global or p_env).strip().lower()
    m_chat = (get_chat_state(db, chat_id, "llm_model") or "").strip()
    m_global = (_get_global_config(db, "llm_model") or "").strip()
    m_env = (os.environ.get("DUCKCLAW_LLM_MODEL", "") or "").strip()
    m = (m_chat or m_global or m_env).strip()
    u_chat = (get_chat_state(db, chat_id, "llm_base_url") or "").strip()
    u_global = (_get_global_config(db, "llm_base_url") or "").strip()
    u_env = (os.environ.get("DUCKCLAW_LLM_BASE_URL", "") or "").strip()
    u = (u_chat or u_global or u_env).strip()
    if p == "mlx":
        ul = u.lower()
        if (not u) or "groq.com" in ul or "deepseek.com" in ul:
            u = mlx_openai_compatible_base_url()
        if not m:
            m = (os.environ.get("MLX_MODEL_ID") or os.environ.get("MLX_MODEL_PATH") or "").strip()
    _debug_log_model_config(
        hypothesis_id="H_sources_priority",
        location="on_the_fly_commands._effective_llm_triplet_for_chat_ui",
        message="effective_triplet_computed",
        data={
            "chat_id": str(chat_id),
            "provider": p,
            "model": m[:80],
            "base_url": u[:120],
            "src_provider": "chat" if p_chat else ("global" if p_global else "env"),
            "src_model": "chat" if m_chat else ("global" if m_global else "env"),
            "src_base_url": "chat" if u_chat else ("global" if u_global else "env"),
            "chat_provider": p_chat[:60],
            "chat_base_url": u_chat[:120],
            "global_provider": p_global[:60],
            "global_base_url": u_global[:120],
            "env_provider": p_env[:60],
            "env_base_url": u_env[:120],
        },
    )
    return (p, m, u)


def chat_has_llm_chat_state_override(db: Any, chat_id: Any) -> bool:
    cid = str(chat_id or "").strip()
    if not cid:
        return False
    for key in ("llm_provider", "llm_model", "llm_base_url"):
        if (get_chat_state(db, cid, key) or "").strip():
            return True
    return False


def resolve_llm_triplet_for_chat_invocation(db: Any, chat_id: Any) -> tuple[str, str, str] | None:
    """Si el chat tiene llm_* en agent_config, devuelve tripleta para build_llm; si no, None (usar cache env del gateway)."""
    has_override = chat_has_llm_chat_state_override(db, chat_id)
    _debug_log_model_config(
        hypothesis_id="H_override_gate",
        location="on_the_fly_commands.resolve_llm_triplet_for_chat_invocation",
        message="chat_override_gate",
        data={"chat_id": str(chat_id), "has_override": bool(has_override)},
    )
    if not has_override:
        return None
    return _effective_llm_triplet_for_chat_ui(db, chat_id)


def execute_model(db: Any, chat_id: Any, args: str) -> str:
    """/model [provider=mlx] [model=...] [base_url=...]: cambia proveedor/modelo LLM en caliente. Sin args muestra el actual."""
    _debug_log_model_config(
        hypothesis_id="H_write_apply",
        location="on_the_fly_commands.execute_model",
        message="execute_model_entry",
        data={"chat_id": str(chat_id), "args": (args or "")[:180]},
    )
    if not args or not args.strip():
        provider, model, base_url = _effective_llm_triplet_for_chat_ui(db, chat_id)
        provider = provider or "—"
        model = model or "—"
        u_show = base_url or "—"
        base_url = u_show[:50] + "…" if len(u_show) > 50 else u_show
        return f"Modelo actual:\n- provider: {provider}\n- model: {model}\n- base_url: {base_url}\n\nUso: /model provider=mlx | /model provider=deepseek | /model provider=openrouter | /model provider=or model=google/gemini-2.5-pro | /model model=Slayer-8B"
    for part in args.split("|"):
        part = part.strip()
        if "=" in part:
            k, _, v = part.partition("=")
            k, v = k.strip().lower(), v.strip()
            if k == "provider":
                if v and v.lower() not in _PROVIDERS:
                    return f"Provider desconocido: {v}. Válidos: {', '.join(_PROVIDERS)}"
                pv = v.lower()
                if pv in ("or", "router"):
                    pv = "openrouter"
                set_chat_state(db, chat_id, "llm_provider", pv)
                # Al cambiar provider, resetear model al default para evitar "Model Not Exist"
                # (ej. Slayer-8B-v1.1 no existe en DeepSeak)
                if pv == "mlx":
                    from duckclaw.integrations.llm_providers import mlx_openai_compatible_base_url

                    set_chat_state(db, chat_id, "llm_base_url", mlx_openai_compatible_base_url())
                    mid = (os.environ.get("MLX_MODEL_ID") or os.environ.get("MLX_MODEL_PATH") or "").strip()
                    set_chat_state(db, chat_id, "llm_model", mid)
                else:
                    default_model = _DEFAULT_MODEL_BY_PROVIDER.get(pv, "")
                    set_chat_state(db, chat_id, "llm_model", default_model)
                    default_url = _DEFAULT_BASE_URL_BY_PROVIDER.get(pv, "")
                    if default_url:
                        set_chat_state(db, chat_id, "llm_base_url", default_url)
                    else:
                        set_chat_state(db, chat_id, "llm_base_url", "")
                _debug_log_model_config(
                    hypothesis_id="H_write_apply",
                    location="on_the_fly_commands.execute_model",
                    message="provider_written",
                    data={
                        "chat_id": str(chat_id),
                        "provider_arg": pv,
                        "default_model": (_DEFAULT_MODEL_BY_PROVIDER.get(pv, "") or "")[:80],
                        "default_base_url": (_DEFAULT_BASE_URL_BY_PROVIDER.get(pv, "") or "")[:120],
                    },
                )
            elif k == "model":
                set_chat_state(db, chat_id, "llm_model", v)
            elif k == "base_url":
                set_chat_state(db, chat_id, "llm_base_url", v)
    _p, _m, _u = _effective_llm_triplet_for_chat_ui(db, chat_id)
    _debug_log_model_config(
        hypothesis_id="H_write_apply",
        location="on_the_fly_commands.execute_model",
        message="execute_model_exit",
        data={"chat_id": str(chat_id), "provider": _p, "model": _m[:80], "base_url": _u[:120]},
    )
    return "✅ Modelo actualizado. Los próximos mensajes usarán esta config."


def _parse_pipe_kv_args(args: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in (args or "").split("|"):
        p = part.strip()
        if "=" not in p:
            continue
        k, _, v = p.partition("=")
        k = k.strip().lower()
        v = v.strip()
        if k:
            out[k] = v
    return out


def _gemini_models_list_from_api(api_key: str) -> tuple[list[str], str | None]:
    url = "https://generativelanguage.googleapis.com/v1beta/models"
    req = urllib.request.Request(
        f"{url}?key={urllib.parse.quote(api_key)}",
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            status = getattr(resp, "status", 200)
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        return [], f"Gemini API HTTP {e.code}: {(detail or '').strip()[:220] or 'sin detalle'}"
    except Exception as e:
        return [], f"No pude consultar Gemini models: {e}"
    if status < 200 or status >= 300:
        return [], f"Gemini API devolvió HTTP {status}."
    try:
        payload = json.loads(body or "{}")
    except json.JSONDecodeError:
        return [], "Gemini API devolvió una respuesta no-JSON."
    models = payload.get("models")
    if not isinstance(models, list):
        return [], "Gemini API no devolvió la lista de modelos."
    usable: list[str] = []
    for row in models:
        if not isinstance(row, dict):
            continue
        raw_name = str(row.get("name") or "").strip()
        if not raw_name:
            continue
        methods = row.get("supportedGenerationMethods") or []
        if isinstance(methods, list) and methods:
            method_names = {str(m).strip() for m in methods if str(m).strip()}
            if "generateContent" not in method_names:
                continue
        short_name = raw_name.split("/")[-1]
        if short_name:
            usable.append(short_name)
    dedup = sorted(set(usable))
    if "gemini-2.0-flash" in dedup:
        dedup = ["gemini-2.0-flash"] + [m for m in dedup if m != "gemini-2.0-flash"]
    return dedup, None


def execute_models(db: Any, chat_id: Any, args: str) -> str:
    """/models provider=gemini: lista modelos disponibles del proveedor."""
    kv = _parse_pipe_kv_args(args)
    provider = (kv.get("provider") or "").strip().lower()
    if not provider:
        provider = (_effective_llm_triplet_for_chat_ui(db, chat_id)[0] or "").strip().lower()
    if not provider:
        return "Uso: /models provider=gemini"
    if provider != "gemini":
        return "Por ahora /models soporta solo provider=gemini."
    key = ((os.environ.get("GOOGLE_API_KEY") or "").strip() or (os.environ.get("GEMINI_API_KEY") or "").strip())
    if not key:
        return "Falta GOOGLE_API_KEY (o GEMINI_API_KEY) para listar modelos de Gemini."
    models, err = _gemini_models_list_from_api(key)
    if err:
        return f"No se pudo listar modelos Gemini. {err}"
    if not models:
        return "Gemini no devolvió modelos utilizables para generateContent."
    preview = "\n".join(f"- {m}" for m in models[:30])
    more = "" if len(models) <= 30 else f"\n... y {len(models) - 30} más."
    hint = "\nSugerencia: /model provider=gemini | model=gemini-2.0-flash"
    return f"Modelos Gemini disponibles ({len(models)}):\n{preview}{more}{hint}"


def execute_prompt(db: Any, chat_id: Any, args: str) -> str:
    """/prompt <worker_id> [--change <nuevo prompt>]: ver o cambiar el system prompt del template. worker_id debe ser uno de /roles."""
    from duckclaw.workers.factory import list_workers
    all_templates = list_workers()
    raw = (args or "").strip()
    if not raw:
        return "Uso: /prompt <worker_id> [--change <texto>]. Ver templates: /roles"
    if raw.startswith("--"):
        return "Indica un worker_id (ej. finanz, research_worker). Ver templates: /roles"
    change_marker = " --change "
    idx = raw.lower().find(change_marker)
    if idx >= 0:
        worker_id = raw[:idx].strip().lower()
        new_prompt = raw[idx + len(change_marker):].strip()
    else:
        worker_id = raw.split()[0].strip().lower() if raw.split() else ""
        new_prompt = ""
    if not worker_id:
        return "Uso: /prompt <worker_id> [--change <texto>]. Ver templates: /roles"
    if worker_id not in all_templates:
        return f"Template '{worker_id}' no encontrado. Disponibles (usa /roles): {', '.join(all_templates)}"
    if new_prompt:
        _set_global_config(db, f"system_prompt_{worker_id}", new_prompt)
        preview = new_prompt[:200] + "..." if len(new_prompt) > 200 else new_prompt
        return f"✅ System prompt de {worker_id} actualizado.\nVista previa: {preview}"
    current = get_effective_system_prompt(db, worker_id)
    if not current:
        return f"System prompt de {worker_id}: (vacío o por defecto del template).\nPara cambiar: /prompt {worker_id} --change <texto>"
    preview = current[:400] + "..." if len(current) > 400 else current
    return f"System prompt de {worker_id}:\n{preview}\n\nPara cambiar: /prompt {worker_id} --change <texto>"


def execute_help(db: Any, chat_id: Any) -> str:
    """/help: lista los fly commands disponibles."""
    entries = list(load_guardrail_pipe_table("fly_commands", "help_entries"))
    block = "\n".join(f"- {cmd} — {desc}" for cmd, desc in entries)
    return f"{load_guardrail('fly_commands', 'help_header')}\n{block}"


def _fly_reply_preview(s: str, max_len: int = 120) -> str:
    """Resumen de respuesta para [FLY] sin volcar secretos ni bloques enormes."""
    t = (s or "").replace("\n", " ").strip()
    if len(t) > max_len:
        return t[:max_len] + "..."
    return t


def _ssh_reach_icon(reach: str) -> str:
    r = (reach or "").lower()
    if "alcanzable" in r and "ok" in r:
        return "✅"
    if "no probado" in r or "falta config" in r:
        return "⚠️"
    return "❌"


def _capadonna_lake_status_lines(*, compact: bool) -> list[str]:
    """Líneas de diagnóstico Lake Capadonna (misma lógica que /lake; compact para /sensors)."""
    from duckclaw.forge.skills.quant_market_bridge import (
        capadonna_ssh_config_ok,
        lake_belief_observed_values,
        _resolved_identity_file,
    )

    host = (os.environ.get("CAPADONNA_SSH_HOST") or "").strip()
    user = (os.environ.get("CAPADONNA_SSH_USER") or "capadonna").strip()
    cmd_set = bool((os.environ.get("CAPADONNA_REMOTE_OHLC_CMD") or "").strip())
    idp = _resolved_identity_file()
    strict = capadonna_ssh_config_ok()
    host_v, online_v = lake_belief_observed_values()
    reach = "no probado (falta config)"
    if strict and host:
        ssh_args: list[str] = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5"]
        if idp:
            ssh_args.extend(["-i", idp])
        ssh_args.extend([f"{user}@{host}", "true"])
        try:
            proc = subprocess.run(ssh_args, capture_output=True, text=True, timeout=20)
            if proc.returncode == 0:
                reach = "alcanzable (ssh true OK)"
            else:
                err = (proc.stderr or proc.stdout or "").strip()[:200]
                reach = f"fallo rc={proc.returncode}" + (f" — {err}" if err else "")
        except FileNotFoundError:
            reach = "ssh no encontrado en PATH"
        except subprocess.TimeoutExpired:
            reach = "timeout 20s"
        except Exception as e:
            reach = str(e)[:120]
    if compact:
        icfg = "✅" if strict else "⚠️"
        ireach = _ssh_reach_icon(reach)
        return [
            "🌊 Lake Capadonna · SSH / Tailscale",
            f"   {icfg} Config operativa: {'sí' if strict else 'no'} · CAPADONNA_SSH_HOST: {'sí' if host else 'no'}",
            f"   📊 Creencias 0/1: lake_host_configured≈{int(host_v)} · lake_status_online≈{int(online_v)}",
            f"   {ireach} Alcance SSH (rápido): {reach}",
        ]
    lines = [
        "Capadonna Lake (SSH)",
        f"- CAPADONNA_SSH_HOST: {'sí' if host else 'no'}",
        f"- CAPADONNA_SSH_USER: {user}",
        f"- CAPADONNA_REMOTE_OHLC_CMD: {'sí' if cmd_set else 'no'}",
        f"- Clave SSH (-i): {idp or '(no definida / ssh-agent)'}",
        f"- Config lista para intentar: {'sí' if strict else 'no'}",
        f"- Semántica creencias (0/1): lake_host_configured≈{int(host_v)} lake_status_online≈{int(online_v)}",
        f"- Alcance SSH rápido: {reach}",
    ]
    return lines


def _probe_ibkr_portfolio(timeout_s: float = 8.0) -> str:
    api_url = os.environ.get("IBKR_PORTFOLIO_API_URL", "").strip()
    api_key = os.environ.get("IBKR_PORTFOLIO_API_KEY", "").strip()
    if not api_url or not api_key:
        return "Portafolio: no configurado (IBKR_PORTFOLIO_API_URL o IBKR_PORTFOLIO_API_KEY)"
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    req = urllib.request.Request(api_url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            if resp.status != 200:
                return f"Portafolio: HTTP {resp.status}"
            return "Portafolio: OK (HTTP 200, JSON)"
    except urllib.error.HTTPError as e:
        return f"Portafolio: HTTP {e.code}"[:80]
    except urllib.error.URLError as e:
        return f"Portafolio: red — {e.reason!s}"[:100]
    except Exception as e:
        return f"Portafolio: {str(e)[:80]}"


def _sensor_line_bullet(icon: str, text: str) -> str:
    """Una línea de detalle bajo un bloque /sensors (icono + texto)."""
    t = (text or "").strip()
    return f"   {icon} {t}" if t else f"   {icon}"


def _ibkr_detail_icon(line: str) -> str:
    low = (line or "").lower()
    if "no configurado" in low:
        return "⚠️"
    if "http 404" in low:
        return "⚠️"
    if ": ok" in low or " ok " in low:
        return "✅"
    if "http 200" in low:
        return "✅"
    return "❌"


def _probe_ibkr_market_data(timeout_s: float = 8.0) -> str:
    base = (os.environ.get("IBKR_MARKET_DATA_URL") or "").strip()
    if not base:
        return "Mercado OHLC: no configurado (IBKR_MARKET_DATA_URL)"
    q = urllib.parse.urlencode({"ticker": "SPY", "timeframe": "1d", "lookback_days": "3"})
    url = f"{base}&{q}" if "?" in base else f"{base}?{q}"
    req = urllib.request.Request(url, method="GET")
    token = (
        os.environ.get("IBKR_PORTFOLIO_API_KEY") or os.environ.get("IBKR_MARKET_DATA_API_KEY") or ""
    ).strip()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return "Mercado OHLC: respuesta no JSON"
        if isinstance(payload, dict):
            err = payload.get("error") or payload.get("message")
            if err and isinstance(err, str) and err.strip():
                return f"Mercado OHLC: API — {err.strip()[:80]}"
        return "Mercado OHLC: OK (JSON)"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return (
                "Mercado OHLC: HTTP 404 — la URL no existe en el API "
                "(despliega GET /api/market/ohlcv, p. ej. services/ibkr-ohlcv-api en :8002; ver spec Capadonna). "
                "Histórico 1d/1w/1M/moc vía lake SSH está bien; "
                "intradía necesita ese endpoint o quita IBKR_MARKET_DATA_URL del .env."
            )[:280]
        return f"Mercado OHLC: HTTP {e.code}"[:80]
    except urllib.error.URLError as e:
        return f"Mercado OHLC: red — {e.reason!s}"[:100]
    except Exception as e:
        return f"Mercado OHLC: {str(e)[:80]}"


def _browser_sandbox_sensor_lines() -> list[str]:
    """Líneas compactas para /sensors: manifest finanz, Docker, imagen browser, red en policy."""
    lines: list[str] = [
        "🌐 Browser sandbox · Playwright (`run_browser_sandbox`)",
    ]
    mf_bs: bool | None = None
    try:
        from duckclaw.workers.manifest import load_manifest

        mf_bs = bool(load_manifest("finanz").browser_sandbox)
    except Exception:
        mf_bs = None

    if mf_bs is None:
        lines.append(_sensor_line_bullet("⚠️", "No se pudo leer manifest finanz (browser_sandbox)"))
    elif mf_bs:
        lines.append(_sensor_line_bullet("✅", "Worker finanz: browser_sandbox=true"))
    else:
        lines.append(_sensor_line_bullet("⚠️", "Worker finanz: browser_sandbox=false — tool no registrada"))

    net_mode: str | None = None
    try:
        from duckclaw.forge import WORKERS_TEMPLATES_DIR
        from duckclaw.forge.schema import load_security_policy

        pol = load_security_policy("finanz", worker_dir=WORKERS_TEMPLATES_DIR / "finanz")
        net_mode = "bridge" if pol.network.default != "deny" else "deny"
        if net_mode == "deny":
            lines.append(
                _sensor_line_bullet(
                    "⚠️",
                    "security_policy finanz: red=deny — Playwright no podrá abrir URLs HTTP",
                )
            )
    except Exception:
        net_mode = None

    try:
        from duckclaw.graphs.sandbox import _browser_image_name, _docker_available
    except Exception as exc:
        lines.append(_sensor_line_bullet("❌", f"Sandbox no importable — {exc!s}"[:120]))
        return lines

    if not _docker_available():
        lines.append(_sensor_line_bullet("❌", "Docker no responde — run_browser_sandbox no arrancará"))
        return lines

    lines.append(_sensor_line_bullet("✅", "Docker ping OK"))

    img = _browser_image_name()
    env_override = bool((os.environ.get("STRIX_BROWSER_IMAGE") or "").strip())
    label = f"{img}" + (" · STRIX_BROWSER_IMAGE" if env_override else "")

    try:
        import docker  # noqa: PLC0415

        client = docker.from_env()
        client.images.get(img)
        lines.append(_sensor_line_bullet("✅", f"Imagen local · {label}"[:140]))
    except Exception:
        lines.append(
            _sensor_line_bullet(
                "⚠️",
                f"Imagen no encontrada localmente · {label} — build/pull antes del primer uso",
            )[:200]
        )

    if net_mode == "bridge":
        lines.append(_sensor_line_bullet("✅", "Policy red: bridge (HTTP permitido en contenedor browser)"))

    return lines


def execute_sensors(db: Any) -> str:
    """/sensors: resumen DuckDB, IBKR, Lake, Tavily, Reddit, Google Trends, browser sandbox (proceso gateway)."""
    blocks: list[str] = ["📡 Sensores Finanz", "═══════════════════════", ""]

    try:
        db.query("SELECT 1")
        blocks.append("🦆 DuckDB local")
        blocks.append(_sensor_line_bullet("✅", "Conectado · SELECT 1 OK"))
    except Exception as e:
        blocks.append("🦆 DuckDB local")
        blocks.append(_sensor_line_bullet("❌", f"Error — {str(e)[:100]}"))

    blocks.append("")
    blocks.append("🏦 IBKR (gateway)")
    p_line = _probe_ibkr_portfolio()
    m_line = _probe_ibkr_market_data()
    blocks.append(_sensor_line_bullet(_ibkr_detail_icon(p_line), p_line))
    blocks.append(_sensor_line_bullet(_ibkr_detail_icon(m_line), m_line))

    blocks.append("")
    try:
        blocks.extend(_capadonna_lake_status_lines(compact=True))
    except Exception as e:
        blocks.append("🌊 Lake Capadonna")
        blocks.append(_sensor_line_bullet("❌", f"Error — {str(e)[:100]}"))

    blocks.append("")
    try:
        from duckclaw.forge.skills.research_bridge import _tavily_available
    except Exception:
        _tavily_available = lambda: False  # type: ignore[misc, assignment]

    tav_pkg = False
    try:
        import tavily  # noqa: F401

        tav_pkg = True
    except ImportError:
        pass
    tav_key = bool((os.environ.get("TAVILY_API_KEY") or "").strip())
    tav_ready = bool(_tavily_available())
    blocks.append("🔎 Tavily (research)")
    if tav_ready and tav_pkg and tav_key:
        blocks.append(_sensor_line_bullet("✅", "Listo · paquete · TAVILY_API_KEY · bridge"))
    elif not tav_pkg and not tav_key:
        blocks.append(_sensor_line_bullet("⚠️", "Sin paquete tavily ni clave"))
    else:
        blocks.append(
            _sensor_line_bullet(
                "⚠️",
                f"Parcial · paquete={'sí' if tav_pkg else 'no'} · clave={'sí' if tav_key else 'no'} · bridge={'sí' if tav_ready else 'no'}",
            )
        )

    blocks.append("")
    try:
        from duckclaw.forge.skills.reddit_bridge import _mcp_available, _reddit_env_ready
    except Exception:
        redd_mcp = False
        redd_env = False
    else:
        redd_mcp = _mcp_available()
        redd_env = _reddit_env_ready()
    npx_ok = shutil.which("npx") is not None
    blocks.append("📣 Reddit · mcp-reddit")
    if redd_mcp and redd_env and npx_ok:
        blocks.append(_sensor_line_bullet("✅", "Librería MCP · env Reddit · npx en PATH"))
    else:
        blocks.append(
            _sensor_line_bullet(
                "⚠️",
                f"mcp_lib={'sí' if redd_mcp else 'no'} · env={'sí' if redd_env else 'no'} · npx={'sí' if npx_ok else 'no'}",
            )
        )

    blocks.append("")
    try:
        from duckclaw.forge.skills.google_trends_bridge import (
            _default_stdio_command_and_args,
            _mcp_available as _gt_mcp_ok,
        )
    except Exception:
        gt_cmd = ""
        gt_args: list[str] = []
        gt_mcp = False
    else:
        gt_mcp = _gt_mcp_ok()
        gt_cmd, gt_args = _default_stdio_command_and_args()
    blocks.append("📈 Google Trends MCP")
    if not gt_cmd:
        blocks.append(_sensor_line_bullet("⚠️", "Stdio no resuelto (google-trends-mcp / uvx en PATH)"))
    else:
        arg_hint = f" {' '.join(gt_args)}" if gt_args else ""
        tid = "✅" if gt_mcp else "⚠️"
        blocks.append(
            _sensor_line_bullet(
                tid,
                f"mcp_lib={'sí' if gt_mcp else 'no'} · stdio: {gt_cmd}{arg_hint}",
            )
        )

    blocks.append("")
    try:
        blocks.extend(_browser_sandbox_sensor_lines())
    except Exception as e:
        blocks.append("🌐 Browser sandbox · Playwright (`run_browser_sandbox`)")
        blocks.append(_sensor_line_bullet("❌", f"Error — {str(e)[:100]}"))

    return "\n".join(blocks)


def execute_lake_status() -> str:
    """/lake [status]: variables Capadonna y prueba SSH corta (BatchMode, ConnectTimeout=5)."""
    try:
        lines = _capadonna_lake_status_lines(compact=False)
    except Exception as e:
        return f"Lake: no se pudo cargar el bridge quant: {e}"
    return "\n".join(lines)


_TRADING_SESSIONS_DDL = """
CREATE SCHEMA IF NOT EXISTS quant_core;
CREATE TABLE IF NOT EXISTS quant_core.trading_sessions (
  id VARCHAR PRIMARY KEY,
  mode VARCHAR NOT NULL,
  tickers VARCHAR NOT NULL DEFAULT '',
  session_uid VARCHAR,
  session_goal JSON,
  status VARCHAR NOT NULL DEFAULT 'ACTIVE',
  anchor_equity DOUBLE,
  peak_equity DOUBLE,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE quant_core.trading_sessions ADD COLUMN IF NOT EXISTS session_uid VARCHAR;
ALTER TABLE quant_core.trading_sessions ADD COLUMN IF NOT EXISTS session_goal JSON;
ALTER TABLE quant_core.trading_sessions ADD COLUMN IF NOT EXISTS anchor_equity DOUBLE;
ALTER TABLE quant_core.trading_sessions ADD COLUMN IF NOT EXISTS peak_equity DOUBLE;
"""

_TRADING_RISK_DDL = """
CREATE SCHEMA IF NOT EXISTS quant_core;
CREATE TABLE IF NOT EXISTS quant_core.trading_risk_constraints (
  id VARCHAR PRIMARY KEY,
  max_drawdown_pct DOUBLE,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# Fila singleton en quant_core.trading_sessions (PK lógica del “estado de sesión”).
_TRADING_SESSION_ROW_ID = "active"
_QUANT_TRADER_TEMPLATE_ID = "Quant-Trader"
_TRADING_SESSION_PNL_SNAPSHOTS_KEY = "trading_session_pnl_snapshots_json"
_TRADING_SESSION_PNL_HIST_UID_KEY = "trading_session_pnl_hist_uid"
_PNL_SNAPSHOT_SYNTH_STEP_SEC = 60.0


def _snap_epoch_from_obj(obj: dict[str, Any]) -> float | None:
    if not isinstance(obj, dict):
        return None
    for k in ("epoch", "t", "ts", "time"):
        if k in obj and obj[k] is not None:
            try:
                return float(obj[k])
            except (TypeError, ValueError):
                continue
    return None


def _snap_pnl_from_obj(obj: dict[str, Any]) -> float | None:
    if not isinstance(obj, dict):
        return None
    for k in ("pnl", "p", "v"):
        if k in obj and obj[k] is not None:
            try:
                return float(obj[k])
            except (TypeError, ValueError):
                continue
    return None


def _pnl_snapshots_parse_stored(raw: Any, *, now: float) -> list[tuple[float, float]]:
    """
    Acepta v1 lista de floats o v2 [{epoch, pnl}, ...].
    v1 obtiene timestamps sintéticos hacia atrás desde ``now``.
    """
    data = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw) if raw.strip() else []
        except Exception:
            return []
    if not isinstance(data, list) or not data:
        return []
    if isinstance(data[0], dict):
        out: list[tuple[float, float]] = []
        for it in data:
            if not isinstance(it, dict):
                continue
            ep = _snap_epoch_from_obj(it)
            pv = _snap_pnl_from_obj(it)
            if ep is None or pv is None:
                continue
            out.append((float(ep), float(pv)))
        out.sort(key=lambda z: z[0])
        return out
    floats: list[float] = []
    for x in data:
        try:
            floats.append(float(x))
        except (TypeError, ValueError):
            continue
    if not floats:
        return []
    n = len(floats)
    return [
        (float(now) - float(n - 1 - i) * _PNL_SNAPSHOT_SYNTH_STEP_SEC, floats[i])
        for i in range(n)
    ]


def _pnl_snapshots_dedupe_epoch(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Misma lógica epsilon que la deduplicación por PnL; conserva el último epoch del tramo."""
    out: list[tuple[float, float]] = []
    for ep, fx in points or []:
        if not out:
            out.append((float(ep), float(fx)))
            continue
        prev = out[-1][1]
        eps = max(1e-4, 1e-6 * max(1.0, abs(fx), abs(prev)))
        if abs(fx - prev) > eps:
            out.append((float(ep), float(fx)))
        else:
            out[-1] = (float(ep), float(fx))
    return out


def _pnl_snapshots_to_floats(points: list[tuple[float, float]]) -> list[float]:
    return [float(p) for _, p in points]


def _pnl_snapshots_serialize_v2(points: list[tuple[float, float]]) -> str:
    return json.dumps(
        [{"epoch": float(ep), "pnl": float(pv)} for ep, pv in points],
        ensure_ascii=False,
    )


def _snapshot_epoch_points_for_session(db: Any, chat_id: Any, session_uid: str) -> list[tuple[float, float]]:
    uid = (session_uid or "").strip()
    if not uid or uid == "n/a":
        return []
    hist_uid_s = str(get_chat_state(db, chat_id, _TRADING_SESSION_PNL_HIST_UID_KEY) or "").strip()
    if hist_uid_s != uid:
        return []
    raw = get_chat_state(db, chat_id, _TRADING_SESSION_PNL_SNAPSHOTS_KEY) or "[]"
    return _pnl_snapshots_dedupe_epoch(_pnl_snapshots_parse_stored(raw, now=time.time()))


def _dedupe_trading_session_snapshots(snaps: list[Any]) -> list[float]:
    """Elimina valores consecutivos ~iguales (mismo snapshot repetido en cada /status)."""
    out: list[float] = []
    for x in snaps or []:
        try:
            fx = float(x)
        except (TypeError, ValueError):
            continue
        if not out:
            out.append(fx)
            continue
        prev = out[-1]
        eps = max(1e-4, 1e-6 * max(1.0, abs(fx), abs(prev)))
        if abs(fx - prev) > eps:
            out.append(fx)
    return out


def _quant_is_drawdown_goal(goal: dict) -> bool:
    k = (goal.get("belief_key") or "").strip().lower()
    if k == "max_portfolio_drawdown_pct":
        return True
    t = (goal.get("title") or "").lower()
    return "drawdown" in t or "max dd" in t


def _quant_normalize_drawdown_goal(goal: dict) -> None:
    """Ajusta belief_key y target (0–1) para límites de DD."""
    goal["belief_key"] = "max_portfolio_drawdown_pct"
    try:
        tv = float(goal.get("target_value") or 0.0)
    except (TypeError, ValueError):
        tv = 0.0
    if tv > 1.0:
        tv = tv / 100.0
    goal["target_value"] = max(0.0, min(1.0, tv))


def _quant_mirror_max_drawdown_to_vault(
    db: Any,
    *,
    tenant_id: str,
    max_dd: float,
) -> tuple[bool, str]:
    upsert = """
INSERT INTO quant_core.trading_risk_constraints (id, max_drawdown_pct)
VALUES ('active', ?)
ON CONFLICT (id) DO UPDATE SET
  max_drawdown_pct = excluded.max_drawdown_pct,
  updated_at = now()
"""
    return _vault_apply_sql_statements(
        db,
        [
            (_TRADING_RISK_DDL, None),
            (upsert, [float(max_dd)]),
        ],
        tenant_id=str(tenant_id or "default").strip() or "default",
    )


def _quant_clear_risk_constraints_vault(db: Any, *, tenant_id: str) -> tuple[bool, str]:
    return _vault_apply_sql_statements(
        db,
        [("DELETE FROM quant_core.trading_risk_constraints WHERE id = 'active'", None)],
        tenant_id=str(tenant_id or "default").strip() or "default",
    )


class TradingSessionGoal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # objective: Literal["maximize_pnl", "rebalance_hrp"] = "maximize_pnl"
    objective: Literal["maximize_pnl", "rebalance_hrp", "overnight_gap_squeeze"] = "maximize_pnl"
    max_drawdown_pct: float = 2.0
    position_size_pct: float = 5.0
    signal_threshold: str = "GAS"
    tickers: list[str] = []
    mode: str = "paper"


class TradingSessionCliArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Optional[str] = None
    tickers_csv: str = ""
    confirm: bool = False
    stop: bool = False
    status: bool = False
    max_drawdown_pct: float = 2.0
    position_size_pct: float = 5.0
    signal_threshold: str = "GAS"
    # objective: Literal["maximize_pnl", "rebalance_hrp"] = "maximize_pnl"
    objective: Literal["maximize_pnl", "rebalance_hrp", "overnight_gap_squeeze"] = "maximize_pnl"


class QuantCycleCliArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tickers_csv: str = ""
    timeframe: str = "1h"
    lookback_days: int = 20
    objective: Literal["maximize_pnl", "rebalance_hrp", "overnight_gap_squeeze"] = "maximize_pnl"
    execute: Literal["auto", "off"] = "auto"
    signal_threshold: str = "GAS"
    weight_pct: float = 5.0


def _parse_trading_session_cli(args: str) -> tuple[Optional[TradingSessionCliArgs], Optional[str]]:
    """Parsea flags de /trading-session."""
    mode: Optional[str] = None
    tickers_raw: list[str] = []
    confirm = False
    stop = False
    status = False
    max_drawdown = 2.0
    position_size = 5.0
    signal_threshold = "GAS"
    objective: str = "maximize_pnl"
    tokens = (args or "").strip().split()
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t == "--mode" and i + 1 < len(tokens):
            mode = tokens[i + 1].strip().lower()
            i += 2
            continue
        if t == "--tickers" and i + 1 < len(tokens):
            tickers_raw = [x.strip().upper() for x in tokens[i + 1].split(",") if x.strip()]
            i += 2
            continue
        if t == "--confirm":
            confirm = True
            i += 1
            continue
        if t == "--stop":
            stop = True
            i += 1
            continue
        if t == "--status":
            status = True
            i += 1
            continue
        if t == "--max-drawdown" and i + 1 < len(tokens):
            try:
                max_drawdown = float(tokens[i + 1])
            except ValueError:
                return None, "--max-drawdown debe ser numérico"
            i += 2
            continue
        if t == "--position-size" and i + 1 < len(tokens):
            try:
                position_size = float(tokens[i + 1])
            except ValueError:
                return None, "--position-size debe ser numérico"
            i += 2
            continue
        if t == "--signal" and i + 1 < len(tokens):
            signal_threshold = str(tokens[i + 1] or "").strip().upper()
            i += 2
            continue
        if t == "--objective" and i + 1 < len(tokens):
            objective = str(tokens[i + 1] or "").strip().lower()
            i += 2
            continue
        i += 1
    if stop and status:
        return None, "Usa --stop o --status, no ambos."
    if (not stop and not status) and not mode:
        return None, "Falta --mode paper|live"
    if mode and mode not in ("paper", "live"):
        return None, "mode debe ser paper o live"
    if objective not in ("maximize_pnl", "rebalance_hrp", "overnight_gap_squeeze"):
        if stop or status:
            objective = "maximize_pnl"
        else:
            return None, "objective debe ser maximize_pnl, rebalance_hrp u overnight_gap_squeeze"
    seen: set[str] = set()
    tickers_ordered: list[str] = []
    for x in tickers_raw:
        if x not in seen:
            seen.add(x)
            tickers_ordered.append(x)
    try:
        parsed = TradingSessionCliArgs.model_validate(
            {
                "mode": mode,
                "tickers_csv": ",".join(tickers_ordered),
                "confirm": bool(confirm),
                "stop": bool(stop),
                "status": bool(status),
                "max_drawdown_pct": float(max_drawdown),
                "position_size_pct": float(position_size),
                "signal_threshold": signal_threshold or "GAS",
                "objective": str(objective).strip().lower() or "maximize_pnl",
            }
        )
    except ValidationError as exc:
        return None, f"flags inválidos: {exc}"
    return parsed, None


def _parse_quant_cycle_cli(args: str) -> tuple[Optional[QuantCycleCliArgs], Optional[str]]:
    """Parsea flags de /quant_cycle."""
    tickers_raw: list[str] = []
    timeframe = "1h"
    lookback_days = 20
    objective = "maximize_pnl"
    execute = "auto"
    signal_threshold = "GAS"
    weight_pct = 5.0
    tokens = (args or "").strip().split()
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t == "--tickers" and i + 1 < len(tokens):
            tickers_raw = [x.strip().upper() for x in str(tokens[i + 1] or "").split(",") if x.strip()]
            i += 2
            continue
        if t == "--timeframe" and i + 1 < len(tokens):
            timeframe = str(tokens[i + 1] or "").strip()
            i += 2
            continue
        if t in ("--lookback_days", "--lookback-days") and i + 1 < len(tokens):
            try:
                lookback_days = int(tokens[i + 1])
            except ValueError:
                return None, "--lookback_days debe ser entero"
            i += 2
            continue
        if t == "--objective" and i + 1 < len(tokens):
            objective = str(tokens[i + 1] or "").strip().lower()
            i += 2
            continue
        if t == "--execute" and i + 1 < len(tokens):
            execute = str(tokens[i + 1] or "").strip().lower()
            i += 2
            continue
        if t == "--signal" and i + 1 < len(tokens):
            signal_threshold = str(tokens[i + 1] or "").strip().upper()
            i += 2
            continue
        if t in ("--weight", "--weight-pct") and i + 1 < len(tokens):
            try:
                weight_pct = float(tokens[i + 1])
            except ValueError:
                return None, "--weight debe ser numérico"
            i += 2
            continue
        i += 1
    if objective not in ("maximize_pnl", "rebalance_hrp", "overnight_gap_squeeze"):
        return None, "objective debe ser maximize_pnl, rebalance_hrp u overnight_gap_squeeze"
    if execute not in ("auto", "off"):
        return None, "execute debe ser auto u off"
    if not re.fullmatch(r"[A-Za-z0-9]+", timeframe or ""):
        return None, "timeframe inválido (solo alfanumérico)"
    if lookback_days < 1 or lookback_days > 4000:
        return None, "lookback_days debe estar entre 1 y 4000"
    if weight_pct <= 0:
        return None, "weight debe ser mayor a 0"
    allowed_threshold = {"SOLID", "LIQUID", "GAS", "PLASMA"}
    if signal_threshold not in allowed_threshold:
        signal_threshold = "GAS"
    seen: set[str] = set()
    tickers_ordered: list[str] = []
    for x in tickers_raw:
        if not re.fullmatch(r"[A-Z0-9]{1,8}", x):
            return None, f"ticker inválido: {x}"
        if x not in seen:
            seen.add(x)
            tickers_ordered.append(x)
    try:
        parsed = QuantCycleCliArgs.model_validate(
            {
                "tickers_csv": ",".join(tickers_ordered),
                "timeframe": timeframe,
                "lookback_days": int(lookback_days),
                "objective": objective,
                "execute": execute,
                "signal_threshold": signal_threshold,
                "weight_pct": float(weight_pct),
            }
        )
    except ValidationError as exc:
        return None, f"flags inválidos: {exc}"
    return parsed, None


def _session_goal_from_cli(parsed: TradingSessionCliArgs) -> TradingSessionGoal:
    threshold = str(parsed.signal_threshold or "GAS").strip().upper() or "GAS"
    allowed = {"SOLID", "LIQUID", "GAS", "PLASMA"}
    if threshold not in allowed:
        threshold = "GAS"
    tickers = [x.strip().upper() for x in (parsed.tickers_csv or "").split(",") if x.strip()]
    oj = str(getattr(parsed, "objective", "maximize_pnl") or "maximize_pnl").strip().lower()
    if oj not in ("maximize_pnl", "rebalance_hrp", "overnight_gap_squeeze"):
        oj = "maximize_pnl"
    return TradingSessionGoal.model_validate(
        {
            "objective": oj,
            "max_drawdown_pct": max(0.1, float(parsed.max_drawdown_pct)),
            "position_size_pct": max(0.1, float(parsed.position_size_pct)),
            "signal_threshold": threshold,
            "tickers": tickers,
            "mode": str(parsed.mode or "paper").strip().lower() or "paper",
        }
    )


def _vault_apply_sql_statements(
    db: Any,
    statements: list[tuple[str, Optional[list[Any]]]],
    *,
    tenant_id: str,
) -> tuple[bool, str]:
    """Ejecuta sentencias en la bóveda o vía cola Redis si el handle es read_only."""
    raw_path = str(getattr(db, "_path", "") or "").strip()
    if not raw_path or raw_path == ":memory:":
        return False, "Ruta de bóveda no resuelta"
    resolved = str(Path(raw_path).expanduser().resolve())
    uid = _infer_user_id_for_audit_queue(resolved)
    tid = str(tenant_id or "default").strip() or "default"

    if not _skip_runtime_ddl(db):
        try:
            for sql, params in statements:
                if params is not None:
                    db.execute(sql, params)
                else:
                    db.execute(sql)
            return True, ""
        except Exception as exc:
            return False, str(exc)[:500]

    try:
        from duckclaw.db_write_queue import enqueue_duckdb_write_sync, poll_task_status_sync
    except Exception as exc:
        return False, f"cola DuckDB no disponible: {exc}"

    released_ro = False
    try:
        release = getattr(db, "release_file_handle_for_external_writer", None)
        susp = getattr(db, "suspend_readonly_file_handle", None)
        resu = getattr(db, "resume_readonly_file_handle", None)
        if callable(release):
            release()
            released_ro = bool(callable(resu))
        elif callable(susp) and callable(resu):
            susp()
            released_ro = True
        for sql, params in statements:
            write_tid = enqueue_duckdb_write_sync(
                db_path=resolved,
                query=sql.strip(),
                params=list(params or []),
                user_id=uid,
                tenant_id=tid,
            ),
            st = poll_task_status_sync(write_tid, timeout_sec=30.0)
            if st is None:
                return False, "timeout esperando db-writer"
            if st.status != "success":
                return False, (st.detail or "db-writer failed")[:500]
        return True, ""
    finally:
        if released_ro:
            try:
                resu2 = getattr(db, "resume_readonly_file_handle", None)
                if callable(resu2):
                    resu2()
            except Exception:
                pass


def set_chat_state_via_vault(
    db: Any,
    chat_id: Any,
    key_suffix: str,
    value: str,
    *,
    tenant_id: str = "default",
) -> tuple[bool, str]:
    """
    Persiste ``agent_config`` vía ``_vault_apply_sql_statements`` — funciona con DuckClaw RO (cola db-writer).
    Fallback a ``set_chat_state`` solo si vault falla (p. ej. redis ausente).
    """
    tid = str(tenant_id or "default").strip() or "default"
    upsert_sql = (
        "INSERT INTO agent_config (key, value) VALUES (?, ?) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP"
    )
    ck = _chat_key(chat_id, key_suffix)[:240]
    vv = str(value)[:16384]
    ok, err = _vault_apply_sql_statements(db, [(upsert_sql, [ck, vv])], tenant_id=tid)
    if ok:
        return True, ""
    try:
        set_chat_state(db, chat_id, key_suffix, vv)
        return True, ""
    except Exception as exc:
        combined = "; ".join(x for x in (err, str(exc)) if x).strip()
        return False, (combined or "persist_failed")[:500]


def schedule_quant_trading_proactive_ticks(
    db: Any,
    *,
    chat_id: Any,
    tenant_id: str,
    interval_seconds: int = 0,
) -> str:
    """
    Programa revisión proactiva (TRADING_TICK vía ticker /crons) para Quant con sesión ACTIVE.
    Persistencia segura desde worker RO vía vault writer. Si ``interval_seconds`` es 0, solo garantiza delta
    default (si hace falta) y meta ``trading_session`` como ``/trading-session``.
    """
    tid = str(tenant_id or "default").strip() or "default"
    cid = chat_id
    try:
        raw = db.query(
            "SELECT session_uid, status FROM quant_core.trading_sessions WHERE id = 'active' LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception as exc:
        return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)
    if not rows or not isinstance(rows[0], dict):
        return json.dumps(
            {"status": "error", "error": "NO_ACTIVE_ROW", "hint": "Abre sesión con /trading-session o read_sql debe mostrar ACTIVE."},
            ensure_ascii=False,
        )
    row = rows[0]
    if str(row.get("status") or "").strip().upper() != "ACTIVE":
        return json.dumps(
            {"status": "error", "error": "SESSION_NOT_ACTIVE", "status_actual": row.get("status")},
            ensure_ascii=False,
        )
    session_uid = str(row.get("session_uid") or "").strip()
    if not session_uid:
        return json.dumps({"status": "error", "error": "MISSING_SESSION_UID"}, ensure_ascii=False)

    if int(interval_seconds) > 0:
        secs_iv = max(
            GOALS_DELTA_MIN_SECONDS,
            min(int(interval_seconds), GOALS_DELTA_MAX_SECONDS),
        )
        fire = str(time.time())
        blob_meta = json.dumps(
            {"trigger": "trading_session", "session_uid": session_uid},
            ensure_ascii=False,
        )
        for suf, val in (
            (_GOALS_CRON_WALL_KEY, ""),
            (_GOALS_DELTA_SECONDS_KEY, str(secs_iv)),
            (_GOALS_PROACTIVE_LAST_FIRE_KEY, fire),
            (_GOALS_PROACTIVE_ANCHOR_KEY, fire),
            (_GOALS_DELTA_ANCHOR_LEGACY_KEY, fire),
            (_GOALS_PROACTIVE_TENANT_KEY, tid),
            (_GOALS_DELTA_META_KEY, blob_meta),
        ):
            ok_w, er_w = set_chat_state_via_vault(db, cid, suf, val, tenant_id=tid)
            if not ok_w:
                return json.dumps({"status": "error", "error": er_w or "persist_failed"}, ensure_ascii=False)
        _ensure_trading_session_goals_delta(
            db, chat_id=cid, tenant_id=tid, session_uid=session_uid
        )
        human = format_goals_delta_interval_human(secs_iv)
        return json.dumps(
            {
                "status": "ok",
                "session_uid": session_uid,
                "interval_seconds": secs_iv,
                "interval_human": human,
                "note": "TRADING_TICK / heartbeat: mismo esquema que /crons --delta con trigger trading_session.",
            },
            ensure_ascii=False,
        )

    enabled, secs = _ensure_trading_session_goals_delta(
        db,
        chat_id=cid,
        tenant_id=tid,
        session_uid=session_uid,
    )
    return json.dumps(
        {
            "status": "ok",
            "scheduler_bootstrap_was_needed": enabled,
            "interval_seconds": secs,
            "interval_human": format_goals_delta_interval_human(secs),
            "session_uid": session_uid,
        },
        ensure_ascii=False,
    )


def _ensure_trading_session_goals_delta(
    db: Any,
    *,
    chat_id: Any,
    tenant_id: str,
    session_uid: str,
) -> tuple[bool, int]:
    """Activa goals delta por default (5m) si hace falta; siempre enlaza meta al tick de sesión Quant."""
    tid = str(tenant_id or "default").strip() or "default"
    try:
        current = int((get_chat_state(db, chat_id, _GOALS_DELTA_SECONDS_KEY) or "0").strip() or "0")
    except ValueError:
        current = 0
    default_secs = 300
    enabled = False
    if current <= 0:
        current = default_secs
        now_s = str(time.time())
        for suf, val in (
            (_GOALS_DELTA_SECONDS_KEY, str(current)),
            (_GOALS_PROACTIVE_LAST_FIRE_KEY, ""),
            (_GOALS_PROACTIVE_ANCHOR_KEY, now_s),
            (_GOALS_DELTA_ANCHOR_LEGACY_KEY, now_s),
        ):
            ok_p, er_p = set_chat_state_via_vault(db, chat_id, suf, val, tenant_id=tid)
            if not ok_p:
                return False, current
        enabled = True
    ok_t, er_t = set_chat_state_via_vault(
        db, chat_id, _GOALS_PROACTIVE_TENANT_KEY, tid, tenant_id=tid
    )
    if not ok_t:
        return False, current
    ok_m, er_m = set_chat_state_via_vault(
        db,
        chat_id,
        _GOALS_DELTA_META_KEY,
        json.dumps({"trigger": "trading_session", "session_uid": session_uid}, ensure_ascii=False),
        tenant_id=tid,
    )
    if not ok_m:
        return False, current
    _sess_obj = ""
    try:
        _raw_s = db.query(
            "SELECT session_goal FROM quant_core.trading_sessions WHERE id = 'active' LIMIT 1"
        )
        _rows_s = json.loads(_raw_s) if isinstance(_raw_s, str) else (_raw_s or [])
        if _rows_s and isinstance(_rows_s[0], dict):
            _sg = _rows_s[0].get("session_goal")
            if isinstance(_sg, dict):
                _sess_obj = str(_sg.get("objective") or "").strip().lower()
            elif isinstance(_sg, str) and _sg.strip():
                try:
                    _sgj = json.loads(_sg)
                    if isinstance(_sgj, dict):
                        _sess_obj = str(_sgj.get("objective") or "").strip().lower()
                except Exception:
                    _sess_obj = ""
    except Exception:
        _sess_obj = ""

    if not get_manager_goals(db, chat_id):
        _seed_goal = {
            "belief_key": "hrp_session_rebalance",
            "target_value": 0.0,
            "threshold": 0.0,
            "observed_value": None,
            "title": "Rebalanceo HRP (pypfopt) vs cartera IBKR en cada tick",
        }
        if _sess_obj == "overnight_gap_squeeze":
            _seed_goal = {
                "belief_key": "overnight_gap_squeeze_session",
                "target_value": 0.0,
                "threshold": 0.0,
                "observed_value": None,
                "title": "Overnight Gap Squeeze (cierre + gap) en cada tick",
            }
        _okg, _erg = set_chat_state_via_vault(
            db,
            chat_id,
            "goals",
            json.dumps([_seed_goal], ensure_ascii=False),
            tenant_id=tid,
        )
        if not _okg:
            set_manager_goals(db, chat_id, [_seed_goal])
    return enabled, current


def _close_active_trading_session(
    db: Any,
    *,
    chat_id: Any,
    tenant_id: str,
) -> tuple[bool, str]:
    """Cierra sesión ACTIVE y limpia scheduler creado por /trading-session."""
    session_uid = ""
    try:
        raw = db.query(
            "SELECT session_uid FROM quant_core.trading_sessions WHERE id = 'active' LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if rows and isinstance(rows[0], dict):
            session_uid = str(rows[0].get("session_uid") or "").strip()
    except Exception:
        session_uid = ""
    ok, detail = _vault_apply_sql_statements(
        db,
        [
            (_TRADING_SESSIONS_DDL, None),
            ("UPDATE quant_core.trading_sessions SET status='CLOSED', updated_at=now() WHERE id = ?", [_TRADING_SESSION_ROW_ID]),
        ],
        tenant_id=tenant_id,
    )
    if not ok:
        return False, detail
    meta_raw = (get_chat_state(db, chat_id, _GOALS_DELTA_META_KEY) or "").strip()
    if '"trigger": "trading_session"' in meta_raw or '"trigger":"trading_session"' in meta_raw:
        clear_goals_proactive_schedule(db, chat_id)
        set_chat_state(db, chat_id, _GOALS_DELTA_META_KEY, "")
        set_chat_state(db, chat_id, _GOALS_DELTA_ANCHOR_LEGACY_KEY, "")
    pnl = 0.0
    if session_uid:
        try:
            esc_uid = session_uid.replace("'", "''")
            raw2 = db.query(
                "SELECT COALESCE(SUM(COALESCE(unrealized_pnl,0)),0) AS pnl "
                "FROM quant_core.trade_signals "
                f"WHERE session_uid = '{esc_uid}' AND status='EXECUTED'"
            )
            rows2 = json.loads(raw2) if isinstance(raw2, str) else (raw2 or [])
            if rows2 and isinstance(rows2[0], dict):
                pnl = float(rows2[0].get("pnl") or 0.0)
        except Exception:
            pnl = 0.0
    try:
        set_chat_state(db, chat_id, _TRADING_SESSION_PNL_SNAPSHOTS_KEY, "[]")
        set_chat_state(db, chat_id, _TRADING_SESSION_PNL_HIST_UID_KEY, "")
        set_chat_state(db, chat_id, "trading_session_last_pnl", "")
        set_chat_state(db, chat_id, "trading_session_prev_pnl", "")
        set_chat_state(db, chat_id, "trading_session_pct_change", "")
    except Exception:
        pass
    return True, f"session_uid={session_uid or 'n/a'} | pnl_estimado={pnl:.2f}"


def _session_notionals_from_ibkr_for_tickers(
    parts: list[str],
) -> tuple[dict[str, float], str | None, float | None]:
    """
    Nocional ``|market_value|`` por símbolo en ``parts``, snapshot IBKR (mismo contrato que
    ``get_ibkr_portfolio``). Retorna ``(mapa, err, total_cuenta)`` donde ``total_cuenta`` es
    ``total_value`` / net liq. del payload (para % como en el resumen IBKR); ``None`` si no es usable.
    """
    import os

    from duckclaw.forge.skills.ibkr_bridge import _ibkr_resolve_payload_with_optional_alt

    api_url = (os.environ.get("IBKR_PORTFOLIO_API_URL") or "").strip()
    api_key = (os.environ.get("IBKR_PORTFOLIO_API_KEY") or "").strip()
    positions_url = (os.environ.get("IBKR_PORTFOLIO_POSITIONS_URL") or "").strip()
    zero = {p: 0.0 for p in parts}
    if not api_url or not api_key:
        return zero, "ibkr_env_missing", None

    try:
        data, _eff, _cfg = _ibkr_resolve_payload_with_optional_alt(
            api_url, api_key, positions_url
        )
    except Exception as exc:
        return zero, str(exc)[:200], None

    if not isinstance(data, dict):
        return zero, "ibkr_payload_invalid", None

    portfolio = data.get("portfolio") or data.get("positions") or []
    if isinstance(portfolio, dict):
        portfolio = list(portfolio.values()) if portfolio else []

    tv = data.get("total_value")
    if tv is None:
        tv = data.get("net_liquidation") or data.get("equity") or data.get("value") or 0
    try:
        total_account_f = float(tv)
    except (TypeError, ValueError):
        total_account_f = 0.0
    if total_account_f <= 0 and isinstance(portfolio, list):
        for pos in portfolio:
            if not isinstance(pos, dict):
                continue
            mv0 = pos.get("market_value") or pos.get("marketValue") or pos.get("value") or 0
            try:
                total_account_f += abs(float(mv0))
            except (TypeError, ValueError):
                continue

    total_account: float | None = total_account_f if total_account_f > 1e-9 else None

    seen = {p.upper() for p in parts}
    notionals: dict[str, float] = {p: 0.0 for p in parts}
    if not isinstance(portfolio, list):
        return notionals, None, total_account

    for pos in portfolio:
        if not isinstance(pos, dict):
            continue
        sym = str(pos.get("symbol") or pos.get("ticker") or "").strip().upper()
        if sym not in seen:
            continue
        mv = pos.get("market_value") or pos.get("marketValue") or pos.get("value") or 0
        try:
            notionals[sym] += abs(float(mv))
        except (TypeError, ValueError):
            continue

    return notionals, None, total_account


def _session_participation_breakdown(
    db: Any, tickers_csv: str
) -> tuple[list[tuple[str, float, float]], bool, str, tuple[str, float, float] | None]:
    """
    Retorna filas ``(símbolo, %, nocional_usd)`` en el orden del CSV de sesión,
    ``True`` si los % vienen de nocional, ``False`` si reparto igual,
    ``weight_source`` en ``{"db", "ibkr", "equal"}``,
    y opcionalmente ``("Cash", %, usd)`` cuando IBKR aporta ``total_value`` y queda
    remanente ``total_value - sum(|mv| tickers sesión)`` (efectivo + posiciones fuera del CSV).
    """
    parts = [x.strip().upper() for x in (tickers_csv or "").split(",") if x.strip()]
    if not parts:
        return [], False, "equal", None
    esc = [p.replace("'", "''") for p in parts]
    in_list = ",".join(f"'{t}'" for t in esc)
    notionals: dict[str, float] = {t: 0.0 for t in parts}
    seen: set[str] = set(parts)
    n_db_rows = 0
    n_rows_dict = 0
    sample_unknown: list[str] = []
    query_err: str | None = None
    try:
        raw = db.query(
            f"SELECT ticker, qty, current_price FROM quant_core.portfolio_positions "
            f"WHERE UPPER(TRIM(ticker)) IN ({in_list})"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        n_db_rows = len(rows or [])
        for it in rows or []:
            if not isinstance(it, dict):
                continue
            n_rows_dict += 1
            sym = str(it.get("ticker") or "").strip().upper()
            if sym not in seen:
                if len(sample_unknown) < 5 and sym:
                    sample_unknown.append(sym[:16])
                continue
            try:
                q = float(it.get("qty") or 0.0)
                px = float(it.get("current_price") or 0.0)
            except (TypeError, ValueError):
                continue
            notionals[sym] = abs(q * px)
    except Exception as exc:
        query_err = str(exc)[:200]
        notionals = {t: 0.0 for t in parts}
    total_n = sum(notionals.values())
    uses_n = total_n > 1e-9
    n_nonzero = sum(1 for v in notionals.values() if v > 1e-9)
    weight_source = "db" if uses_n else "equal"
    ibkr_err: str | None = None
    ibkr_attempted = False
    pct_denom = total_n
    ibkr_pct_denom_src: str | None = None
    if not uses_n:
        ibkr_attempted = True
        ibkr_map, ibkr_err, ibkr_acct_total = _session_notionals_from_ibkr_for_tickers(parts)
        total_ibkr = sum(ibkr_map.values())
        if total_ibkr > 1e-9:
            notionals = ibkr_map
            total_n = total_ibkr
            uses_n = True
            weight_source = "ibkr"
            n_nonzero = sum(1 for v in notionals.values() if v > 1e-9)
            if ibkr_acct_total is not None and ibkr_acct_total > 1e-9:
                pct_denom = ibkr_acct_total
                ibkr_pct_denom_src = "ibkr_total_value"
            else:
                pct_denom = total_ibkr
                ibkr_pct_denom_src = "sum_session_abs_mv_fallback"
    if uses_n:
        d = pct_denom if pct_denom > 1e-9 else total_n
        out = [(sym, notionals[sym] / d * 100.0, notionals[sym]) for sym in parts]
        cash_row: tuple[str, float, float] | None = None
        if (
            weight_source == "ibkr"
            and ibkr_pct_denom_src == "ibkr_total_value"
            and float(d) > 1e-9
        ):
            session_mv_sum = sum(notionals[s] for s in parts)
            rem_usd = max(float(d) - session_mv_sum, 0.0)
            if rem_usd > 1e-6:
                cash_row = ("Cash", rem_usd / float(d) * 100.0, rem_usd)
        return out, True, weight_source, cash_row
    eq = 100.0 / len(parts)
    return [(sym, eq, 0.0) for sym in parts], False, "equal", None


def _format_session_ticker_weights(db: Any, tickers_csv: str, *, max_lines: int = 12) -> str:
    """
    Desglose ticker → % de nocional (qty * current_price en quant_core.portfolio_positions).
    Sin nocional: mismo % para todos los símbolos de la sesión.
    """
    breakdown, uses_nocional, weight_src, cash_row = _session_participation_breakdown(
        db, tickers_csv
    )
    if not breakdown:
        return ""
    notes: list[str] = []
    if uses_nocional:
        for sym, pct, noc in breakdown:
            notes.append(f"`{sym}` {pct:.1f}% (${noc:,.2f} noc.)")
        if cash_row is not None:
            _cs, _cp, _cn = cash_row
            notes.append(
                f"`{_cs}` {_cp:.1f}% (${_cn:,.2f} — resto cuenta vs total_value IBKR)"
            )
        if weight_src == "ibkr":
            head = "**Participación (% |mv| vs valor total cuenta IBKR, tickers de sesión):**\n"
        else:
            head = "**Participación (nocional qty×px):**\n"
    else:
        for sym, pct, _ in breakdown:
            notes.append(
                f"`{sym}` ~{pct:.1f}% (peso igual; sin nocional en portfolio_positions)"
            )
        head = "**Participación:**\n"
    body = "\n".join(f"- {ln}" for ln in notes[:max_lines])
    if len(notes) > max_lines:
        body += f"\n- … y {len(notes) - max_lines} más"
    return head + body


def _pie_slices_from_breakdown(
    breakdown: list[tuple[str, float, float]], *, top_n: int
) -> list[tuple[str, float, float]]:
    """Top ``top_n`` por % descendente + ``Otros`` (suma % y suma nocional del resto)."""
    if not breakdown or top_n < 1:
        return []
    ranked = sorted(breakdown, key=lambda t: (-t[1], t[0]))
    if len(ranked) <= top_n:
        return [(sym, pct, noc) for sym, pct, noc in ranked]
    head = ranked[:top_n]
    rest_pct = sum(p[1] for p in ranked[top_n:])
    rest_noc = sum(p[2] for p in ranked[top_n:])
    rows = [(sym, pct, noc) for sym, pct, noc in head]
    if rest_pct > 1e-4:
        rows.append(("Otros", rest_pct, max(rest_noc, 1e-12)))
    return rows


def _build_session_participation_pie_b64(db: Any, *, top_n: int = 5) -> str | None:
    """Torta top_n + rebanada Otros si aplica; misma lógica de pesos que el status."""
    try:
        raw = db.query(
            "SELECT status, tickers FROM quant_core.trading_sessions WHERE id = 'active' LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception:
        return None
    if not rows or not isinstance(rows[0], dict):
        return None
    if str(rows[0].get("status") or "").strip().upper() != "ACTIVE":
        return None
    tickers_csv = str(rows[0].get("tickers") or "").strip()
    breakdown, uses_nocional, weight_src, cash_row = _session_participation_breakdown(
        db, tickers_csv
    )
    pie_rows = _pie_slices_from_breakdown(breakdown, top_n=top_n)
    if not pie_rows:
        return None
    if cash_row is not None and cash_row[1] > 1e-4:
        pie_rows = [*pie_rows, cash_row]
    labels = [s for s, _, _ in pie_rows]
    label_pcts = [p for _, p, _ in pie_rows]
    sizes = [max(n, 1e-12) for _, _, n in pie_rows]
    try:
        from io import BytesIO

        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    fig, ax = plt.subplots(figsize=(7.8, 5.0), dpi=110)
    wedges, _t, autotexts = ax.pie(
        sizes,
        labels=None,
        autopct="%1.1f%%",
        textprops={"fontsize": 7},
        wedgeprops={"linewidth": 0.6, "edgecolor": "white"},
        pctdistance=0.72,
    )
    for i, t in enumerate(autotexts):
        t.set_fontsize(7)
        if i < len(label_pcts):
            t.set_text(f"{label_pcts[i]:.1f}%")
    ax.legend(
        wedges,
        labels,
        title="Ticker",
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        fontsize=7,
        title_fontsize=8,
        framealpha=0.92,
    )
    if uses_nocional:
        if weight_src == "ibkr":
            sub = (
                "% = |mv| / total_value cuenta IBKR (snapshot); tickers de sesión"
                + (
                    " · Cash = total − |mv| tickers sesión (efectivo y fuera de lista)"
                    if cash_row is not None
                    else ""
                )
            )
        else:
            sub = "Fuente: nocional |qty×px| en portfolio_positions"
    else:
        sub = (
            f"Sin filas útiles en portfolio_positions: "
            f"reparto igual 1/{len(breakdown)} entre tickers de sesión"
        )
    ax.set_title(f"Participación sesión · top {top_n}\n{sub}", fontsize=9)
    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=100, facecolor="white", edgecolor="none", bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _read_trading_session_status_summary(db: Any, *, chat_id: Any) -> str:
    try:
        raw_cols = db.query("PRAGMA table_info('quant_core.trading_sessions')")
        cols_rows = json.loads(raw_cols) if isinstance(raw_cols, str) else (raw_cols or [])
        known_cols = {
            str((it or {}).get("name") or "").strip().lower()
            for it in cols_rows
            if isinstance(it, dict)
        }
        has_session_goal = "session_goal" in known_cols
        has_anchor_equity = "anchor_equity" in known_cols
        has_peak_equity = "peak_equity" in known_cols
        select_goal = "session_goal" if has_session_goal else "NULL AS session_goal"
        select_anchor = "anchor_equity" if has_anchor_equity else "NULL AS anchor_equity"
        select_peak = "peak_equity" if has_peak_equity else "NULL AS peak_equity"
        raw = db.query(
            "SELECT mode, tickers, session_uid, status, "
            + select_goal
            + ", "
            + select_anchor
            + ", "
            + select_peak
            + " FROM quant_core.trading_sessions WHERE id = 'active' LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception as exc:
        return f"No se pudo leer trading_sessions: {exc}"
    if not rows or not isinstance(rows[0], dict):
        return "No hay sesión de trading registrada."
    row = rows[0]
    if str(row.get("status") or "").strip().upper() != "ACTIVE":
        return "No hay sesión activa."
    uid = str(row.get("session_uid") or "").strip() or "n/a"
    mode = str(row.get("mode") or "paper").strip().lower() or "paper"
    tickers = str(row.get("tickers") or "").strip() or "(vacío)"
    total = executed = cancelled = pending = 0
    try:
        raw2 = db.query(
            "SELECT status FROM quant_core.trade_signals WHERE session_uid = '"
            + uid.replace("'", "''")
            + "'"
        )
        rows2 = json.loads(raw2) if isinstance(raw2, str) else (raw2 or [])
    except Exception:
        rows2 = []
    if not rows2:
        try:
            raw3 = db.query(
                "SELECT status FROM finance_worker.trade_signals ORDER BY created_at DESC LIMIT 200"
            )
            rows2 = json.loads(raw3) if isinstance(raw3, str) else (raw3 or [])
        except Exception:
            rows2 = []
    for it in rows2:
        if not isinstance(it, dict):
            continue
        st = str(it.get("status") or "").strip().upper()
        total += 1
        if st == "EXECUTED":
            executed += 1
        elif st in ("CANCELLED", "DISCARDED"):
            cancelled += 1
        elif st in ("PENDING_HITL", "AWAITING_HITL", "PENDING"):
            pending += 1
    pnl_raw, pnl_reliable = _compute_trading_session_pnl_now_with_confidence(db, uid)
    old_last_s = str(get_chat_state(db, chat_id, "trading_session_last_pnl") or "").strip()
    hist_uid_s = str(get_chat_state(db, chat_id, _TRADING_SESSION_PNL_HIST_UID_KEY) or "").strip()
    _now = time.time()
    if hist_uid_s != uid:
        snap_points: list[tuple[float, float]] = []
    else:
        try:
            _raw_hist = get_chat_state(db, chat_id, _TRADING_SESSION_PNL_SNAPSHOTS_KEY) or "[]"
            snap_points = _pnl_snapshots_parse_stored(_raw_hist, now=_now)
        except Exception:
            snap_points = []
    snap_points = _pnl_snapshots_dedupe_epoch(snap_points)
    snapshots = _pnl_snapshots_to_floats(snap_points)
    _prev_for_carry: float | None = None
    if snapshots:
        try:
            _prev_for_carry = float(snapshots[-1])
        except (TypeError, ValueError):
            _prev_for_carry = None
    pnl_now = _trading_session_coalesce_unreliable_pnl_tick(
        pnl_raw, pnl_reliable, _prev_for_carry
    )
    prev_val: float | None = None
    if old_last_s:
        try:
            prev_val = float(old_last_s)
        except (TypeError, ValueError):
            prev_val = None
    pct_num: float | None = None
    _append_snap = True
    if snapshots:
        try:
            _last_s = float(snapshots[-1])
            _eps = max(1e-4, 1e-6 * max(1.0, abs(pnl_now), abs(_last_s)))
            if abs(float(pnl_now) - _last_s) <= _eps:
                _append_snap = False
        except (TypeError, ValueError):
            pass
    if _append_snap:
        snap_points.append((float(_now), float(pnl_now)))
    snap_points = _pnl_snapshots_dedupe_epoch(snap_points)
    snap_points = snap_points[-64:]
    snapshots = _pnl_snapshots_to_floats(snap_points)
    _display_pnl = float(snapshots[-1]) if snapshots else float(pnl_now)
    if prev_val is not None and abs(prev_val) > 1e-12:
        pct_num = (_display_pnl - prev_val) / abs(prev_val) * 100.0
    set_chat_state(db, chat_id, "trading_session_last_pnl", f"{_display_pnl:.6f}".rstrip("0").rstrip("."))
    set_chat_state(db, chat_id, "trading_session_prev_pnl", old_last_s)
    set_chat_state(
        db,
        chat_id,
        "trading_session_pct_change",
        f"{pct_num:.6f}".rstrip("0").rstrip(".") if pct_num is not None else "",
    )
    set_chat_state(db, chat_id, _TRADING_SESSION_PNL_SNAPSHOTS_KEY, _pnl_snapshots_serialize_v2(snap_points))
    set_chat_state(db, chat_id, _TRADING_SESSION_PNL_HIST_UID_KEY, uid)
    try:
        ds = int((get_chat_state(db, chat_id, _GOALS_DELTA_SECONDS_KEY) or "0").strip() or "0")
    except ValueError:
        ds = 0
    ds = max(0, ds)
    if ds > 0:
        _ih, cp, _lb = _goals_proactive_interval_countdown_parts(db, chat_id, ds)
        tick_line = f"Tick delta: cada ~{format_goals_delta_interval_human(ds)}{cp}"
    else:
        tick_line = "Tick delta: inactivo"
    try:
        _anchor_eq = float(row.get("anchor_equity") or 0.0)
    except (TypeError, ValueError):
        _anchor_eq = 0.0
    _tearsheet = _compute_tick_tearsheet_metrics_from_pnl(
        snapshots=snapshots,
        anchor_equity=_anchor_eq,
    )
    _pnl_curr_txt = f"{_display_pnl:.2f}"
    _pnl_prev_txt = f"{prev_val:.2f}" if prev_val is not None else "N/D"
    _pnl_pct_txt = f"{pct_num:+.2f}%" if pct_num is not None else "N/D"
    _sharpe_txt = (
        f"{_tearsheet['sharpe']:+.2f}" if _tearsheet.get("sharpe") is not None else "N/D"
    )
    _sortino_txt = (
        f"{_tearsheet['sortino']:+.2f}" if _tearsheet.get("sortino") is not None else "N/D"
    )
    _vol_txt = (
        f"{_tearsheet['volatility_pct']:.2f}%"
        if _tearsheet.get("volatility_pct") is not None
        else "N/D"
    )
    _mdd_txt = (
        f"{_tearsheet['max_drawdown_pct']:.2f}%"
        if _tearsheet.get("max_drawdown_pct") is not None
        else "N/D"
    )
    if _anchor_eq > 0:
        _cap_est = float(_anchor_eq) + float(_display_pnl)
        _cap_line = (
            f"Capital disponible (est., anchor_equity + PnL): "
            f"${_cap_est:,.2f} (anchor ${_anchor_eq:,.2f})\n"
        )
    else:
        _cap_line = "Capital disponible: N/D (sin anchor_equity en sesión)\n"
    _head_session = (
        f"Sesión activa: `{uid}`\n"
        f"Mode: `{mode}`\n"
        f"{_cap_line}"
    )
    _status_text = (
        f"{_head_session}"
        f"Señales generadas: {total}\n"
        f"- Ejecutadas: {executed}\n"
        f"- Canceladas: {cancelled}\n"
        f"- Pendientes HITL: {pending}\n"
        f"PnL actual: {_pnl_curr_txt}\n"
        f"PnL anterior: {_pnl_prev_txt}\n"
        f"Cambio vs anterior: {_pnl_pct_txt}\n"
        "📊 Tearsheet (tick-based):\n"
        f"- ⚡ Sharpe: {_sharpe_txt}\n"
        f"- 🛡️ Sortino: {_sortino_txt}\n"
        f"- 🌪️ Volatilidad: {_vol_txt}\n"
        f"- 📉 Max Drawdown: {_mdd_txt}\n"
        f"{tick_line}"
    )
    return _status_text


def _quant_core_trade_signals_column_names(db: Any) -> set[str]:
    try:
        raw = db.query("PRAGMA table_info('quant_core.trade_signals')")
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        return {
            str((it or {}).get("name") or "").strip().lower()
            for it in rows
            if isinstance(it, dict)
        }
    except Exception:
        return set()


def _trading_session_coalesce_unreliable_pnl_tick(
    raw: float, reliable: bool, previous_last: float | None
) -> float:
    """
    Si ninguna fuente pudo leer PnL con certeza (p. ej. IB Gateway abajo y todo devuelve 0),
    reutilizar el último tick en lugar de 0, para no distorsionar la serie del gráfico.
    """
    if reliable:
        return float(raw)
    if previous_last is not None:
        return float(previous_last)
    return float(raw)


def _compute_trading_session_pnl_now_with_confidence(
    db: Any, session_uid: str
) -> tuple[float, bool]:
    """
    PnL agregado: trade_signals (sum no nula), portfolio_positions, luego IBKR.
    Retorna (valor, fiable). fiable == False si se llega a 0 sin que ninguna fuente
    haya dado un número (IBKR con None, sin snapshot usable).
    Un (0, True) indica 0 con respuesta explícita (p. ej. IB devolvió 0.0 y portfolio vacío).
    """
    uid = (session_uid or "").strip()
    if not uid or uid == "n/a":
        return (0.0, True)
    esc = uid.replace("'", "''")
    cols = _quant_core_trade_signals_column_names(db)
    if "unrealized_pnl" in cols:
        try:
            raw = db.query(
                f"SELECT COALESCE(SUM(unrealized_pnl), 0) AS s "
                f"FROM quant_core.trade_signals WHERE session_uid = '{esc}'"
            )
            rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
            if rows and isinstance(rows[0], dict):
                v = float(rows[0].get("s") or 0.0)
                if abs(v) > 1e-12:
                    return (v, True)
        except Exception:
            pass
    try:
        raw = db.query(
            "SELECT COALESCE(SUM(unrealized_pnl), 0) AS s FROM quant_core.portfolio_positions"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if rows and isinstance(rows[0], dict):
            v = float(rows[0].get("s") or 0.0)
            if abs(v) > 1e-12:
                return (v, True)
    except Exception:
        pass
    try:
        from duckclaw.forge.skills.ibkr_bridge import fetch_ibkr_unrealized_pnl_total_numeric

        ibkr_u, _err = fetch_ibkr_unrealized_pnl_total_numeric()
        if ibkr_u is not None:
            return (float(ibkr_u), True)
    except Exception:
        pass
    return (0.0, False)


def _compute_trading_session_pnl_now(db: Any, session_uid: str) -> float:
    v, _ = _compute_trading_session_pnl_now_with_confidence(db, session_uid)
    return v


def _trading_session_snapshots_for_tearsheet_label(
    db: Any, chat_id: Any, *, session_uid: str
) -> list[float]:
    """
    Misma fuente de serie que el bloque "Tearsheet (tick-based)" de
    _read_trading_session_status_summary: snapshots guardados en agent_config
    (PnL agregado por tick), alineados a session_uid.
    Debe usarse en la anotación del PNG para no divergir del texto.
    """
    uid = (session_uid or "").strip()
    if not uid or uid == "n/a":
        return []
    hist_uid_s = str(get_chat_state(db, chat_id, _TRADING_SESSION_PNL_HIST_UID_KEY) or "").strip()
    if hist_uid_s != uid:
        return []
    try:
        _raw = get_chat_state(db, chat_id, _TRADING_SESSION_PNL_SNAPSHOTS_KEY) or "[]"
        pts = _pnl_snapshots_parse_stored(_raw, now=time.time())
    except Exception:
        return []
    if not pts:
        return []
    try:
        return _pnl_snapshots_to_floats(_pnl_snapshots_dedupe_epoch(pts))
    except (TypeError, ValueError):
        return []


def _compute_tick_tearsheet_metrics_from_pnl(
    *,
    snapshots: list[float],
    anchor_equity: float,
) -> dict[str, float | None]:
    """
    Métricas estilo tearsheet a partir de snapshots de PnL.
    Son métricas "tick-based" (sin calendario fijo) y se anualizan con 252 pasos.
    """
    out: dict[str, float | None] = {
        "sharpe": None,
        "sortino": None,
        "volatility_pct": None,
        "max_drawdown_pct": None,
    }
    if anchor_equity <= 0:
        return out
    if not isinstance(snapshots, list) or len(snapshots) < 3:
        return out
    try:
        pnl_series = [float(x) for x in snapshots]
    except (TypeError, ValueError):
        return out
    equity = [anchor_equity + p for p in pnl_series]
    if len(equity) < 3:
        return out
    rets: list[float] = []
    for i in range(1, len(equity)):
        prev = float(equity[i - 1])
        curr = float(equity[i])
        if prev <= 0:
            continue
        rets.append((curr / prev) - 1.0)
    if len(rets) < 2:
        return out
    try:
        mean_r = statistics.fmean(rets)
        std_r = statistics.pstdev(rets)
    except Exception:
        return out
    if std_r > 1e-12:
        out["sharpe"] = (mean_r / std_r) * math.sqrt(252.0)
        out["volatility_pct"] = std_r * math.sqrt(252.0) * 100.0
    downside = [r for r in rets if r < 0]
    if downside:
        try:
            down_std = statistics.pstdev(downside)
            if down_std > 1e-12:
                out["sortino"] = (mean_r / down_std) * math.sqrt(252.0)
        except Exception:
            pass
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (v / peak) - 1.0
            if dd < max_dd:
                max_dd = dd
    out["max_drawdown_pct"] = max_dd * 100.0
    return out


def _build_trading_session_pnl_chart_b64(db: Any, *, chat_id: Any) -> str | None:
    """Serie PnL acumulado (señales EXECUTED) → PNG base64, o None."""
    try:
        raw = db.query(
            "SELECT mode, session_uid, status, anchor_equity FROM quant_core.trading_sessions WHERE id = 'active' LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception:
        return None
    if not rows or not isinstance(rows[0], dict):
        return None
    row = rows[0]
    if str(row.get("status") or "").strip().upper() != "ACTIVE":
        return None
    mode = str(row.get("mode") or "paper").strip().lower() or "paper"
    uid = str(row.get("session_uid") or "").strip()
    if not uid or uid == "n/a":
        return None
    try:
        _anchor_eq = float(row.get("anchor_equity") or 0.0)
    except (TypeError, ValueError):
        _anchor_eq = 0.0
    esc = uid.replace("'", "''")
    executed_pnls: list[float] = []
    pnl_total = 0.0
    _sig_cols = _quant_core_trade_signals_column_names(db)
    has_unrealized = "unrealized_pnl" in _sig_cols
    if has_unrealized:
        try:
            raw_ex = db.query(
                "SELECT COALESCE(unrealized_pnl, 0) AS pnl FROM quant_core.trade_signals "
                f"WHERE session_uid = '{esc}' AND UPPER(TRIM(COALESCE(status,''))) = 'EXECUTED' "
                "ORDER BY COALESCE(ts, updated_at) ASC"
            )
            r_ex = json.loads(raw_ex) if isinstance(raw_ex, str) else (raw_ex or [])
            for it in r_ex or []:
                if isinstance(it, dict):
                    try:
                        executed_pnls.append(float(it.get("pnl") or 0.0))
                    except (TypeError, ValueError):
                        executed_pnls.append(0.0)
            raw_all = db.query(
                f"SELECT COALESCE(unrealized_pnl, 0) AS pnl FROM quant_core.trade_signals "
                f"WHERE session_uid = '{esc}'"
            )
            r_all = json.loads(raw_all) if isinstance(raw_all, str) else (raw_all or [])
            for it in r_all or []:
                if isinstance(it, dict):
                    try:
                        pnl_total += float(it.get("pnl") or 0.0)
                    except (TypeError, ValueError):
                        pass
        except Exception:
            return None
    # Misma serie "tick" que el tearsheet: snapshots con epoch (v2) o v1 parseado.
    _epoch_pts_chart = _snapshot_epoch_points_for_session(db, chat_id, uid)
    _snap_for_line: list[float] = _pnl_snapshots_to_floats(_epoch_pts_chart)
    pnl_line_source = "executed"
    cum: list[float] = [0.0]
    if _snap_for_line:
        pnl_line_source = "snapshots"
        for it in _snap_for_line:
            try:
                cum.append(float(it))
            except (TypeError, ValueError):
                cum.append(cum[-1])
    elif executed_pnls:
        for p in executed_pnls:
            cum.append(cum[-1] + p)
    else:
        pnl_line_source = "fallback"
        hist_uid_g = str(get_chat_state(db, chat_id, _TRADING_SESSION_PNL_HIST_UID_KEY) or "").strip()
        if hist_uid_g == uid.strip():
            try:
                snap_raw = get_chat_state(db, chat_id, _TRADING_SESSION_PNL_SNAPSHOTS_KEY) or "[]"
                pts_fb = _pnl_snapshots_parse_stored(snap_raw, now=time.time())
            except Exception:
                pts_fb = []
            snaps_fb = _pnl_snapshots_to_floats(_pnl_snapshots_dedupe_epoch(pts_fb))
            if snaps_fb:
                cum = [0.0]
                for it in snaps_fb:
                    try:
                        cum.append(float(it))
                    except (TypeError, ValueError):
                        cum.append(cum[-1])
            else:
                pnl_total = _compute_trading_session_pnl_now(db, uid)
                cum = [0.0, pnl_total]
        else:
            pnl_total = _compute_trading_session_pnl_now(db, uid)
            cum = [0.0, pnl_total]
    try:
        from datetime import datetime, timezone
        from io import BytesIO
        from zoneinfo import ZoneInfo

        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
    except Exception:
        return None
    _pnl_chart_tz = ZoneInfo(COT_TZ_NAME)
    _tc_anchor = time.time()
    n = len(cum)
    x_dt: list[datetime]
    if pnl_line_source == "snapshots" and _epoch_pts_chart and len(cum) == len(_epoch_pts_chart) + 1:
        first_ep = float(_epoch_pts_chart[0][0])
        x_dt = [
            datetime.fromtimestamp(first_ep - _PNL_SNAPSHOT_SYNTH_STEP_SEC, tz=timezone.utc)
        ]
        x_dt.extend(
            datetime.fromtimestamp(float(ep), tz=timezone.utc) for ep, _ in _epoch_pts_chart
        )
    else:
        x_dt = [
            datetime.fromtimestamp(
                _tc_anchor - _PNL_SNAPSHOT_SYNTH_STEP_SEC * (n - 1 - i), tz=timezone.utc
            )
            for i in range(n)
        ]
    if len(x_dt) != n:
        x_dt = [
            datetime.fromtimestamp(
                _tc_anchor - _PNL_SNAPSHOT_SYNTH_STEP_SEC * (n - 1 - i), tz=timezone.utc
            )
            for i in range(n)
        ]
    x = mdates.date2num(x_dt)
    # Tearsheet: misma lista que la curva cuando hay snapshots; si no, derivada de `cum`.
    _snap_for_metrics = _snap_for_line or _trading_session_snapshots_for_tearsheet_label(
        db, chat_id, session_uid=uid
    )
    _tearsheet = _compute_tick_tearsheet_metrics_from_pnl(
        snapshots=_snap_for_metrics
        if _snap_for_metrics
        else [float(v) for v in cum],
        anchor_equity=_anchor_eq,
    )
    _sharpe_txt = (
        f"{_tearsheet['sharpe']:+.2f}" if _tearsheet.get("sharpe") is not None else "N/D"
    )
    _sortino_txt = (
        f"{_tearsheet['sortino']:+.2f}" if _tearsheet.get("sortino") is not None else "N/D"
    )
    _vol_txt = (
        f"{_tearsheet['volatility_pct']:.2f}%"
        if _tearsheet.get("volatility_pct") is not None
        else "N/D"
    )
    _mdd_txt = (
        f"{_tearsheet['max_drawdown_pct']:.2f}%"
        if _tearsheet.get("max_drawdown_pct") is not None
        else "N/D"
    )
    equity_curve = [_anchor_eq + float(v) for v in cum] if _anchor_eq > 0 else []
    drawdowns: list[float] = []
    if equity_curve:
        peak = equity_curve[0]
        for v in equity_curve:
            if v > peak:
                peak = v
            drawdowns.append(((v / peak) - 1.0) * 100.0 if peak > 0 else 0.0)
    else:
        drawdowns = [0.0 for _ in cum]
    fig, (ax, ax_dd) = plt.subplots(
        2,
        1,
        figsize=(7.2, 4.8),
        dpi=110,
        gridspec_kw={"height_ratios": [3.0, 1.2]},
    )
    ax.fill_between(x, cum, 0.0, color="#93c5fd", alpha=0.35, linewidth=0)
    ax.plot(x, cum, color="#2563eb", linewidth=2, marker="o", markersize=2.8, label="PnL acumulado")
    ax.axhline(0, color="#94a3b8", linewidth=0.8)
    if cum:
        n_c = len(cum)
        i_max = max(range(n_c), key=lambda i: cum[i])
        i_min = min(range(n_c), key=lambda i: cum[i])
        _ann_bbox = {
            "boxstyle": "round,pad=0.25",
            "facecolor": "white",
            "alpha": 0.82,
            "edgecolor": "#e5e7eb",
        }
        _arr = {"arrowstyle": "-", "color": "#64748b", "lw": 0.55}
        i_curr = n_c - 1
        v_curr = float(cum[i_curr])
        v_max = float(cum[i_max])
        v_min = float(cum[i_min])
        eps = max(1e-4, 1e-9 * max(1.0, abs(v_max), abs(v_min), abs(v_curr)))
        flat = abs(v_max - v_min) <= eps
        if flat:
            ax.annotate(
                f"Actual ${v_curr:,.0f}",
                xy=(x[i_curr], v_curr),
                xytext=(10, 12),
                textcoords="offset points",
                fontsize=7,
                color="#111827",
                bbox=_ann_bbox,
                arrowprops=_arr,
            )
        else:
            if v_min + eps < v_curr:
                ax.annotate(
                    f"Mín ${v_min:,.0f}",
                    xy=(x[i_min], cum[i_min]),
                    xytext=(8, -16),
                    textcoords="offset points",
                    fontsize=7,
                    color="#111827",
                    bbox=_ann_bbox,
                    arrowprops=_arr,
                )
            shown_historical_max = v_max > v_curr + eps
            if shown_historical_max:
                ax.annotate(
                    f"Máx ${v_max:,.0f}",
                    xy=(x[i_max], cum[i_max]),
                    xytext=(8, 10),
                    textcoords="offset points",
                    fontsize=7,
                    color="#111827",
                    bbox=_ann_bbox,
                    arrowprops=_arr,
                )
            ax.annotate(
                f"Actual ${v_curr:,.0f}",
                xy=(x[i_curr], cum[i_curr]),
                xytext=(10, -16 if shown_historical_max else 12),
                textcoords="offset points",
                fontsize=7,
                color="#111827",
                bbox=_ann_bbox,
                arrowprops=_arr,
            )
    ax.set_ylabel("PnL ($)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M", tz=_pnl_chart_tz))
    ax.set_title(
        f"Trading Session Tearsheet · {mode} · {uid[:8]}… (Bogotá, COT)",
        fontsize=10,
    )
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
    ax.text(
        0.99,
        0.02,
        f"Sharpe: {_sharpe_txt} | Sortino: {_sortino_txt} | Vol: {_vol_txt} | MaxDD: {_mdd_txt}",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=8,
        color="#111827",
        bbox={"facecolor": "white", "alpha": 0.78, "edgecolor": "#d1d5db", "pad": 2.5},
    )
    ax_dd.plot(x, drawdowns, color="#dc2626", linewidth=1.6)
    ax_dd.fill_between(x, drawdowns, [0.0 for _ in drawdowns], color="#fecaca", alpha=0.6)
    ax_dd.axhline(0, color="#9ca3af", linewidth=0.8)
    ax_dd.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M", tz=_pnl_chart_tz))
    ax_dd.set_xlabel("Tiempo (Bogotá, COT)")
    ax_dd.set_ylabel("DD %")
    ax_dd.grid(True, alpha=0.25)
    fig.autofmt_xdate(bottom=0.22, rotation=18)
    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=100, facecolor="white", edgecolor="none", bbox_inches="tight")
    plt.close(fig)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return b64


def execute_trading_session(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    tenant_id: Any = None,
    vault_user_id: Any = None,
) -> str:
    """/trading-session --mode paper|live [--tickers A,B] [--objective ...] [--confirm] [--status] [--stop]."""
    _ = vault_user_id
    parsed, err = _parse_trading_session_cli(args)
    if err or parsed is None:
        return (
            f"Error: {err}\n\n"
            "Uso: `/trading-session --mode paper|live [--tickers AAPL,NVDA] [--confirm]`\n"
            "Extras: `--objective maximize_pnl|rebalance_hrp|overnight_gap_squeeze` · `--max-drawdown 2` · "
            "`--position-size 5` · `--signal GAS` · `--status` · `--stop`\n"
            "Modo **live** exige añadir **--confirm** en el mismo mensaje (riesgo de capital)."
        )
    tid = str(tenant_id or "default").strip() or "default"
    if parsed.status:
        out = _read_trading_session_status_summary(db, chat_id=chat_id)
        try:
            b64c = _build_trading_session_pnl_chart_b64(db, chat_id=chat_id)
        except Exception:
            b64c = None
        if b64c:
            register_fly_outbound_chart_b64(chat_id, b64c)
        try:
            pie_b64 = _build_session_participation_pie_b64(db)
        except Exception:
            pie_b64 = None
        if pie_b64:
            register_fly_outbound_chart_b64(chat_id, pie_b64)
        return out
    if parsed.stop:
        ok_close, detail_close = _close_active_trading_session(
            db,
            chat_id=chat_id,
            tenant_id=tid,
        )
        if not ok_close:
            return f"No se pudo cerrar la sesión: {detail_close}"
        return f"Sesión cerrada (status=CLOSED). Scheduler limpiado. {detail_close}"
    mode = str(parsed.mode or "").strip().lower()
    if mode == "live" and not parsed.confirm:
        return (
            "RIESGO DE CAPITAL: modo `live` enruta órdenes al broker real.\n\n"
            "Si aceptas el riesgo, reenvía el comando con **--confirm**:\n"
            "`/trading-session --mode live --tickers NVDA --confirm`"
        )
    session_uid = str(uuid.uuid4())
    goal = _session_goal_from_cli(parsed)
    goal_json = goal.model_dump_json(ensure_ascii=False)
    upsert = """
INSERT INTO quant_core.trading_sessions (id, mode, tickers, session_uid, session_goal, status)
VALUES (?, ?, ?, ?, CAST(? AS JSON), 'ACTIVE')
ON CONFLICT (id) DO UPDATE SET
  mode = excluded.mode,
  tickers = excluded.tickers,
  session_uid = excluded.session_uid,
  session_goal = excluded.session_goal,
  status = 'ACTIVE',
  updated_at = now()
"""
    reset_eq = (
        "UPDATE quant_core.trading_sessions SET anchor_equity = NULL, peak_equity = NULL WHERE id = ?",
        [_TRADING_SESSION_ROW_ID],
    )
    ok, detail = _vault_apply_sql_statements(
        db,
        [
            (_TRADING_SESSIONS_DDL, None),
            (
                upsert,
                [_TRADING_SESSION_ROW_ID, mode, parsed.tickers_csv or "", session_uid, goal_json],
            ),
            reset_eq,
        ],
        tenant_id=tid,
    )
    if not ok:
        return f"No se pudo guardar la sesión: {detail}"
    try:
        from duckclaw.forge.skills.ibkr_bridge import fetch_ibkr_total_equity_numeric

        eq, _eq_err = fetch_ibkr_total_equity_numeric()
        if eq is not None:
            _vault_apply_sql_statements(
                db,
                [
                    (
                        "UPDATE quant_core.trading_sessions SET anchor_equity = ?, peak_equity = ? WHERE id = ?",
                        [float(eq), float(eq), _TRADING_SESSION_ROW_ID],
                    )
                ],
                tenant_id=tid,
            )
    except Exception:
        pass
    enabled, secs = _ensure_trading_session_goals_delta(
        db,
        chat_id=chat_id,
        tenant_id=tid,
        session_uid=session_uid,
    )
    delta_msg = (
        f"Ticker /crons auto-activado cada ~{format_goals_delta_interval_human(secs)} (trigger=trading_session)."
        if enabled
        else f"Ticker /crons ya activo cada ~{format_goals_delta_interval_human(secs)} (se conserva configuración)."
    )
    tick_note = f"\nTickers: `{parsed.tickers_csv}`" if parsed.tickers_csv else ""
    sid = _TRADING_SESSION_ROW_ID
    try:
        set_chat_state(db, chat_id, _TRADING_SESSION_PNL_SNAPSHOTS_KEY, "[]")
        set_chat_state(db, chat_id, _TRADING_SESSION_PNL_HIST_UID_KEY, str(session_uid))
        set_chat_state(db, chat_id, "trading_session_last_pnl", "")
        set_chat_state(db, chat_id, "trading_session_prev_pnl", "")
        set_chat_state(db, chat_id, "trading_session_pct_change", "")
    except Exception:
        pass
    return (
        f"**Id sesión:** `{sid}`\n"
        f"**Unique ID sesión:** `{session_uid}`\n"
        f"Sesión de trading **{mode.upper()}** registrada en `quant_core.trading_sessions` (status=ACTIVE)."
        f"{tick_note}\n"
        f"session_goal: `{goal_json}`\n"
        f"{delta_msg}\n"
        "El reactor Quant debe leer tickers y `status=ACTIVE` antes de proponer señales."
    )


def execute_quant_cycle(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    tenant_id: Any = None,
    vault_user_id: Any = None,
) -> str:
    """/quant_cycle: ciclo determinista Quant (fetch+portfolio+evaluate+signal) en un solo comando."""
    _ = vault_user_id
    parsed, err = _parse_quant_cycle_cli(args)
    if err or parsed is None:
        return (
            f"Error: {err}\n\n"
            "Uso: `/quant_cycle [--tickers AAPL,NVDA] [--timeframe 1h] [--lookback_days 20]`\n"
            "Extras: `--objective maximize_pnl|rebalance_hrp|overnight_gap_squeeze` · `--signal GAS|LIQUID|SOLID|PLASMA` · "
            "`--weight 5` · `--execute auto|off`\n"
            "Si no pasas `--tickers`, se usan los de `quant_core.trading_sessions` (id=active) o `SPY` por defecto."
        )
    from duckclaw.forge.skills.ibkr_bridge import _get_ibkr_portfolio_impl
    from duckclaw.forge.skills.quant_market_bridge import _fetch_ib_gateway_ohlcv_impl
    from duckclaw.forge.skills.quant_tool_context import (
        bind_quant_market_evidence_chat,
        note_quant_market_evidence_ticker,
        reset_quant_market_evidence,
        set_quant_tool_chat_id,
        set_quant_tool_db_path,
        set_quant_tool_tenant_id,
        set_quant_tool_user_id,
    )
    from duckclaw.forge.skills.quant_trader_bridge import (
        _evaluate_cfd_state_impl,
        _run_quant_signal_cycle_impl,
    )

    tid = str(tenant_id or "default").strip() or "default"
    cid = str(chat_id).strip() or "default"
    uid = cid
    set_quant_tool_chat_id(cid)
    set_quant_tool_tenant_id(tid)
    set_quant_tool_user_id(uid)
    set_quant_tool_db_path(str(getattr(db, "_path", "") or ""))
    bind_quant_market_evidence_chat(cid)
    reset_quant_market_evidence()

    session_uid = ""
    session_tickers: list[str] = []
    try:
        raw = db.query(
            "SELECT session_uid, tickers FROM quant_core.trading_sessions "
            "WHERE id = 'active' AND status = 'ACTIVE' LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if rows and isinstance(rows[0], dict):
            session_uid = str(rows[0].get("session_uid") or "").strip()
            session_tickers = [
                x.strip().upper()
                for x in str(rows[0].get("tickers") or "").split(",")
                if x.strip()
            ]
    except Exception:
        pass
    tickers = [x.strip().upper() for x in (parsed.tickers_csv or "").split(",") if x.strip()]
    if not tickers:
        tickers = list(session_tickers)
    if not tickers:
        tickers = ["SPY"]

    fetch_stage: list[dict[str, Any]] = []
    for tkr in tickers:
        raw_fetch = _fetch_ib_gateway_ohlcv_impl(
            db,
            ticker=tkr,
            timeframe=parsed.timeframe,
            lookback_days=int(parsed.lookback_days),
        )
        try:
            obj = json.loads(raw_fetch) if isinstance(raw_fetch, str) else raw_fetch
        except Exception:
            obj = {"error": "INVALID_FETCH_RESPONSE", "raw": str(raw_fetch)[:220]}
        if isinstance(obj, dict) and obj.get("status") == "ok":
            note_quant_market_evidence_ticker(tkr)
        fetch_stage.append({"ticker": tkr, "result": obj})

    portfolio_raw = _get_ibkr_portfolio_impl()
    eval_raw = _evaluate_cfd_state_impl(
        db,
        session_uid=session_uid,
        tickers=tickers,
        signal_threshold=parsed.signal_threshold,
    )
    try:
        eval_obj = json.loads(eval_raw) if isinstance(eval_raw, str) else eval_raw
    except Exception:
        eval_obj = {"error": "INVALID_EVAL_RESPONSE", "raw": str(eval_raw)[:300]}

    should_propose = False
    target_ticker = tickers[0]
    rank_probe: list[dict[str, Any]] = []
    if isinstance(eval_obj, dict):
        results = eval_obj.get("results")
        if isinstance(results, list):
            for r in results:
                if not isinstance(r, dict):
                    continue
                rank_probe.append(
                    {
                        "ticker": str(r.get("ticker") or ""),
                        "ok": bool(r.get("ok")),
                        "has_pending_hitl": bool(r.get("has_pending_hitl")),
                        "phase_rank": r.get("phase_rank"),
                        "threshold_rank": r.get("threshold_rank"),
                    }
                )
                if bool(r.get("ok")) and not bool(r.get("has_pending_hitl")):
                    try:
                        pr = int(r.get("phase_rank") or 0)
                        tr = int(r.get("threshold_rank") or 0)
                    except Exception:
                        pr, tr = 0, 99
                    if pr >= tr:
                        should_propose = True
                        target_ticker = str(r.get("ticker") or target_ticker).strip().upper()
                        break

    signal_obj: dict[str, Any] = {
        "status": "skipped",
        "reason": "ALIGNED_OR_INSUFFICIENT_SIGNAL_CONTEXT",
        "message": "No se propuso señal en este ciclo porque la evaluación no exige acción.",
    }
    if should_propose:
        raw_signal = _run_quant_signal_cycle_impl(
            db,
            mandate_id="",
            ticker=target_ticker,
            weight=float(parsed.weight_pct),
            rationale=(
                f"/quant_cycle objective={parsed.objective} timeframe={parsed.timeframe} "
                f"lookback_days={int(parsed.lookback_days)} execute={parsed.execute}"
            ),
            signal_type="ENTRY",
            execute_now=False,
        )
        try:
            parsed_signal = json.loads(raw_signal) if isinstance(raw_signal, str) else raw_signal
            signal_obj = parsed_signal if isinstance(parsed_signal, dict) else {"raw": str(raw_signal)[:800]}
        except Exception:
            signal_obj = {"raw": str(raw_signal)[:800]}

    fetch_errors = [x for x in fetch_stage if isinstance(x.get("result"), dict) and x["result"].get("error")]
    portfolio_error = ""
    if str(portfolio_raw or "").strip().lower().startswith("error"):
        portfolio_error = str(portfolio_raw or "")
    eval_error = str(eval_obj.get("error") or "") if isinstance(eval_obj, dict) else ""
    signal_error = str(signal_obj.get("error") or "") if isinstance(signal_obj, dict) else ""

    policy_decision = "HITL_REQUIRED"
    if isinstance(signal_obj, dict) and bool(signal_obj.get("auto_executed")):
        policy_decision = "AUTO_EXECUTED"
    elif isinstance(signal_obj, dict) and isinstance(signal_obj.get("auto_execute"), dict):
        auto_exec = signal_obj.get("auto_execute") or {}
        if auto_exec.get("skipped"):
            policy_decision = f"AUTO_EXECUTION_SKIPPED:{str(auto_exec.get('reason') or 'UNKNOWN')}"
        elif auto_exec.get("error"):
            policy_decision = f"AUTO_EXECUTION_ERROR:{str(auto_exec.get('error') or 'UNKNOWN')}"
    elif parsed.execute == "off":
        policy_decision = "PROPOSED_WITH_HITL_ONLY"

    out_obj: dict[str, Any] = {
        "status": "ok",
        "command": "quant_cycle",
        "objective": parsed.objective,
        "policy_decision": policy_decision,
        "session_uid": session_uid,
        "params": {
            "tickers": tickers,
            "timeframe": parsed.timeframe,
            "lookback_days": int(parsed.lookback_days),
            "signal_threshold": parsed.signal_threshold,
            "weight_pct": float(parsed.weight_pct),
            "execute": parsed.execute,
        },
        "stages": {
            "fetch": fetch_stage,
            "portfolio": {"summary_text": str(portfolio_raw or "")[:1200]},
            "evaluation": eval_obj,
            "signal": signal_obj,
        },
        "errors_by_stage": {
            "fetch": [x.get("result", {}).get("error") for x in fetch_errors],
            "portfolio": portfolio_error,
            "evaluation": eval_error,
            "signal": signal_error,
        },
    }
    signal_id = str(signal_obj.get("signal_id") or "").strip() if isinstance(signal_obj, dict) else ""
    signal_status = str(signal_obj.get("status") or "").strip() if isinstance(signal_obj, dict) else ""
    human_msg = [
        "Ciclo Quant determinista ejecutado.",
        f"- Tickers: {', '.join(tickers)}",
        f"- Evaluación: {str(eval_obj.get('outcome') if isinstance(eval_obj, dict) else 'N/A')}",
        f"- Señal: {signal_status or 'skipped'}",
    ]
    if signal_id:
        human_msg.append(f"- signal_id: `{signal_id}`")
    if signal_id and signal_status.upper() in ("PROPOSED", "PENDING_HITL", "PENDING"):
        human_msg.append(f"- HITL: `/execute-signal {signal_id}`")
    return "\n".join(human_msg) + "\n\n```json\n" + json.dumps(out_obj, ensure_ascii=False, indent=2) + "\n```"


def _looks_like_hallucinated_placeholder_uuid(sid: str) -> bool:
    """
    Detecta UUID de baja entropía o patrones típicos inventados por el LLM cuando no hubo tool call.
    No sustituye el ledger: solo mejora el mensaje de error (evidencia: gateway tools usadas=ninguna + e0e5e5e5...).
    """
    t = (sid or "").strip().lower()
    if not t:
        return False
    if "e0e5e5e5" in t or "deadbeef" in t:
        return True
    try:
        u = uuid.UUID(t)
    except ValueError:
        return False
    h32 = u.hex
    if h32 == "0" * 32:
        return True
    # uuid4 real suele tener muchos símbolos hex distintos; placeholders repetitivos tienen pocos
    if len(set(h32)) <= 4:
        return True
    return False


def _execute_signal_verify_ledger(db: Any, sid: str) -> tuple[bool, str]:
    """Comprueba que el UUID exista y sea ejecutable (Quant: finance_worker; Finanz: quant_core)."""
    if db is None:
        return True, ""
    q_sid = sid.replace("'", "''")
    try:
        raw = db.query(
            f"SELECT status FROM finance_worker.trade_signals WHERE signal_id = '{q_sid}' LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception:
        rows = []
    if rows and isinstance(rows[0], dict):
        st = str(rows[0].get("status") or "").upper()
        if st in ("EXECUTED", "FAILED", "DISCARDED", "CANCELLED"):
            return False, f"Señal ya cerrada ({st})."
        if st not in ("AWAITING_HITL", "PENDING", "PENDING_HITL"):
            return False, f"Estado no ejecutable: {st}"
        return True, ""
    try:
        raw2 = db.query(
            f"SELECT signal_id FROM quant_core.trade_signals WHERE signal_id = '{q_sid}' LIMIT 1"
        )
        rows2 = json.loads(raw2) if isinstance(raw2, str) else (raw2 or [])
    except Exception:
        rows2 = []
    if rows2:
        return True, ""
    return False, "UUID no encontrado en finance_worker.trade_signals ni quant_core.trade_signals."


def execute_quant_execute_signal(db: Any, chat_id: Any, args: str) -> str:
    """/execute-signal <uuid>: HITL para Quant Trader (execute_approved_signal)."""
    sid = (args or "").strip().lower().split()[0] if (args or "").strip() else ""
    if not re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        sid,
    ):
        return "Uso: /execute-signal <signal_id_UUID>"
    if _looks_like_hallucinated_placeholder_uuid(sid):
        return (
            "No: ese UUID parece inventado por el modelo (no viene de `propose_trade_signal`). "
            "Pide al asistente que en el **mismo turno** ejecute OHLCV + `propose_trade_signal` "
            "y uses solo el `signal_id` del JSON de la herramienta."
        )
    try:
        from duckclaw.graphs.graph_server import get_db as _get_db

        _db = _get_db()
        tid = str(get_chat_state(_db, chat_id, "tenant_id") or "default").strip() or "default"
        rid = str(get_chat_state(_db, chat_id, "last_requester_id") or "").strip()
        if _is_wr_tenant(tid):
            clearance = _wr_member_clearance(_db, tenant_id=tid, user_id=rid)
            if not (_is_gateway_owner_user(rid) or clearance == "admin"):
                return "❌ Acceso denegado: /execute-signal en War Room requiere clearance admin."
    except Exception:
        pass
    ok_ledger, ledger_msg = _execute_signal_verify_ledger(db, sid)
    if not ok_ledger:
        return f"No: {ledger_msg}"
    try:
        from duckclaw.forge.skills.quant_hitl import grant_execute_order

        grant_execute_order(str(chat_id).strip(), sid)
    except Exception as e:
        return f"No se pudo registrar la confirmación: {e}"
    return (
        f"Confirmación registrada para la señal {sid}. "
        "Pide al asistente que ejecute **execute_approved_signal** "
        f"(Quant Trader) con signal_id={sid} en esta sesión."
    )


def execute_quant_profile(db: Any, chat_id: Any, args: str, *, tenant_id: Any = None) -> str:
    """`/profile`: perfil inferido desde VSS (Quantum vault)."""
    del args
    from duckclaw.forge.atoms.investor_profile_vss import format_profile_summary, get_investor_profile
    from duckclaw.forge.skills.quant_tool_context import set_quant_tool_db_path

    raw_path = str(getattr(db, "_path", "") or "").strip()
    if raw_path:
        set_quant_tool_db_path(raw_path)
    tid = str(tenant_id or get_chat_state(db, chat_id, "tenant_id") or "default").strip() or "default"
    try:
        profile = get_investor_profile(db, tid)
    except Exception as exc:
        return f"No se pudo leer el perfil: {exc}"
    return format_profile_summary(profile)


def execute_quant_macro_update(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    requester_id: Any = None,
    tenant_id: Any = None,
) -> str:
    """`/macro --update …`: sólo admin/owner — escribe macro_manual_state vía Singleton Writer."""
    from duckclaw.forge.atoms.macro_fly_parse import parse_macro_update_cli

    tid = str(tenant_id or get_chat_state(db, chat_id, "tenant_id") or "default").strip() or "default"
    rid = str(requester_id or get_chat_state(db, chat_id, "last_requester_id") or "").strip()
    if not (_is_gateway_owner_user(rid) or _is_team_admin(db, tenant_id=tid, requester_id=rid)):
        return "❌ Acceso denegado: `/macro --update` requiere admin del tenant u owner."

    parsed, err = parse_macro_update_cli(args)
    if not parsed:
        return err or "Parse inválido."

    rg = str(parsed["regime"] or "").strip().upper()
    stmts: list[tuple[str, Optional[list[Any]]]] = [
        ("DELETE FROM quant_core.macro_manual_state WHERE id = 'singleton'", None),
        (
            "INSERT INTO quant_core.macro_manual_state (id, regime_override, confidence, evidence, updated_at) "
            "VALUES ('singleton', ?, ?, ?, CURRENT_TIMESTAMP)",
            [
                rg,
                float(parsed["confidence"]),
                str(parsed["evidence"] or "")[:8000],
            ],
        ),
    ]

    ok, detail = _vault_apply_sql_statements(db, stmts, tenant_id=tid)
    if not ok:
        return f"No se pudo registrar el régimen manual: {detail}"
    conf_pct = float(parsed["confidence"]) * 100.0
    return (
        "✅ Régimen manual actualizado (singleton writer).\n"
        f"- Régimen: {rg} (conf objetivo fly {conf_pct:.0f}%)\n"
        "El pipeline MOC usará esta pista antes de las reglas por VIX.\n"
        "Contexto opcional para VSS: /context --add … en la misma bóveda."
    )


def execute_quant_execute_all_moc(db: Any, chat_id: Any, args: str) -> str:
    """/execute_all_moc <session_uid>: aprueba y ejecuta en secuencia señales MOC batch."""
    from duckclaw.forge.skills.quant_hitl import grant_execute_order
    from duckclaw.forge.skills.quant_tool_context import (
        set_quant_tool_chat_id,
        set_quant_tool_db_path,
    )
    from duckclaw.forge.skills.quant_trader_bridge import _execute_approved_signal_impl

    session_uid = (args or "").strip().split()[0] if (args or "").strip() else ""
    if not re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        session_uid,
        re.IGNORECASE,
    ):
        return "Uso: /execute_all_moc <session_uid_UUID>"
    try:
        from duckclaw.graphs.graph_server import get_db as _get_db

        _db = _get_db()
        tid = str(get_chat_state(_db, chat_id, "tenant_id") or "default").strip() or "default"
        rid = str(get_chat_state(_db, chat_id, "last_requester_id") or "").strip()
        if _is_wr_tenant(tid):
            clearance = _wr_member_clearance(_db, tenant_id=tid, user_id=rid)
            if not (_is_gateway_owner_user(rid) or clearance == "admin"):
                return "❌ Acceso denegado: /execute_all_moc en War Room requiere clearance admin."
    except Exception:
        pass

    raw_path = str(getattr(db, "_path", "") or "").strip()
    if raw_path:
        set_quant_tool_db_path(raw_path)
    set_quant_tool_chat_id(str(chat_id).strip())

    esc = session_uid.replace("'", "''")
    sql = (
        "SELECT CAST(fs.signal_id AS VARCHAR) AS signal_id "
        "FROM finance_worker.trade_signals fs "
        "INNER JOIN quant_core.trade_signals q ON q.signal_id = fs.signal_id "
        f"WHERE q.session_uid = '{esc}' AND COALESCE(q.strategy_name, '') = 'moc_hrp_cfd' "
        "AND UPPER(COALESCE(fs.status, '')) = 'PENDING_HITL' ORDER BY fs.ticker NULLS LAST"
    )
    try:
        raw = db.query(sql)
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception as exc:
        return f"No se pudieron listar señales MOC: {exc}"
    signal_ids = [
        str((r or {}).get("signal_id") or "").strip().lower()
        for r in rows
        if isinstance(r, dict) and (r or {}).get("signal_id")
    ]
    if not signal_ids:
        return (
            "No hay señales PENDING_HITL `moc_hrp_cfd` para esa session_uid "
            "(o ya fueron ejecutadas/canceladas)."
        )

    ib_order_ids: list[str] = []
    notionals_parts: list[str] = []
    skipped: list[str] = []

    cid = str(chat_id or "").strip() or "default"
    for sid in signal_ids:
        ok_ledger, ledger_msg = _execute_signal_verify_ledger(db, sid)
        if not ok_ledger:
            skipped.append(f"{sid[:13]}… — {ledger_msg}")
            continue
        grant_execute_order(cid, sid)
        exec_raw = _execute_approved_signal_impl(db, signal_id=sid)
        ej: dict[str, Any] = {}
        try:
            if isinstance(exec_raw, str) and exec_raw.strip().startswith("{"):
                ej = json.loads(exec_raw)
        except json.JSONDecodeError:
            ej = {}
        oid = ej.get("ib_order_id") or ej.get("order_id") or ej.get("broker_order_id")
        if oid is not None:
            ib_order_ids.append(str(oid))
        for key in ("notional_usd", "notional", "amount_usd", "usd_notional"):
            if ej.get(key) is not None:
                try:
                    notionals_parts.append(f"{sid[:8]}:{float(ej.get(key)):,.0f}")
                except (TypeError, ValueError):
                    pass
                break

    def _summarize_notional(parts: list[str]) -> float:
        total = 0.0
        for p in parts:
            try:
                total += abs(float((p.split(":", maxsplit=1)[-1] or "").replace(",", "")))
            except (ValueError, TypeError):
                continue
        return total

    total_n = _summarize_notional(notionals_parts)
    rep = (
        f"✅ MOC ejecutado: {len(signal_ids) - len(skipped)} órdenes "
        f"(listadas {len(signal_ids)}).\n"
        f"Notional declarado (~sum componentes Telegram): USD {total_n:,.0f}\n"
        f"IDs: {', '.join(ib_order_ids) if ib_order_ids else '(extraer desde execution JSON)'}"
    )
    if skipped:
        rep += "\nOmitidas:\n" + "\n".join(skipped[:12])
    return rep


def execute_cancel_signal(db: Any, chat_id: Any, args: str, *, tenant_id: Any = None) -> str:
    """/cancel_signal <signal_id>: marca PENDING_HITL/AWAITING_HITL como CANCELLED."""
    _ = chat_id
    sid = (args or "").strip().lower().split()[0] if (args or "").strip() else ""
    if not re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", sid):
        return "Uso: /cancel_signal <signal_id_UUID>"
    tid = str(tenant_id or "default").strip() or "default"
    qsid = sid.replace("'", "''")
    try:
        raw = db.query(
            "SELECT status FROM finance_worker.trade_signals "
            f"WHERE signal_id = '{qsid}' LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception:
        rows = []
    st = str(rows[0].get("status") or "").strip().upper() if rows and isinstance(rows[0], dict) else ""
    if st and st not in ("PENDING_HITL", "AWAITING_HITL", "PENDING"):
        return f"No se puede cancelar: estado actual {st}."
    ok, detail = _vault_apply_sql_statements(
        db,
        [
            (
                "UPDATE finance_worker.trade_signals SET status='CANCELLED' "
                "WHERE signal_id = ? AND status IN ('PENDING_HITL','AWAITING_HITL','PENDING')",
                [sid],
            ),
            (
                "UPDATE quant_core.trade_signals SET status='CANCELLED', updated_at=now() "
                "WHERE signal_id = ? AND status IN ('PENDING_HITL','AWAITING_HITL','PENDING')",
                [sid],
            ),
        ],
        tenant_id=tid,
    )
    if not ok:
        return f"No se pudo cancelar la señal: {detail}"
    return f"❌ Señal {sid} cancelada."


def _dispatch_fly_command(
    db: Any,
    chat_id: Any,
    name: str,
    args: str,
    *,
    requester_id: Any = None,
    tenant_id: Any = None,
    vault_user_id: Any = None,
    username: str = "",
    entry_worker_id: str | None = None,
) -> Optional[str]:
    """Ejecuta un comando fly ya parseado (sin contexto de logging)."""
    if name == "sensors":
        return execute_sensors(db)
    if name == "lake":
        sub = (args or "").strip().lower()
        if sub in ("", "status"):
            return execute_lake_status()
        return "Uso: /lake o /lake status"
    if name in ("execute_signal", "execute-signal"):
        return execute_quant_execute_signal(db, chat_id, args)
    if name == "execute_all_moc":
        return execute_quant_execute_all_moc(db, chat_id, args)
    if name == "profile":
        return execute_quant_profile(db, chat_id, args, tenant_id=tenant_id)
    if name == "macro":
        return execute_quant_macro_update(
            db, chat_id, args, requester_id=requester_id, tenant_id=tenant_id
        )
    if name == "cancel_signal":
        return execute_cancel_signal(db, chat_id, args, tenant_id=tenant_id)
    if name in ("trading-session", "trading_session"):
        return execute_trading_session(
            db,
            chat_id,
            args,
            tenant_id=tenant_id,
            vault_user_id=vault_user_id,
        )
    if name == "quant_cycle":
        return execute_quant_cycle(
            db,
            chat_id,
            args,
            tenant_id=tenant_id,
            vault_user_id=vault_user_id,
        )
    if name == "register_wr_member":
        return register_wr_member(db, tenant_id, requester_id, args)
    if name == "get_wr_context":
        return get_wr_context(db, tenant_id, args)
    if name == "broadcast_alert":
        return broadcast_alert(db, tenant_id, requester_id, args)
    if name == "help":
        return execute_help(db, chat_id)
    if name == "role":
        return (
            "El comando /role ya no existe. Usa /workers para ver o definir el equipo, /help para ver todos los comandos."
        
        )
    if name == "roles":
        return execute_roles(db, chat_id)
    if name == "team":
        return execute_team_whitelist(db, tenant_id, requester_id, args)
    if name == "vault":
        return execute_vault(
            args,
            vault_user_id=vault_user_id or requester_id or chat_id,
            tenant_id=tenant_id,
            db=db,
            entry_worker_id=entry_worker_id,
            chat_id=chat_id,
        )
    if name == "workers":
        return execute_team(
            db, chat_id, args, tenant_id=tenant_id, requester_id=requester_id
        )
    if name == "skills":
        return execute_skills_list(db, chat_id, args)
    if name == "forget":
        return execute_forget(db, chat_id)
    if name == "context":
        return execute_context_toggle(db, chat_id, args)
    if name in ("sandbox", "sandox"):
        return execute_sandbox_toggle(db, chat_id, args)
    if name == "ibkr":
        return execute_ibkr_toggle(db, chat_id, args)
    if name in ("internet", "red", "network"):
        return execute_internet_toggle(db, chat_id, args, tenant_id=tenant_id)
    if name == "heartbeat":
        return execute_heartbeat(db, chat_id, args, tenant_id=tenant_id)
    if name == "audit":
        return execute_audit(db, chat_id)
    if name == "health":
        return execute_health(db)
    if name == "approve":
        return execute_approve_reject(db, chat_id, True)
    if name == "reject":
        return execute_approve_reject(db, chat_id, False)
    if name in ("prompt", "system_prompt", "system"):
        return execute_prompt(db, chat_id, args)
    if name in ("model", "provider", "llm"):
        return execute_model(db, chat_id, args)
    if name in ("models",):
        return execute_models(db, chat_id, args)
    if name == "setup":
        return _execute_setup(db, chat_id, args)
    if name in ("crons", "goals"):
        return execute_goals(
            db,
            chat_id,
            args,
            tenant_id=tenant_id,
            vault_user_id=vault_user_id,
        )
    if name == "tasks":
        return execute_tasks(db, chat_id)
    if name == "history":
        return execute_history(db, chat_id, args)
    return None




def handle_command(
    db: Any,
    chat_id: Any,
    text: str,
    *,
    requester_id: Any = None,
    tenant_id: Any = None,
    vault_user_id: Any = None,
    username: str = "",
    entry_worker_id: str | None = None,
) -> Optional[str]:
    """
    Middleware: si el mensaje es un comando on-the-fly, ejecuta y retorna la respuesta.
    Si no es comando o no es manejado, retorna None.
    """
    name, args = parse_command(text)
    if not name:
        return None
    tid = str(tenant_id or "default").strip() or "default"
    try:
        cid = str(chat_id if chat_id is not None else "unknown").strip() or "unknown"
    except Exception:
        cid = "unknown"
    uname = (username or "").strip()
    if not uname and db is not None:
        try:
            uname = str(get_chat_state(db, chat_id, "username") or "").strip()
        except Exception:
            uname = ""
    chat_ident = format_chat_log_identity(cid, uname or None)
    _fly_log = get_obs_logger("duckclaw.fly")
    with structured_log_context(tenant_id=tid, worker_id="gateway", chat_id=chat_ident):
        try:
            set_chat_state(db, chat_id, "tenant_id", tid)
            if requester_id is not None:
                set_chat_state(db, chat_id, "last_requester_id", str(requester_id).strip())
        except Exception:
            pass
        out = _dispatch_fly_command(
            db,
            chat_id,
            name,
            args,
            requester_id=requester_id,
            tenant_id=tenant_id,
            vault_user_id=vault_user_id,
            username=username or "",
            entry_worker_id=entry_worker_id,
        )
        if out is not None:
            log_fly(_fly_log, "/%s -> %s", name, _fly_reply_preview(out))
        return out


def _execute_setup(db: Any, chat_id: Any, args: str) -> str:
    """/setup [key=value | key=value]: formato compatible con Telegram. Sin args muestra config."""
    if not args or not args.strip():
        p = get_chat_state(db, chat_id, "llm_provider") or _get_global_config(db, "llm_provider")
        m = get_chat_state(db, chat_id, "llm_model") or _get_global_config(db, "llm_model")
        wid = get_chat_state(db, chat_id, "worker_id")
        prompt = _get_global_config(db, "system_prompt") or ""
        return (
            f"Config actual:\n- llm_provider: {p or '—'}\n- llm_model: {m or '—'}\n"
            f"- worker_id: {wid or '—'}\n- system_prompt: {prompt[:80]}...\n\n"
            "Para cambiar: /setup llm_provider=deepseek | /setup system_prompt=..."
        
        )
    for part in args.split("|"):
        part = part.strip()
        if "=" in part:
            k, _, v = part.partition("=")
            k, v = k.strip().lower(), v.strip()
            if k in ("llm_provider", "provider"):
                if v and v.lower() not in _PROVIDERS:
                    return f"Provider desconocido: {v}. Válidos: {', '.join(_PROVIDERS)}"
                set_chat_state(db, chat_id, "llm_provider", v)
                if v.lower() == "mlx":
                    from duckclaw.integrations.llm_providers import mlx_openai_compatible_base_url

                    set_chat_state(db, chat_id, "llm_base_url", mlx_openai_compatible_base_url())
                    mid = (os.environ.get("MLX_MODEL_ID") or os.environ.get("MLX_MODEL_PATH") or "").strip()
                    set_chat_state(db, chat_id, "llm_model", mid)
                else:
                    default_model = _DEFAULT_MODEL_BY_PROVIDER.get(v.lower(), "")
                    set_chat_state(db, chat_id, "llm_model", default_model)
                    default_url = _DEFAULT_BASE_URL_BY_PROVIDER.get(v.lower(), "")
                    if default_url:
                        set_chat_state(db, chat_id, "llm_base_url", default_url)
                    else:
                        set_chat_state(db, chat_id, "llm_base_url", "")
            elif k in ("llm_model", "model"):
                set_chat_state(db, chat_id, "llm_model", v)
            elif k in ("llm_base_url", "base_url"):
                set_chat_state(db, chat_id, "llm_base_url", v)
            elif k in ("system_prompt", "prompt"):
                _set_global_config(db, "system_prompt", v)
    return "✅ Config actualizado."


def get_history_limit_for_chat(db: Any, chat_id: Any, default: int = 10) -> int:
    """Devuelve el límite de historial según use_rag del chat (para /context off = menos contexto)."""
    use_rag = get_chat_state(db, chat_id, "use_rag")
    if use_rag == "false":
        return 3
    return default


def get_worker_id_for_chat(db: Any, chat_id: Any) -> str:
    """Devuelve el worker_id asignado a este chat. Por defecto: manager (orquesta y delega a templates)."""
    return get_chat_state(db, chat_id, "worker_id") or _DEFAULT_WORKER


def save_last_audit(db: Any, chat_id: Any, latency_ms: int, sql: str = "", run_id: str = "", tokens: Any = None) -> None:
    """Guarda datos de la última ejecución para /audit."""
    data = {"latency_ms": latency_ms, "sql": sql or "", "run_id": run_id or "", "tokens": tokens or ""}
    set_chat_state(db, chat_id, "last_audit", json.dumps(data))


_TASK_AUDIT_TABLE = "task_audit_log"


def _ensure_task_audit_log(db: Any) -> None:
    """Crea task_audit_log y aplica migraciones suaves (plan_title)."""
    if _skip_runtime_ddl(db):
        return
    db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_TASK_AUDIT_TABLE} (
            task_id VARCHAR PRIMARY KEY,
            tenant_id VARCHAR NOT NULL,
            worker_id VARCHAR,
            query_prefix VARCHAR,
            status VARCHAR NOT NULL,
            duration_ms INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            plan_title VARCHAR
        )
        """
    )
    # Migración suave: añadir plan_title si la tabla existe sin esta columna (bases antiguas)
    try:
        info = db.query(f"PRAGMA table_info({_TASK_AUDIT_TABLE})")
        rows = json.loads(info) if isinstance(info, str) else (info or [])
        cols = {str(r.get("name") or "") for r in rows if isinstance(r, dict)}
        if "plan_title" not in cols:
            db.execute(f"ALTER TABLE {_TASK_AUDIT_TABLE} ADD COLUMN plan_title VARCHAR")
    except Exception:
        # No romper si PRAGMA/ALTER falla; la feature seguirá funcionando sin plan_title persistente.
        pass


def _infer_user_id_for_audit_queue(db_path: str) -> str:
    """Alineado con validate_user_db_path: slug bajo db/private/{user}/."""
    from pathlib import Path

    parts = Path(db_path).expanduser().resolve().parts
    if "private" in parts:
        i = parts.index("private")
        if i + 1 < len(parts):
            return str(parts[i + 1])
    return "default"


def append_task_audit(
    db: Any,
    tenant_id: Any,
    worker_id: str,
    query_prefix: str,
    status: str,
    duration_ms: int,
    plan_title: Optional[str] = None,
) -> None:
    """Append a task to task_audit_log for /history. plan_title es el identificador semántico para auditoría y /history."""
    import uuid

    _ensure_task_audit_log(db)
    task_id = f"TASK-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    tenant_s = str(tenant_id).replace("'", "''")[:128]
    worker_s = (worker_id or "").replace("'", "''")[:64]
    prefix_s = (query_prefix or "")[:256].replace("'", "''")
    status_s = (status or "SUCCESS").upper().replace("'", "''")[:32]
    status_allowed = ("SUCCESS", "FAILED", "PROACTIVE_MESSAGE_SENT", "SECURITY_VIOLATION_ATTEMPT")
    status_s = "SUCCESS" if status_s not in status_allowed else status_s
    plan_title_s = (plan_title or "")[:256].replace("'", "''") if plan_title else ""
    sql = (
        f"""
        INSERT INTO {_TASK_AUDIT_TABLE} (task_id, tenant_id, worker_id, query_prefix, status, duration_ms, plan_title)
        VALUES ('{task_id}', '{tenant_s}', '{worker_s}', '{prefix_s}', '{status_s}', {int(duration_ms)}, '{plan_title_s}')
        """
    )
    if _skip_runtime_ddl(db):
        try:
            from pathlib import Path

            from duckclaw.db_write_queue import enqueue_duckdb_write_sync, poll_task_status_sync

            raw_path = str(getattr(db, "_path", "") or "").strip()
            if not raw_path or raw_path == ":memory:":
                return
            resolved = str(Path(raw_path).expanduser().resolve())
            uid = _infer_user_id_for_audit_queue(resolved)
            # El manager RO mantiene ``duckdb.connect`` al vault: db-writer no puede tomar RW
            # hasta suspender el handle (mismo patrón que ``admin_sql`` para workers RO).
            released_ro = False
            try:
                release = getattr(db, "release_file_handle_for_external_writer", None)
                susp = getattr(db, "suspend_readonly_file_handle", None)
                resu = getattr(db, "resume_readonly_file_handle", None)
                if callable(release):
                    release()
                    released_ro = bool(callable(resu))
                elif callable(susp) and callable(resu):
                    susp()
                    released_ro = True
                write_tid = enqueue_duckdb_write_sync(
                    db_path=resolved,
                    query=sql.strip(),
                    user_id=uid,
                    tenant_id=str(tenant_id or "default").strip() or "default",
                )
                poll_task_status_sync(write_tid, timeout_sec=15.0)
            finally:
                if released_ro:
                    try:
                        resu2 = getattr(db, "resume_readonly_file_handle", None)
                        if callable(resu2):
                            resu2()
                    except Exception:
                        pass
        except Exception:
            pass
        return
    db.execute(sql)


def _is_simple_greeting(prefix: str) -> bool:
    """True si el mensaje es un saludo corto (hola, hi, etc.) sin tarea real."""
    p = (prefix or "").strip().lower()[:50]
    if len(p) > 35:
        return False
    greetings = (
        "hola", "hi", "hey", "hello", "buenas", "qué tal", "que tal",
        "buenos días", "buenos dias", "buenas tardes", "buenas noches",
        "ola", "saludos", "ciao", "adios", "chao",
    )
    return p in greetings or p.rstrip("!?.") in greetings


_CAPABILITIES_SMALLTALK = re.compile(
    r"""^[\s¿¡]*(
  qu[eé]\s+puedes\s+hacer(\s+ahora|\s+por\s+m[ií]|\s+por\s+nosotros)? |
  qu[eé]\s+sabes\s+hacer |
  en\s+qu[eé]\s+puedes\s+ayud(ar|arme) |
  qu[eé]\s+puedes\s+ofrec(er|erme) |
  cu[aá]les\s+son\s+tus\s+capacidades |
  para\s+qu[eé]\s+sirves |
  qu[eé]\s+funciones\s+tienes |
  mu[eé]strame\s+qu[eé]\s+puedes(\s+hacer)? |
  what\s+can\s+you\s+do |
  how\s+can\s+you\s+help(\s+me)?
)[\s?!.]*$""",
    re.IGNORECASE | re.VERBOSE,
)

# Pedidos de ejemplo meta (sin dataset concreto): no invocar plan + worker
# Nota: ``pued(es|as|a|e)`` cubre «puedes», «puedas», «puede», «pueda» (no usar ``pueda?s?``, que no casa «puedes»).
_CAPABILITIES_EXAMPLE_SMALLTALK = re.compile(
    r"""^[\s¿¡]*(
  d[aá]me\s+(un\s+)?ejemplo(\s+de\s+algo)?\s+que\s+pued(es|as|a|e)\s+hacer |
  d[aá]me\s+un\s+ejemplo\s+de\s+lo\s+que\s+pued(es|as|a|e)\s+hacer |
  (mu[eé]strame|ens[eé][ñn]ame)\s+(un\s+)?ejemplo(\s+de\s+algo\s+que\s+pued(es|as|a|e)\s+hacer)? |
  (mu[eé]strame|ens[eé][ñn]ame)\s+un\s+ejemplo |
  ejemplo\s+de\s+algo\s+que\s+pued(es|as|a|e)\s+hacer |
  un\s+ejemplo\s+de\s+lo\s+que\s+pued(es|as|a|e)\s+hacer |
  pued(es|as|a|e)\s+dar(me)?\s+un\s+ejemplo |
  alg[uú]n\s+ejemplo\s+de\s+lo\s+que\s+pued(es|as|a|e)\s+hacer |
  give\s+me\s+an?\s+example(\s+of\s+what\s+you\s+can\s+do)? |
  show\s+me\s+an?\s+example
)[\s?!.]*$""",
    re.IGNORECASE | re.VERBOSE,
)


def _is_capabilities_smalltalk(text: str) -> bool:
    """
    True si el usuario pide capacidades o un ejemplo genérico de uso, en una frase corta,
    sin datos concretos (evita plan LLM + invoke_worker).
    """
    raw = (text or "").strip()
    if not raw or raw.startswith("/"):
        return False
    if len(raw) > 120:
        return False
    # Pregunta meta + pedido concreto: mejor pasar por el planner
    if re.search(
        r"\b(con|sobre|analiz|datos|tabla|tablas|sql|ventas|csv|duckdb|query|métrica|metrica|grafico|gráfico)\b",
        raw,
        re.I,
    ):
        return False
    return bool(_CAPABILITIES_SMALLTALK.match(raw) or _CAPABILITIES_EXAMPLE_SMALLTALK.match(raw))


def _is_complex_task(row: dict) -> bool:
    """True si la tarea usó herramientas (tool use) o no es un saludo simple."""
    prefix = (row.get("query_prefix") or "").strip()
    if _is_simple_greeting(prefix):
        return False
    try:
        dur_ms = int(row.get("duration_ms") or 0)
    except (TypeError, ValueError):
        dur_ms = 0
    return dur_ms >= 1500 or len(prefix) > 20


def execute_history(db: Any, chat_id: Any, args: str) -> str:
    """/history [n]: historial de tareas complejas (tool use). Saludos simples (hola) se muestran como máximo uno."""
    tenant_s = str(chat_id).replace("'", "''")[:128]
    try:
        n = int((args or "5").strip())
        n = max(1, min(n, 20))
    except ValueError:
        n = 5
    _ensure_task_audit_log(db)
    try:
        r = db.query(
            f"""
            SELECT task_id, query_prefix, status, duration_ms, created_at, worker_id, plan_title
            FROM {_TASK_AUDIT_TABLE}
            WHERE tenant_id = '{tenant_s}'
            ORDER BY created_at DESC
            LIMIT 100
            """
        )
        rows = json.loads(r) if isinstance(r, str) else (r or [])
    except Exception as e:
        return f"Error al cargar historial: {e}."

    if not rows:
        return "📋 Sin tareas registradas."

    # Filtrar: tareas complejas con título de plan + como máximo 1 saludo simple
    complex_rows = []
    one_greeting = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        plan_title_raw = (row.get("plan_title") or "").strip()
        if _is_complex_task(row) and plan_title_raw:
            complex_rows.append(row)
        elif one_greeting is None and _is_simple_greeting(row.get("query_prefix") or ""):
            one_greeting = row
    filtered = complex_rows[:n]
    if one_greeting is not None and len(filtered) < n:
        filtered.append(one_greeting)

    if not filtered:
        return "📋 Sin tareas complejas."

    # Evitar duplicados: si hay varias filas con mismo worker/status/duración y
    # solo algunas tienen plan_title explícito, preferir las que sí lo tienen.
    deduped = []
    for idx, row in enumerate(filtered):
        if not isinstance(row, dict):
            continue
        raw_plan = (row.get("plan_title") or "").strip()
        if not raw_plan:
            wid = (row.get("worker_id") or "").strip()
            status = (row.get("status") or "UNKNOWN").upper()
            try:
                dur_ms = int(row.get("duration_ms") or 0)
            except (TypeError, ValueError):
                dur_ms = 0
            has_better = False
            for j, other in enumerate(filtered):
                if j == idx or not isinstance(other, dict):
                    continue
                other_plan = (other.get("plan_title") or "").strip()
                if not other_plan:
                    continue
                wid2 = (other.get("worker_id") or "").strip()
                status2 = (other.get("status") or "UNKNOWN").upper()
                try:
                    dur2 = int(other.get("duration_ms") or 0)
                except (TypeError, ValueError):
                    dur2 = 0
                if wid2 == wid and status2 == status and dur2 == dur_ms:
                    has_better = True
                    break
            if has_better:
                continue
        deduped.append(row)

    if not deduped:
        return "📋 Sin tareas complejas."

    lines = [f"📋 Últimas {len(deduped)}"]
    for i, row in enumerate(deduped, 1):
        if not isinstance(row, dict):
            continue
        prefix = (row.get("query_prefix") or "").strip()[:80]
        # Título del plan (guardado por el Manager): se muestra después del subagente
        plan_title = (row.get("plan_title") or "").strip()
        if not plan_title:
            # Fallback retrocompatible: derivar un pseudo-título desde query_prefix
            if prefix:
                words = prefix.split()
                plan_title = " ".join(words[:5])
            else:
                plan_title = "Interacción del Usuario"
        status = (row.get("status") or "UNKNOWN").upper()
        wid = (row.get("worker_id") or "").strip()
        try:
            dur_ms = int(row.get("duration_ms") or 0)
        except (TypeError, ValueError):
            dur_ms = 0
        dur_s = f"{dur_ms / 1000:.1f}s"
        # Formato: número. [subagente] Título del plan · ⏱️ duración
        worker_part = f"[{wid}] " if wid else ""
        title_part = plan_title if plan_title else ""
        lines.append(f"{i}. {worker_part}{title_part} · ⏱️ {dur_s}")

    success_rows = [r for r in filtered if isinstance(r, dict) and (r.get("status") or "").upper() == "SUCCESS"]
    def _dur(r):
        try:
            return int(r.get("duration_ms") or 0)
        except (TypeError, ValueError):
            return 0
    avg_ms = sum(_dur(r) for r in success_rows) / len(success_rows) if success_rows else 0
    try:
        r24 = db.query(
            f"""
            SELECT COUNT(*) as cnt FROM {_TASK_AUDIT_TABLE}
            WHERE tenant_id = '{tenant_s}' AND status = 'FAILED'
            AND created_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
            """
        )
        rows24 = json.loads(r24) if isinstance(r24, str) else (r24 or [])
        failed_24h = rows24[0].get("cnt", 0) if rows24 else 0
    except Exception:
        failed_24h = 0
    lines.append(f"— avg {avg_ms/1000:.1f}s · fallidas 24h: {failed_24h}")

    return "\n".join(lines)