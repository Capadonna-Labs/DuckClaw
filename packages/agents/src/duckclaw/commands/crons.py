"""DB-first chat scheduling commands for proactive goal reviews."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time
from typing import Any, Optional

from duckclaw.commands.chat_state import (
    _PREFIX,
    _chat_key,
    get_chat_state,
    set_chat_state,
)
from duckclaw.runtime.scheduling.cron_wall_schedule import (
    format_cron_wall_human,
    parse_cron_wall_tokens,
)

_CRONS_DEBUG_LOG = "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-fd1dbb.log"

# Revisión proactiva /crons --delta (agent_config; claves internas goals_* sin cambiar)
_GOALS_DELTA_SECONDS_KEY = "goals_delta_seconds"
_GOALS_PROACTIVE_LAST_FIRE_KEY = "goals_proactive_last_fire_epoch"
_GOALS_PROACTIVE_ANCHOR_KEY = "goals_proactive_schedule_anchor_epoch"
_GOALS_PROACTIVE_TENANT_KEY = "goals_proactive_tenant_id"
_GOALS_DELTA_ANCHOR_LEGACY_KEY = "goals_delta_anchor"
_GOALS_DELTA_META_KEY = "goals_delta_meta"
_GOALS_PROACTIVE_NOTIFY_KEY = "goals_proactive_notify_channel"
_GOALS_CRON_WALL_KEY = "goals_cron_wall"
GOALS_DELTA_MIN_SECONDS = 60
GOALS_DELTA_MAX_SECONDS = 7 * 24 * 3600

# IDs mostrados en /crons para quitar un schedule con /crons --rm <cron-id>
CRON_SCHEDULE_ID_DELTA = "delta"
CRON_SCHEDULE_ID_WALL = "wall"


def _crons_debug_log(
    location: str,
    message: str,
    data: dict[str, Any],
    *,
    hypothesis_id: str = "crons",
) -> None:
    # #region agent log
    try:
        with open(_CRONS_DEBUG_LOG, "a", encoding="utf-8") as _f:
            _f.write(
                json.dumps(
                    {
                        "sessionId": "fd1dbb",
                        "location": location,
                        "message": message,
                        "data": data,
                        "timestamp": int(time.time() * 1000),
                        "hypothesisId": hypothesis_id,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:
        pass
    # #endregion


def _normalize_cron_rm_id(token: str) -> Optional[str]:
    """``delta`` / ``interval`` → intervalo; ``wall`` / ``timestamp`` → reloj."""
    t = (token or "").strip().lower()
    if t in (CRON_SCHEDULE_ID_DELTA, "interval"):
        return CRON_SCHEDULE_ID_DELTA
    if t in (CRON_SCHEDULE_ID_WALL, "timestamp"):
        return CRON_SCHEDULE_ID_WALL
    return None


def _extract_crons_delta_options(toks: list[str]) -> tuple[list[str], dict[str, Any], Optional[str]]:
    """
    Parsea tokens tras ``--delta``: duración + flags ``--notify``, ``--mode``, ``--jitter``.
    ``toks[0]`` debe ser ``--delta``.
    """
    dur_parts: list[str] = []
    opts: dict[str, Any] = {}
    i = 1
    while i < len(toks):
        t = toks[i]
        if t == "--notify":
            if i + 1 >= len(toks):
                return [], {}, "Falta valor tras --notify (admin, telegram o both)."
            opts["notify"] = toks[i + 1]
            i += 2
            continue
        if t == "--mode":
            if i + 1 >= len(toks):
                return [], {}, "Falta valor tras --mode (always u on_misalignment)."
            opts["mode"] = toks[i + 1]
            i += 2
            continue
        if t == "--jitter":
            if i + 1 >= len(toks):
                return [], {}, "Falta valor tras --jitter (ej. 20% o 0.15)."
            opts["jitter"] = toks[i + 1]
            i += 2
            continue
        if t.startswith("--"):
            return [], {}, f"Flag desconocida: {t}"
        dur_parts.append(t)
        i += 1
    return dur_parts, opts, None


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

    legacy_poll_env = "GOALS_" + "TIC" + "KER_POLL_SECONDS"
    poll_s = _int_env("GOALS_POLL_SECONDS", os.getenv(legacy_poll_env, "45"))
    hb_s = _int_env("HEARTBEAT_INTERVAL_SECONDS", "3600")
    legacy_embed_env = "DUCKCLAW_EMBED_GOALS_" + "TIC" + "KER"
    embed_raw = (
        os.getenv("DUCKCLAW_EMBED_GOALS_SCHEDULER")
        or os.getenv(legacy_embed_env)
        or "true"
    ).strip().lower()
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
    """Bloque de intervalo delta en el listado /crons."""
    try:
        ds_list = int((get_chat_state(db, chat_id, _GOALS_DELTA_SECONDS_KEY) or "0").strip() or "0")
    except ValueError:
        ds_list = 0
    if ds_list <= 0:
        return ""

    interval_h, countdown_part, last_bit = _goals_proactive_interval_countdown_parts(db, chat_id, ds_list)
    notify_raw = (get_chat_state(db, chat_id, _GOALS_PROACTIVE_NOTIFY_KEY) or "").strip()
    meta = _crons_goals_delta_meta_dict(db, chat_id)
    mode_raw = str((meta or {}).get("mode") or "").strip()
    jitter_raw = (meta or {}).get("jitter_ratio")
    notify_line = f" · canal: {notify_raw}" if notify_raw else ""
    mode_line = f" · modo: {mode_raw}" if mode_raw else ""
    jitter_line = ""
    if jitter_raw is not None:
        try:
            jr = float(jitter_raw)
            jitter_line = f" · jitter: {int(jr * 100)}%"
        except (TypeError, ValueError):
            pass
    line = (
        f"- Intervalo (cron-id {CRON_SCHEDULE_ID_DELTA}): cada ~{interval_h}{countdown_part}"
        f"{last_bit}{notify_line}{mode_line}{jitter_line} "
        f"(/crons --delta off o /crons --rm {CRON_SCHEDULE_ID_DELTA})."
    )
    return "\n\nRevisión proactiva\n" + line


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
    set_chat_state(conn, chat_id, _GOALS_PROACTIVE_NOTIFY_KEY, "")


def _enqueue_agent_config_entries_remote(
    db_path: str,
    chat_id: Any,
    suffix_values: dict[str, Any],
) -> None:
    """Queue chat-scoped agent_config upserts for a remote DuckDB file."""
    from duckclaw.db_write_queue import enqueue_typed_command
    from duckclaw.write_commands import UpsertAgentConfigEntriesCommand

    entries = {
        _chat_key(chat_id, suffix): str(value)[:16384]
        for suffix, value in suffix_values.items()
        if str(suffix or "").strip()
    }
    if not entries:
        return
    try:
        target = str(Path(db_path).expanduser().resolve())
    except OSError:
        target = str(db_path)

    enqueue_typed_command(
        UpsertAgentConfigEntriesCommand(
            tenant_id="default",
            actor_email="system",
            entries=entries,
        ),
        db_path=target,
        user_id=str(chat_id),
    )


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

    from duckclaw.gateway_db import iter_goals_delta_clear_duckdb_paths

    for _p in iter_goals_delta_clear_duckdb_paths(primary_fly_db_path=primary_resolved):
        _rp = ""
        try:
            _rp = str(Path(_p).expanduser().resolve())
        except OSError:
            _rp = str(_p)
        if primary_resolved and _rp == primary_resolved:
            continue
        try:
            _enqueue_agent_config_entries_remote(
                _p,
                chat_id,
                {
                    _GOALS_DELTA_SECONDS_KEY: "0",
                    _GOALS_PROACTIVE_ANCHOR_KEY: "",
                    _GOALS_DELTA_ANCHOR_LEGACY_KEY: "",
                    _GOALS_DELTA_META_KEY: "",
                    _GOALS_PROACTIVE_NOTIFY_KEY: "",
                },
            )
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

    from duckclaw.gateway_db import iter_goals_delta_clear_duckdb_paths

    for _p in iter_goals_delta_clear_duckdb_paths(primary_fly_db_path=primary_resolved):
        _rp = ""
        try:
            _rp = str(Path(_p).expanduser().resolve())
        except OSError:
            _rp = str(_p)
        if primary_resolved and _rp == primary_resolved:
            continue
        try:
            _enqueue_agent_config_entries_remote(
                _p,
                chat_id,
                {_GOALS_CRON_WALL_KEY: ""},
            )
        except Exception:
            continue


def clear_goals_proactive_schedule(db: Any, chat_id: Any) -> None:
    """
    Apaga el programador ``/crons --delta`` en el hub y en las bóvedas del **mismo** usuario que
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

    from duckclaw.gateway_db import iter_goals_delta_clear_duckdb_paths

    for _p in iter_goals_delta_clear_duckdb_paths(primary_fly_db_path=primary_resolved):
        _rp = ""
        try:
            _rp = str(Path(_p).expanduser().resolve())
        except OSError:
            _rp = str(_p)
        if primary_resolved and _rp == primary_resolved:
            continue
        try:
            _enqueue_agent_config_entries_remote(
                _p,
                chat_id,
                {
                    _GOALS_DELTA_SECONDS_KEY: "0",
                    _GOALS_PROACTIVE_LAST_FIRE_KEY: "",
                    _GOALS_PROACTIVE_ANCHOR_KEY: "",
                    _GOALS_PROACTIVE_TENANT_KEY: "",
                    _GOALS_DELTA_ANCHOR_LEGACY_KEY: "",
                    _GOALS_DELTA_META_KEY: "",
                    _GOALS_CRON_WALL_KEY: "",
                },
            )
            paths_touched.append(_rp or _p)
        except Exception:
            continue


def _goal_title_for_crons(goal: dict, fallback_key: str) -> str:
    t = (goal.get("title") or "").strip()
    if t:
        return t[:80] + ("…" if len((goal.get("title") or "").strip()) > 80 else "")
    return (goal.get("belief_key") or fallback_key or "").strip()


def build_goals_proactive_system_event_message(goals: list, **_ignored: Any) -> str:
    titles: list[str] = []
    for goal in goals:
        if not isinstance(goal, dict):
            continue
        key = (goal.get("belief_key") or "").strip()
        titles.append(_goal_title_for_crons(goal, key))
    summary = "; ".join(titles[:12]) if titles else "(sin títulos)"
    return (
        "[SYSTEM_EVENT: Revisión periódica de /crons. Objetivos: "
        f"{summary}. Evalúa con herramientas si hace falta qué tan alineado está el "
        "contexto actual con cumplir cada meta. Responde al usuario con un breve "
        "análisis o propuesta concreta.]"
    )


def execute_crons_schedule(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    tenant_id: Any = None,
    vault_user_id: Any = None,
) -> str:
    """/crons [--delta …] [--timestamp …] [--rm …] — solo programación proactiva (metas en /goals)."""
    _ = vault_user_id
    from harness_core.targets import load_homeostasis_manifest

    tid = str(tenant_id or "default").strip() or "default"
    manifest = load_homeostasis_manifest(db, tid, chat_id=chat_id)
    goals_count = len(manifest.goals)

    raw = (args or "").strip()
    toks = raw.split()
    _crons_debug_log(
        "commands/crons.py:execute_crons_schedule",
        "execute_crons_entry",
        {
            "args_preview": raw[:120],
            "chat_id": str(chat_id),
            "tenant_id": tid,
            "goals_count": goals_count,
        },
        hypothesis_id="A",
    )

    if toks and toks[0] == "--delta":
        if len(toks) < 2:
            return (
                "Uso: /crons --delta 20min [--notify admin|telegram|both] "
                "[--mode always|on_misalignment] [--jitter 20%] · /crons --delta off\n"
                "El programador (heartbeat o embebido en el gateway) escanea el hub y las bóvedas "
                f"en db/private/*/*.duckdb. Intervalo permitido: {GOALS_DELTA_MIN_SECONDS}s … 7d."
            )
        dur_parts, sched_opts, opt_err = _extract_crons_delta_options(toks)
        if opt_err:
            return opt_err
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
        from duckclaw.forge.homeostasis.goals_alignment import (
            normalize_jitter_ratio,
            normalize_notify_channel,
            normalize_proactive_mode,
        )

        notify_ch = normalize_notify_channel(str(sched_opts.get("notify") or ""))
        set_chat_state(db, chat_id, _GOALS_PROACTIVE_NOTIFY_KEY, notify_ch)
        mode = normalize_proactive_mode(str(sched_opts.get("mode") or ""))
        jitter_ratio = normalize_jitter_ratio(sched_opts.get("jitter"))
        # Cooldown starts now so the first tick waits ~secs (not the next 45s gateway poll).
        _fire_anchor = str(time.time())
        set_chat_state(db, chat_id, _GOALS_PROACTIVE_LAST_FIRE_KEY, _fire_anchor)
        _anchor_now = _fire_anchor
        set_chat_state(db, chat_id, _GOALS_PROACTIVE_ANCHOR_KEY, _anchor_now)
        set_chat_state(db, chat_id, _GOALS_DELTA_ANCHOR_LEGACY_KEY, _anchor_now)
        meta_obj: dict[str, Any] = {
            "trigger": "goals_cli",
            "mode": mode,
            "jitter_ratio": jitter_ratio,
        }
        set_chat_state(
            db,
            chat_id,
            _GOALS_DELTA_META_KEY,
            json.dumps(meta_obj, ensure_ascii=False),
        )
        human = format_goals_delta_interval_human(secs)
        _crons_debug_log(
            "commands/crons.py:execute_crons_schedule",
            "delta_schedule_persisted",
            {
                "secs": secs,
                "chat_id": str(chat_id),
                "trigger": "goals_cli",
                "mode": mode,
                "notify": notify_ch,
            },
            hypothesis_id="A",
        )
        goals_note = (
            f"Metas homeostasis cargadas: {goals_count}. Define o edita con /goals."
            if goals_count
            else "Sin metas en manifiesto: usa /goals <objetivo> antes del programador proactivo."
        )
        return (
            f"Revisión proactiva cada ~{human} (modo {mode}, canal {notify_ch}, jitter ~{int(jitter_ratio * 100)}%). "
            "El programador disparará SYSTEM_EVENT ante desalineación con el manifiesto /goals, "
            f"o en cada intervalo si modo=always. {goals_note} /crons --delta off para cancelar."
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
                if not isinstance(mobj, dict) or str(mobj.get("trigger") or "").lower() != "goals_wall":
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

    if raw and not raw.startswith("--"):
        return (
            "Las metas homeostasis se gestionan con /goals (no con /crons).\n"
            "Ej.: /goals --set error_rate_pct 2 · /goals para listar.\n"
            "/crons solo programa revisiones: --delta, --timestamp, --rm."
        )

    platform = format_platform_cron_summary()
    proactive_section = _crons_goals_delta_listing_section(db, chat_id)
    wall_note = _goals_cron_wall_listing_note(db, chat_id)
    goals_hint = (
        f"Metas homeostasis: {goals_count} en manifiesto (/goals para ver o editar)."
        if goals_count
        else "Sin metas en manifiesto. Usa /goals <objetivo>."
    )
    user_body = (
        "Tus crons (programación)\n\n"
        f"{goals_hint}\n"
        f"{proactive_section}{wall_note}"
    )
    return f"{user_body}\n\n{platform}"


# Backward compat: tests and imports that still reference execute_goals.
execute_goals = execute_crons_schedule
