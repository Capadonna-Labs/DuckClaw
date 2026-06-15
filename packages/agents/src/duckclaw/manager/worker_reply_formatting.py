"""Worker reply formatting helpers for manager invocations."""

from __future__ import annotations

import re


# Lineas tipo "worker 2", "Job-Hunter 1" al inicio del cuerpo (eco de heartbeats / historial).
# El numero es subagent_slot_rank (Redis), no replica PM2; ver subagent_run_id.
_SUBAGENT_INSTANCE_HEADER_LINE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*\s+\d+\s*$")


def _strip_leading_subagent_instance_headers(text: str) -> str:
    """
    Elimina una o mas lineas iniciales ``<worker_id> <n>`` que el modelo repite tras ver
    DMs de delegacion o turnos anteriores. Deja intacto el resto del mensaje.
    """
    t = (text or "").strip()
    while t:
        lines = t.splitlines()
        if not lines:
            break
        if not _SUBAGENT_INSTANCE_HEADER_LINE.match(lines[0].strip()):
            break
        t = "\n".join(lines[1:]).strip()
    return t


_CAVEMAN_WORKER_HEADER_RE = re.compile(
    r"(?:^\s*\*\*(?P<b>[A-Za-z0-9][A-Za-z0-9_.-]*)\s+\d+[^*]*\*\*"
    r"|^\s*(?P<p>[A-Za-z0-9][A-Za-z0-9_.-]*)\s+\d+(?:\s+·|\s*$))",
    re.MULTILINE | re.IGNORECASE,
)


def _worker_base_from_subagent_label(label: str) -> str:
    """``Worker-A 4`` -> ``Worker-A``; ids sin slot quedan igual."""
    clean = (label or "").strip()
    if not clean:
        return ""
    parts = clean.rsplit(" ", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0].strip()
    return clean


def _reply_already_has_worker_header(reply: str, worker_base: str) -> bool:
    """
    True si el worker ya firmo la respuesta (Caveman ``**Worker N ... COT**``,
    linea plana ``Worker N``, o etiqueta de subagente al inicio).
    """
    base = (worker_base or "").strip()
    if not base:
        return False
    text = (reply or "").strip()
    if not text:
        return False
    esc = re.escape(base)
    if re.search(rf"(?m)^\s*\*\*{esc}\s+\d+[^*]*\*\*", text, re.IGNORECASE):
        return True
    if re.search(rf"(?m)^\s*\*\*{esc}[^*]*\bCOT\b[^*]*\*\*", text, re.IGNORECASE):
        return True
    if re.search(rf"(?m)^\s*{esc}\s+\d+\b", text, re.IGNORECASE):
        return True
    if re.search(rf"(?m)^\s*{esc}\s*·[^\n]*\bCOT\b", text, re.IGNORECASE):
        return True
    for match in _CAVEMAN_WORKER_HEADER_RE.finditer(text):
        found = (match.group("b") or match.group("p") or "").strip()
        if found.lower() == base.lower():
            return True
    return False


def _prepend_subagent_label_once(reply: str, label: str) -> str:
    """
    Anade el encabezado del subagente solo si el texto aun no lo trae al inicio.
    Evita respuestas con doble prefijo como:
    `worker 1` + `worker 1` o Caveman + etiqueta manager.
    """
    clean_reply = _strip_leading_subagent_instance_headers(reply or "")
    clean_label = (label or "").strip()
    if not clean_label or not clean_reply:
        return clean_reply
    worker_base = _worker_base_from_subagent_label(clean_label)
    if _reply_already_has_worker_header(clean_reply, worker_base):
        return clean_reply
    # Tolerar un prefijo markdown basico (`**label**`) ademas del plano.
    if clean_reply.startswith(clean_label):
        return clean_reply
    if clean_reply.startswith(f"**{clean_label}**"):
        return clean_reply
    return f"{clean_label}\n\n{clean_reply}"


__all__ = [
    "_prepend_subagent_label_once",
    "_reply_already_has_worker_header",
    "_strip_leading_subagent_instance_headers",
    "_worker_base_from_subagent_label",
]
