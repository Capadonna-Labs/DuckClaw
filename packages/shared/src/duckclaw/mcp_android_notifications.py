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
    }
)

_NODE_OPEN_RE = re.compile(r"<node\b([^>/]*)(?:/>|>)")


def is_android_ui_dump_tool(tool_name: str) -> bool:
    return (tool_name or "").strip().lower().endswith(_UI_DUMP_TOOL_SUFFIX)


def is_android_swipe_tool(tool_name: str) -> bool:
    return (tool_name or "").strip().lower().endswith("__swipe_screen")


def is_non_dismissible_notification_title(title: str) -> bool:
    t = (title or "").strip()
    if not t:
        return False
    return any(p.search(t) for p in _NON_DISMISSIBLE_TITLE_RES)


def row_should_skip(title: str, body: str = "") -> bool:
    if is_non_dismissible_notification_title(title):
        return True
    if is_non_dismissible_notification_title(body):
        return True
    merged = f"{title} {body}".lower()
    if "sistema android" in merged:
        return True
    if "tarjeta sim" in merged:
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


def extract_notification_rows(raw: str, *, min_width: int = _MIN_ROW_WIDTH) -> list[dict[str, Any]]:
    """Cluster labeled nodes into full-width notification rows."""
    rows: list[dict[str, Any]] = []
    for cluster in _cluster_nodes(_collect_labeled_nodes(raw)):
        labels = sorted(set(cluster.get("labels") or []), key=len)
        if not labels:
            continue
        x1, y1, x2, y2 = cluster["bounds"]
        width = x2 - x1
        height = y2 - y1
        if width < min_width or height < 40:
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


def _extract_fallback_texts(raw: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for node in _collect_labeled_nodes(raw):
        label = str(node.get("label") or "").strip()
        if len(label) < 8 or label in seen:
            continue
        seen.add(label)
        out.append(label)
    return out[:25]


def extract_notification_titles(raw: str) -> list[str]:
    return [str(r["title"]) for r in extract_notification_rows(raw)]


def analyze_notification_ui_dump(raw: str) -> dict[str, Any]:
    text = raw or ""
    rows = extract_notification_rows(text)
    parser_mode = "full_width"
    if not rows and len(text) > 15000:
        rows = extract_notification_rows(text, min_width=400)
        parser_mode = "relaxed_width"
    fallback_texts = _extract_fallback_texts(text) if not rows and len(text) > 8000 else []
    skip = [str(r["title"]) for r in rows if r["action"] == "SKIP"]
    dismissible = [str(r["title"]) for r in rows if r["action"] == "DISMISS"]
    dismiss_actions = [r for r in rows if r["action"] == "DISMISS"]
    digest = [
        {
            "title": r.get("title"),
            "body": r.get("body") or "",
            "action": r.get("action"),
            **({"swipe": r["swipe"]} if r.get("swipe") else {}),
        }
        for r in rows
    ]
    return {
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
        "workflow": [
            "1. Lee digest — escribe insight en el MENSAJE FINAL (bullets: app + resumen body).",
            "2. UN swipe horizontal por turno (solo filas DISMISS).",
            "3. SKIP = no swipe. Verifica con get_ui_dump tras cada dismiss.",
        ],
        "final_message_must_include": (
            "Bullets con cada notificación DISMISS leída: '- {title}: {body}' y cuáles quedaron SKIP."
        ),
        "after_read": (
            "El insight va en la respuesta de texto al usuario, no solo en tool calls. "
            "Prohibido encadenar 3+ swipe_screen en un solo turno."
        ),
        "rule": (
            "SKIP = no swipe. DISMISS = swipe horizontal una vez. "
            "Prohibido swipe vertical para descartar."
        ),
    }


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
    if not rows and not fallback:
        return text
    if not rows and fallback:
        hints["digest"] = [{"title": t, "body": "", "action": "READ_ONLY"} for t in fallback]
        hints["workflow"] = [
            "1. Resume fallback_texts en bullets para el usuario.",
            "2. android_expand_notifications + get_ui_dump de nuevo si faltan coords dismiss.",
        ]
    block = json.dumps(hints, ensure_ascii=False)
    plan = f"[DUCKCLAW_NOTIFICATION_PLAN]\n{block}\n[/DUCKCLAW_NOTIFICATION_PLAN]"
    if rows or fallback:
        return plan
    return plan + "\n\n" + _compact_xml_tail(text)
