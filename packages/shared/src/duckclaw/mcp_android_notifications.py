"""Android notification shade — classify rows + dismiss plan for ui_dump."""

from __future__ import annotations

import json
import re
from typing import Any

_UI_DUMP_TOOL_SUFFIX = "__get_ui_dump"
_MIN_ROW_WIDTH = 700
_CLUSTER_Y_GAP = 80
_MAX_ROW_HEIGHT = 280

_NON_DISMISSIBLE_TITLE_RES = tuple(
    re.compile(p, re.I)
    for p in (
        r"^sistema android$",
        r"^android system$",
        r"tarjeta sim",
        r"sim card",
        r"no sim",
        r"sin tarjeta",
        r"usb debugging",
        r"depuraci[oó]n inal[aá]mbrica",
        r"wireless debugging",
        r"depuraci[oó]n usb",
        r"^datos m[oó]viles$",
        r"^bluetooth$",
        r"no interrumpir",
        r"^cargando\b",
        r"^charging\b",
        r"vpn activ",
        r"active vpn",
        r"actualizaci[oó]n del sistema",
        r"system update",
        r"modo desarrollador",
        r"developer mode",
    )
)

_UI_CHROME_LOWER = frozenset(
    {
        "clear all",
        "borrar todo",
        "notificaciones",
        "notifications",
        "configuración",
        "settings",
        "administrar",
        "manage",
        "silenciar",
        "mute",
        "notification shade",
        "panel de notificaciones",
    }
)

_QS_TILE_MARKERS_LOWER = frozenset(
    {
        "datos móviles",
        "datos moviles",
        "mobile data",
        "bluetooth",
        "no interrumpir",
        "do not disturb",
        "wi-fi",
        "wifi",
        "linterna",
        "flashlight",
        "modo avión",
        "airplane mode",
    }
)

_BUTTON_LABELS_LOWER = frozenset(
    {
        "sí",
        "si",
        "no",
        "yes",
        "desactivado",
        "activado",
        "disabled",
        "enabled",
        "abrir",
        "open",
        "responder",
        "reply",
        "cancelar",
        "cancel",
        "hecho",
        "done",
        "descartar",
        "dismiss",
        "cerrar",
        "close",
        "más tarde",
        "later",
        "expandir",
        "contraer",
    }
)

_NODE_OPEN_RE = re.compile(r"<node\b([^>]*?)(?:/>|>)", re.DOTALL)
_NOTIF_DE_RE = re.compile(r"Notificaci[oó]n de ([^:]+):\s*(.*)", re.I)
_TIENE_NOTIF_RE = re.compile(r"^(.+?) tiene \d+ notificaci[oó]n", re.I)
_APP_NAME_IN_DUMP_RE = re.compile(
    r'(?:text|content-desc)="((?:Bloomberg|AfterHour|Reddit|Stocktwits|Telegram|WhatsApp|Chrome|Gmail|SoundCloud)[^"]*)"',
    re.I,
)
_KNOWN_APP_NAMES = (
    "Bloomberg",
    "AfterHour",
    "Reddit",
    "Stocktwits",
    "Telegram",
    "WhatsApp",
    "Chrome",
    "Gmail",
    "SoundCloud",
)
_BODY_SKIP_RE = re.compile(
    r"^(hace \d|expandir|contraer|\d{1,2}:\d{2}|silenciadas|borrar|administrar|spx$)",
    re.I,
)


def is_android_ui_dump_tool(tool_name: str) -> bool:
    return (tool_name or "").strip().lower().endswith(_UI_DUMP_TOOL_SUFFIX)


def is_android_swipe_tool(tool_name: str) -> bool:
    return (tool_name or "").strip().lower().endswith("__swipe_screen")


def is_non_dismissible_notification_title(title: str) -> bool:
    t = (title or "").strip()
    if not t:
        return False
    return any(p.search(t) for p in _NON_DISMISSIBLE_TITLE_RES)


def _is_junk_notification_title(title: str) -> bool:
    t = (title or "").strip()
    if not t or is_button_label(t):
        return True
    if _BODY_SKIP_RE.search(t):
        return True
    low = t.lower()
    if low.startswith("hace "):
        return True
    if low in {"el tiempo", "silenciadas", "ahora"}:
        return True
    return False


def row_should_skip(title: str, body: str = "") -> bool:
    if _is_junk_notification_title(title):
        return True
    if is_non_dismissible_notification_title(title):
        return True
    if is_non_dismissible_notification_title(body):
        return True
    merged = f"{title} {body}".lower()
    if "sistema android" in merged:
        return True
    if "tarjeta sim" in merged:
        return True
    b = (body or "").strip().lower()
    t = (title or "").strip().lower()
    if b in _QS_TILE_MARKERS_LOWER or t in _QS_TILE_MARKERS_LOWER:
        return True
    if len(t) <= 8 and b in _QS_TILE_MARKERS_LOWER:
        return True
    return False


def is_button_label(label: str) -> bool:
    t = (label or "").strip().lower()
    if not t:
        return True
    if t in _BUTTON_LABELS_LOWER:
        return True
    if t in _UI_CHROME_LOWER:
        return True
    return len(t) <= 2


def _parse_attrs(fragment: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in re.finditer(r'([\w:-]+)="([^"]*)"', fragment)}


def _node_label(attrs: dict[str, str]) -> str:
    for key in ("text", "content-desc"):
        val = (attrs.get(key) or "").strip()
        if val and val.lower() not in _UI_CHROME_LOWER:
            return val
    return ""


def _parse_bounds(attrs: dict[str, str]) -> tuple[int, int, int, int] | None:
    raw = (attrs.get("bounds") or "").strip()
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", raw)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))


def _collect_labeled_nodes(raw: str) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for m in _NODE_OPEN_RE.finditer(raw or ""):
        attrs = _parse_attrs(m.group(1))
        label = _node_label(attrs)
        bounds = _parse_bounds(attrs)
        if not label or not bounds or is_button_label(label):
            continue
        x1, y1, x2, y2 = bounds
        height = y2 - y1
        if y1 < 80 or height < 8 or height > 600:
            continue
        nodes.append({"label": label, "bounds": bounds})
    nodes.sort(key=lambda n: (n["bounds"][1], -len(n["label"])))
    return nodes


def _hint_nodes(raw: str) -> list[dict[str, Any]]:
    """Labeled nodes for app_hint/a11y — same y cutoff as cluster path (min y=80)."""
    nodes: list[dict[str, Any]] = []
    for m in _NODE_OPEN_RE.finditer(raw or ""):
        attrs = _parse_attrs(m.group(1))
        label = _node_label(attrs)
        bounds = _parse_bounds(attrs)
        if not label or not bounds or is_button_label(label):
            continue
        x1, y1, x2, y2 = bounds
        if y1 < 80 or (y2 - y1) < 8:
            continue
        nodes.append({"label": label, "bounds": [x1, y1, x2, y2]})
    nodes.sort(key=lambda n: (n["bounds"][1], n["bounds"][0]))
    return nodes


def _merge_bounds(nodes: list[dict[str, Any]]) -> list[int]:
    xs1 = [int(n["bounds"][0]) for n in nodes]
    ys1 = [int(n["bounds"][1]) for n in nodes]
    xs2 = [int(n["bounds"][2]) for n in nodes]
    ys2 = [int(n["bounds"][3]) for n in nodes]
    return [min(xs1), min(ys1), max(xs2), max(ys2)]


def _pick_body_for_title(nodes: list[dict[str, Any]], title_node: dict[str, Any], title: str) -> str:
    y2 = int(title_node["bounds"][3])
    candidates: list[tuple[int, str]] = []
    for n in nodes:
        lab = str(n.get("label") or "").strip()
        if not lab or lab.lower() == title.lower():
            continue
        ny1 = int(n["bounds"][1])
        if ny1 < y2 - 8 or ny1 > y2 + 220:
            continue
        if is_button_label(lab) or _BODY_SKIP_RE.search(lab):
            continue
        low = lab.lower()
        if low in _QS_TILE_MARKERS_LOWER or low in _UI_CHROME_LOWER:
            continue
        if lab.lower().startswith("notificación de"):
            continue
        candidates.append((ny1, lab))
    candidates.sort(key=lambda item: item[0])
    if not candidates:
        return ""
    return max(candidates, key=lambda item: len(item[1]))[1]


def _make_notification_row(
    *,
    title: str,
    body: str,
    bounds: list[int],
    source: str,
) -> dict[str, Any]:
    x1, y1, x2, y2 = bounds
    cy = (y1 + y2) // 2
    skip = row_should_skip(title, body)
    row: dict[str, Any] = {
        "title": title,
        "body": body,
        "bounds": [x1, y1, x2, y2],
        "cy": cy,
        "action": "SKIP" if skip else "DISMISS",
        "source": source,
    }
    if not skip:
        row["swipe"] = {"x1": 980, "y1": cy, "x2": 80, "y2": cy, "duration_ms": 450}
    return row


def _merge_into_cluster(cluster: dict[str, Any], node: dict[str, Any]) -> None:
    labels = cluster.setdefault("labels", [])
    if node["label"] not in labels:
        labels.append(node["label"])
    b = cluster["bounds"]
    nb = node["bounds"]
    cluster["bounds"] = [
        min(b[0], nb[0]),
        min(b[1], nb[1]),
        max(b[2], nb[2]),
        max(b[3], nb[3]),
    ]


def _cluster_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group text nodes into notification rows by Y proximity."""
    clusters: list[dict[str, Any]] = []
    for node in nodes:
        y1 = int(node["bounds"][1])
        y2 = int(node["bounds"][3])
        placed = False
        for cluster in clusters:
            anchor = int(cluster["anchor_y"])
            if abs(y1 - anchor) > _CLUSTER_Y_GAP:
                continue
            prospective_y2 = max(int(cluster["bounds"][3]), y2)
            if prospective_y2 - anchor > _MAX_ROW_HEIGHT:
                continue
            _merge_into_cluster(cluster, node)
            placed = True
            break
        if not placed:
            clusters.append(
                {"labels": [node["label"]], "bounds": list(node["bounds"]), "anchor_y": y1}
            )
    return clusters


def extract_notification_rows(
    raw: str, *, min_width: int = _MIN_ROW_WIDTH, min_height: int = 40
) -> list[dict[str, Any]]:
    """Cluster labeled nodes into full-width notification rows."""
    rows: list[dict[str, Any]] = []
    for cluster in _cluster_nodes(_collect_labeled_nodes(raw)):
        labels = sorted(set(cluster.get("labels") or []), key=len)
        if not labels:
            continue
        x1, y1, x2, y2 = cluster["bounds"]
        width = x2 - x1
        height = y2 - y1
        if width < min_width or height < min_height:
            continue
        title = labels[0]
        body = labels[-1] if len(labels) > 1 and labels[-1] != title else ""
        if is_button_label(title):
            continue
        cy = (y1 + y2) // 2
        skip = row_should_skip(title, body)
        row: dict[str, Any] = {
            "title": title,
            "body": body,
            "bounds": [x1, y1, x2, y2],
            "cy": cy,
            "action": "SKIP" if skip else "DISMISS",
        }
        if not skip:
            row["swipe"] = {"x1": 980, "y1": cy, "x2": 80, "y2": cy, "duration_ms": 450}
        rows.append(row)
    rows.sort(key=lambda r: int(r["bounds"][1]))
    return rows


def extract_a11y_notification_rows(raw: str) -> list[dict[str, Any]]:
    """Parse content-desc patterns; attach real bounds from the same XML node."""
    nodes = _hint_nodes(raw)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for n in nodes:
        label = str(n.get("label") or "").strip()
        title = body = ""
        m_de = _NOTIF_DE_RE.match(label)
        if m_de:
            title = m_de.group(1).strip()
            body = m_de.group(2).strip()
        else:
            m_tiene = _TIENE_NOTIF_RE.match(label)
            if m_tiene:
                title = m_tiene.group(1).strip()
            else:
                continue
        key = title.lower()
        if not title or key in seen or is_button_label(title):
            continue
        seen.add(key)
        if not body:
            body = _pick_body_for_title(nodes, n, title)
        row_nodes = [
            n2
            for n2 in nodes
            if abs(int(n2["bounds"][1]) - int(n["bounds"][1])) <= _CLUSTER_Y_GAP + 40
        ]
        bounds = _merge_bounds(row_nodes) if row_nodes else n["bounds"]
        rows.append(_make_notification_row(title=title, body=body, bounds=bounds, source="content-desc"))
    return rows


def extract_app_hint_rows(raw: str) -> list[dict[str, Any]]:
    """Known app titles as text= nodes with real bounds + neighbor body text."""
    nodes = _hint_nodes(raw)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for app in _KNOWN_APP_NAMES:
        app_low = app.lower()
        if app_low in seen:
            continue
        title_node: dict[str, Any] | None = None
        for n in nodes:
            lab = str(n.get("label") or "").strip()
            lab_low = lab.lower()
            if lab_low == app_low or lab_low.startswith(f"{app_low} "):
                title_node = n
                break
        if not title_node:
            continue
        body = _pick_body_for_title(nodes, title_node, app)
        anchor_y = int(title_node["bounds"][1])
        anchor_y2 = int(title_node["bounds"][3])
        row_nodes = [
            n2
            for n2 in nodes
            if int(n2["bounds"][1]) >= anchor_y - 10 and int(n2["bounds"][3]) <= anchor_y2 + 80
        ]
        bounds = _merge_bounds(row_nodes) if row_nodes else title_node["bounds"]
        rows.append(_make_notification_row(title=app, body=body, bounds=bounds, source="app_hint"))
        seen.add(app_low)
    if "afterhour" not in seen:
        for n in nodes:
            lab = str(n.get("label") or "").strip()
            if lab.lower() not in {"geo21208", "spx"} and "geo21208" not in lab.lower():
                continue
            anchor_y = int(n["bounds"][1])
            row_nodes = [
                n2
                for n2 in nodes
                if abs(int(n2["bounds"][1]) - anchor_y) <= _MAX_ROW_HEIGHT
            ]
            body = lab if lab.lower() != "spx" else _pick_body_for_title(nodes, n, "AfterHour")
            if lab.lower() == "spx":
                for n2 in row_nodes:
                    if "geo" in n2["label"].lower() or len(n2["label"]) >= 6:
                        body = n2["label"]
                        break
            bounds = _merge_bounds(row_nodes) if row_nodes else n["bounds"]
            rows.append(
                _make_notification_row(title="AfterHour", body=body or lab, bounds=bounds, source="app_hint")
            )
            seen.add("afterhour")
            break
    return rows


def _extract_fallback_texts(raw: str, *, min_len: int = 4) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for node in _collect_labeled_nodes(raw):
        label = str(node.get("label") or "").strip()
        if len(label) < min_len or label in seen:
            continue
        seen.add(label)
        out.append(label)
    if out:
        return out[:25]
    for m in re.finditer(rf'(?:text|content-desc)="([^"]{{{min_len},120}})"', raw):
        label = m.group(1).strip()
        if is_button_label(label):
            continue
        low = label.lower()
        if low in _UI_CHROME_LOWER or low in _QS_TILE_MARKERS_LOWER:
            continue
        if label not in seen:
            seen.add(label)
            out.append(label)
    return out[:25]


def _dump_shows_quick_settings_only(raw: str) -> bool:
    if _APP_NAME_IN_DUMP_RE.search(raw or ""):
        return False
    low = raw.lower()
    if "notificación de" in low or "notificacion de" in low:
        return False
    if _TIENE_NOTIF_RE.search(raw or ""):
        return False
    if "geo21208" in low:
        return False
    return sum(1 for m in _QS_TILE_MARKERS_LOWER if m in low) >= 2


def extract_notification_titles(raw: str) -> list[str]:
    return [str(r["title"]) for r in extract_notification_rows(raw)]


def analyze_notification_ui_dump(raw: str) -> dict[str, Any]:
    text = raw or ""
    parser_mode = "full_width"
    # Pass 1: Moto shade — known apps with real bounds (before noisy narrow clusters).
    hint_rows = extract_app_hint_rows(text)
    hint_dismiss = [r for r in hint_rows if r.get("action") == "DISMISS"]
    if hint_dismiss:
        rows = hint_rows
        parser_mode = "app_hint"
    else:
        rows = extract_notification_rows(text)
        dismiss_rows = [r for r in rows if r.get("action") == "DISMISS"]
        if not dismiss_rows:
            low = text.lower()
            has_app_signals = bool(
                _APP_NAME_IN_DUMP_RE.search(text)
                or _TIENE_NOTIF_RE.search(text)
                or "geo21208" in low
                or "notificación de" in low
                or "notificacion de" in low
            )
            if has_app_signals:
                for min_w, mode in ((400, "relaxed_width"), (200, "narrow_width")):
                    if len(text) < 3000 and min_w < 400:
                        continue
                    min_h = 12 if min_w <= 200 else 24
                    candidate = extract_notification_rows(text, min_width=min_w, min_height=min_h)
                    candidate = [
                        r for r in candidate if not _is_junk_notification_title(str(r.get("title") or ""))
                    ]
                    cand_dismiss = [r for r in candidate if r.get("action") == "DISMISS"]
                    if not cand_dismiss:
                        continue
                    # Prefer app_hint over content-desc "Notificación de X:" false clusters.
                    if _APP_NAME_IN_DUMP_RE.search(text):
                        retry = extract_app_hint_rows(text)
                        retry_dismiss = [r for r in retry if r.get("action") == "DISMISS"]
                        if retry_dismiss:
                            rows = retry
                            parser_mode = "app_hint"
                            dismiss_rows = retry_dismiss
                            break
                    rows = candidate
                    parser_mode = mode
                    dismiss_rows = cand_dismiss
                    break
        if not dismiss_rows:
            a11y_rows = extract_a11y_notification_rows(text)
            if a11y_rows:
                rows = a11y_rows
                parser_mode = "content_desc"
                dismiss_rows = [r for r in rows if r.get("action") == "DISMISS"]
        if not dismiss_rows and hint_rows:
            rows = hint_rows
            parser_mode = "app_hint"
    # Merge any missing known apps.
    have_titles = {str(r.get("title") or "").lower() for r in rows}
    for hr in extract_app_hint_rows(text):
        t = str(hr.get("title") or "").lower()
        if not t or t in have_titles:
            continue
        rows.append(hr)
        have_titles.add(t)
    if any(r.get("source") == "app_hint" for r in rows):
        parser_mode = "app_hint"
    rows.sort(key=lambda r: int((r.get("bounds") or [0, 0, 0, 0])[1]))
    dismiss_rows = [r for r in rows if r.get("action") == "DISMISS"]
    fallback_texts = _extract_fallback_texts(text) if not dismiss_rows and len(text) > 2000 else []
    skip = [str(r["title"]) for r in rows if r["action"] == "SKIP"]
    dismissible = [str(r["title"]) for r in rows if r["action"] == "DISMISS"]
    dismiss_actions = [r for r in rows if r["action"] == "DISMISS"]
    qs_only = _dump_shows_quick_settings_only(text) and not dismiss_actions
    if qs_only:
        panel_state = "quick_settings_only"
    elif dismiss_actions or rows:
        panel_state = "expanded"
    elif len(text) > 8000:
        panel_state = "collapsed_or_unparsed"
    else:
        panel_state = "unknown"
    digest = [
        {
            "title": r.get("title"),
            "body": r.get("body") or "",
            "action": r.get("action"),
            **({"swipe": r["swipe"]} if r.get("swipe") else {}),
        }
        for r in rows
    ]
    workflow = [
        "1. Lee digest — escribe insight en el MENSAJE FINAL (bullets: app + resumen body).",
        "2. UN swipe horizontal por turno (solo filas DISMISS).",
        "3. SKIP = no swipe. Verifica con get_ui_dump tras cada dismiss.",
    ]
    if qs_only or panel_state == "collapsed_or_unparsed":
        workflow = [
            "1. Despertar pantalla si está apagada.",
            "2. android_expand_notifications → get_ui_dump (lee digest ANTES de scroll).",
            "3. Si digest vacío: UN swipe vertical x1=540,y1=1200,x2=540,y2=400 → get_ui_dump.",
            "4. UN swipe horizontal por turno usando EXACTAMENTE digest[].swipe.",
            "5. get_ui_dump tras cada dismiss.",
        ]
    result = {
        "panel_state": panel_state,
        "panel_open_hint": len(text) > 15000,
        "parser_mode": parser_mode,
        "digest": digest,
        "fallback_texts": fallback_texts,
        "rows": rows,
        "skip_non_dismissible": skip,
        "dismissible": dismissible,
        "dismiss_actions": dismiss_actions,
        "max_swipe_attempts_per_row": 1,
        "one_swipe_per_turn": True,
        "workflow": workflow,
        "final_message_must_include": (
            "Bullets con cada notificación DISMISS leída: '- {title}: {body}' y cuáles quedaron SKIP."
        ),
        "after_read": (
            "El insight va en la respuesta de texto al usuario, no solo en tool calls. "
            "Prohibido encadenar 3+ swipe_screen en un solo turno."
        ),
        "rule": (
            "No afirmar '0 notificaciones' hasta completar expand + get_ui_dump. "
            "SKIP = no swipe. DISMISS = swipe horizontal una vez con coords exactas del digest. "
            "Nunca swipe en filas con title 'Hace …', 'Expandir', 'El Tiempo' (son chrome, no apps)."
        ),
    }
    if qs_only:
        result["parse_note"] = (
            "Solo Quick Settings visible (Datos móviles, Bluetooth, etc.). "
            "Notificaciones de apps probablemente debajo — expand + scroll antes de concluir vacío."
        )
    elif panel_state == "collapsed_or_unparsed" and not dismiss_actions:
        result["parse_note"] = (
            "Dump grande sin filas dismissibles parseadas. "
            "Expande el panel y haz scroll vertical en la lista de notificaciones."
        )
    return result


def classify_swipe_result(result: str) -> dict[str, Any]:
    m = re.search(
        r"Swiped from \((\d+),\s*(\d+)\) to \((\d+),\s*(\d+)\)",
        result or "",
        re.I,
    )
    if not m:
        return {"parsed": False}
    x1, y1, x2, y2 = (int(m.group(i)) for i in range(1, 5))
    vertical = abs(x1 - x2) <= 80
    horizontal = abs(y1 - y2) <= 80
    return {
        "parsed": True,
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
        "vertical": vertical,
        "horizontal": horizontal,
        "kind": "vertical" if vertical else ("horizontal" if horizontal else "diagonal"),
    }


def _compact_xml_tail(raw: str, *, max_chars: int = 1200) -> str:
    if len(raw) <= max_chars:
        return raw
    return (
        f"<!-- ui_dump XML compactado ({len(raw)} chars). Usa digest del plan para leer/dismiss -->\n"
        f"{raw[:max_chars]}\n... [truncado]"
    )


def append_notification_hints_to_ui_dump(raw: str) -> str:
    text = raw or ""
    hints = analyze_notification_ui_dump(text)
    rows = hints.get("rows") or []
    fallback = hints.get("fallback_texts") or []
    panel_state = hints.get("panel_state") or "unknown"
    force_plan = len(text) > 8000 and panel_state in {
        "quick_settings_only",
        "collapsed_or_unparsed",
        "unknown",
    }
    if not rows and not fallback and not force_plan:
        return text
    if not rows and fallback:
        hint_rows = extract_app_hint_rows(text)
        hint_dismiss = [r for r in hint_rows if r.get("action") == "DISMISS"]
        if hint_dismiss:
            hints["rows"] = hint_rows
            hints["parser_mode"] = "app_hint"
            hints["panel_state"] = "expanded"
            hints["dismissible"] = [str(r["title"]) for r in hint_dismiss]
            hints["dismiss_actions"] = hint_dismiss
            hints["digest"] = [
                {
                    "title": r.get("title"),
                    "body": r.get("body") or "",
                    "action": r.get("action"),
                    **({"swipe": r["swipe"]} if r.get("swipe") else {}),
                }
                for r in hint_rows
            ]
            hints["workflow"] = [
                "1. Lee digest — bullets con title + body para el usuario.",
                "2. UN swipe horizontal por turno usando EXACTAMENTE digest[].swipe (y1 real).",
                "3. get_ui_dump tras cada dismiss para verificar.",
            ]
            hints["rule"] = (
                "OBLIGATORIO: copiar x1/y1/x2/y2 de digest[].swipe al llamar swipe_screen. "
                "No inventar coordenadas."
            )
        else:
            hints["digest"] = [{"title": t, "body": "", "action": "READ_ONLY"} for t in fallback]
            hints["workflow"] = [
                "1. Resume fallback_texts en bullets para el usuario.",
                "2. android_expand_notifications + get_ui_dump de nuevo si faltan coords dismiss.",
            ]
    block = json.dumps(hints, ensure_ascii=False)
    plan = f"[DUCKCLAW_NOTIFICATION_PLAN]\n{block}\n[/DUCKCLAW_NOTIFICATION_PLAN]"
    if rows or fallback or force_plan:
        return plan
    return plan + "\n\n" + _compact_xml_tail(text)
