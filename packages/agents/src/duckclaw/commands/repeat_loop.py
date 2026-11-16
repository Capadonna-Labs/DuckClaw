"""/loop <intervalo> <prompt o /skill>: repeat a prompt every N, several per chat.

Each loop is one item of the chat's clock-cron list (``goals_cron_wall``, kind ``interval``), so the
Heartbeat runs it like any prompt cron: background turn, "Veredicto:" push, nothing on "sin novedades".
The self-review cycle that used to be /loop is /aware.
"""

from __future__ import annotations

import time
from typing import Any

from duckclaw.commands.chat_state import get_chat_state
from duckclaw.commands.crons import (
    _GOALS_CRON_WALL_KEY,
    _GOALS_PROACTIVE_TENANT_KEY,
    _queued_write_suffix,
    _save_wall_items,
    _set_chat_state_entries,
    format_goals_delta_interval_human,
    parse_goals_delta_arg,
)
from duckclaw.runtime.scheduling.cron_wall_schedule import dump_wall_items, load_wall_items, next_wall_item_id

LOOP_MIN_SECONDS = 5 * 60   # each run is a full agent turn
USAGE = (
    "Uso: /loop 30m /mi_skill · /loop 2h revisa el VIX y avísame si pasa de 25 · "
    "/loop (lista) · /loop off c2 · /loop off all\n"
    f"Intervalo mínimo {LOOP_MIN_SECONDS // 60} min. Puedes tener varios por chat. "
    "El ciclo de auto-revisión es /aware."
)
_AWARE_FIRST = {"on", "reject", "approve", "--status", "--self", "--now", "--delta"}


def is_aware_syntax(args: str) -> bool:
    """Old /loop options (on, --status, approve…): now /aware."""
    first = ((args or "").strip().lower().split() or [""])[0]
    return first in _AWARE_FIRST


def _loops(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [i for i in items if str(i.get("kind") or "") == "interval"]


def _listing(items: list[dict[str, Any]]) -> str:
    loops = _loops(items)
    if not loops:
        return "No hay loops en este chat.\n" + USAGE
    now = time.time()
    lines = ["Loops de este chat:"]
    for i in loops:
        every = int(i.get("every_s") or 0)
        nxt = max(0, int(float(i.get("last_fire") or 0) + every - now))
        lines.append(
            f"- {i['id']}: cada {format_goals_delta_interval_human(every)} → {str(i.get('prompt') or '')[:100]} "
            f"(próxima en ~{format_goals_delta_interval_human(nxt) if nxt >= 60 else 'menos de 1 min'})"
        )
    lines.append("Quita uno con /loop off <id>, o todos con /loop off all.")
    return "\n".join(lines)


def execute_repeat_loop(db: Any, chat_id: Any, args: str, *, tenant_id: Any = None) -> str:
    tid = str(tenant_id or "default").strip() or "default"
    raw = (args or "").strip()
    items = load_wall_items(get_chat_state(db, chat_id, _GOALS_CRON_WALL_KEY))
    toks = raw.split()
    if not toks or toks[0].lower() in ("list", "ls", "--list"):
        return _listing(items)

    if toks[0].lower() in ("off", "stop", "rm"):
        target = toks[1].lower() if len(toks) > 1 else ""
        if not target:
            return "¿Cuál? /loop off <id> (ver ids con /loop) o /loop off all."
        loops = _loops(items)
        drop = {str(i["id"]) for i in loops} if target == "all" else {target} & {str(i["id"]) for i in loops}
        if not drop:
            return f"No hay un loop `{target}` en este chat.\n" + _listing(items)
        err = _save_wall_items(db, chat_id, [i for i in items if str(i.get("id")) not in drop], tenant_id=tid)
        if err:
            return f"No se pudo guardar: {err}"
        return f"Loop(s) detenido(s): {', '.join(sorted(drop))}."

    secs, err = parse_goals_delta_arg(toks[0])
    if err or not secs:
        return (err + "\n" if err else "") + USAGE
    if secs < LOOP_MIN_SECONDS:
        return f"El mínimo de /loop es {LOOP_MIN_SECONDS // 60} min: cada ejecución es un turno completo del agente."
    prompt = raw[len(toks[0]):].strip().strip("\"'“”").strip()[:2000]
    if not prompt:
        return "Falta qué repetir. " + USAGE
    spec = {
        "v": 1,
        "kind": "interval",
        "every_s": secs,
        "prompt": prompt,
        "id": next_wall_item_id(i["id"] for i in items),
        # Non-zero so the Heartbeat does not fall back to the chat's shared last-fire; 1.0 = run on the next poll.
        "last_fire": 1.0,
    }
    ok, perr = _set_chat_state_entries(
        db, chat_id, {_GOALS_CRON_WALL_KEY: dump_wall_items([*items, spec]), _GOALS_PROACTIVE_TENANT_KEY: tid}, tenant_id=tid
    )
    if not ok:
        return f"No se pudo guardar: {perr}"
    return (
        f"Loop {spec['id']} creado: cada {format_goals_delta_interval_human(secs)} → {prompt[:120]}. "
        f"Primera ejecución en ~1 min. /loop para listar, /loop off {spec['id']} para quitarlo."
        f"{_queued_write_suffix(perr)}"
    )
