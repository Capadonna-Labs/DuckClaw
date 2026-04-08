#!/usr/bin/env python3
"""
Sanitiza trazas ChatML (conversation_traces) para SFT Gemma 4 / mlx_lm.lora.

Spec: specs/features/SFT Trace Sanitizer Gemma 4.md
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

_LOG = logging.getLogger(__name__)

_REDACTED_THINKING = re.compile(
    r"<redacted_thinking>.*?</redacted_thinking>",
    re.DOTALL | re.IGNORECASE,
)
# Palabras clave seguidas de números o símbolos de moneda con dígitos.
# Evita dispararse con "No tengo precios" o "Hablemos de la Temperatura" sin valor.
EVIDENCE_PATTERN = (
    r"(?i)(?:(?:\$|COP|USD)\s?\d+(?:[.,]\d+)?|"
    r"Temperatura:\s?\d+|Densidad:\s*\d+|Masa:\s*\d+)"
)
_EVIDENCE_RE = re.compile(EVIDENCE_PATTERN)


def needs_evidence(content: str) -> bool:
    """True si el texto reporta cifras concretas que deben ir respaldadas por tool."""
    if not (content or "").strip():
        return False
    low = content.lower()
    negatives = (
        "no puedo",
        "no tengo acceso",
        "no soy",
        "estamos preparando",
        "confirmamos cuando",
    )
    if any(neg in low for neg in negatives):
        return False
    return bool(_EVIDENCE_RE.search(content))


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in [p.parent, *p.parents]:
        if (parent / "pyproject.toml").is_file():
            return parent
    return Path(__file__).resolve().parents[1]


def clean_content(text: str) -> str:
    """Elimina bloques CoT tipo DeepSeek R1 y compacta espacios."""
    if not text:
        return ""
    s = _REDACTED_THINKING.sub("", text)
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _message_text(msg: dict[str, Any]) -> str:
    c = msg.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts: list[str] = []
        for block in c:
            if isinstance(block, dict):
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    parts.append(block["text"])
                elif isinstance(block.get("text"), str):
                    parts.append(block["text"])
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(c or "")


def tool_content_indicates_success(content: str) -> bool:
    """True si el ToolMessage parece resultado OK (DuckClaw / JSON)."""
    raw = (content or "").strip()
    if not raw:
        return False
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        # Texto plano (p. ej. IBKR formateado): sin JSON de error estándar
        low = raw.lower()
        if '"error"' in raw or "'error'" in raw:
            return False
        if "error" in low and ("traceback" in low or "failed" in low):
            return False
        return len(raw) > 0

    if isinstance(data, list):
        return True
    if not isinstance(data, dict):
        return True

    if data.get("error") is not None and data.get("error") != "":
        err = data.get("error")
        if isinstance(err, str) and err.strip():
            return False

    if "exit_code" in data:
        try:
            return int(data.get("exit_code")) == 0
        except (TypeError, ValueError):
            return False

    st = data.get("status")
    if st is not None and str(st).lower() not in ("ok", "success", "200"):
        if str(st).lower() in ("error", "failed"):
            return False

    return True


def _last_user_content_before(messages: list[dict[str, Any]], assistant_index: int) -> str:
    for j in range(assistant_index - 1, -1, -1):
        if (messages[j].get("role") or "").lower() == "user":
            return clean_content(_message_text(messages[j]))
    return ""


def validate_evidence_turn(
    user_message: str,
    assistant_message: str,
    prev_was_tool: bool,
) -> bool:
    """
    Validación por turno (regla user / assistant / prev_was_tool).
    Estado operativo → fuentes no-SQL → usuario/directivas → simetría → EVIDENCE_PATTERN.
    """
    assistant_low = assistant_message.lower()
    user_low = user_message.lower()

    operational_keywords = (
        "error",
        "bloqueo",
        "vacía",
        "0 vacantes",
        "no hay",
        "no pude",
        "no tengo",
        "pid",
        "tablas",
        "esquemas",
        "columna",
        "binder error",
        "ceguera sensorial",
        "sin datos",
        "fuera de alcance",
        "indeterminada",
        "no se encontraron",
        "no hay registros",
        "módulo no disponible",
        "ingesta exitosa",
        "ingesta completada",
        "datos descargados",
        "confirmada en base",
        "registrada correctamente",
        "actualizado en vivo",
        "comandos disponibles",
        "pasos a seguir",
        "verificación",
    )
    if any(k in assistant_low for k in operational_keywords):
        return True

    source_indicators = (
        "osint",
        "visual",
        "imagen",
        "tavily",
        "búsqueda",
        "titular",
        "bloomberg",
        "noticia",
        "msci",
        "revisé",
        "analiza",
        "resume",
        "según",
        "reportado",
        "observado",
        "insights",
        "reddit",
        "hilo",
    )
    if any(k in assistant_low for k in source_indicators):
        return True

    if any(
        k in user_low
        for k in (
            "http",
            "www.",
            "analiza",
            "resume",
            "tavily",
            "reddit",
            "msci",
        )
    ):
        return True
    um = user_message.upper()
    if (
        "SUMMARIZE" in um
        or "CONTEXT_RESTORE" in um
        or "TAREA:" in um
    ):
        return True

    user_numbers = set(
        re.findall(
            r"\d{3,}",
            user_message.replace(".", "").replace(",", ""),
        )
    )
    asst_numbers = set(
        re.findall(
            r"\d{3,}",
            assistant_message.replace(".", "").replace(",", ""),
        )
    )
    if asst_numbers and asst_numbers.issubset(user_numbers):
        return True

    if re.search(EVIDENCE_PATTERN, assistant_message):
        if not prev_was_tool:
            return False

    return True


def validate_evidence_rule(messages: list[dict[str, Any]]) -> tuple[bool, str | None]:
    """
    Aplica validate_evidence_turn a cada mensaje assistant (texto ya coherente con clean_content).
    """
    if not messages:
        return False, "empty_messages"

    for i, msg in enumerate(messages):
        role = (msg.get("role") or "").lower()
        if role != "assistant":
            continue
        text = clean_content(_message_text(msg))
        if not text.strip():
            continue

        user_before = _last_user_content_before(messages, i)
        prev_was_tool = False
        if i > 0:
            prev = messages[i - 1]
            pr = (prev.get("role") or "").lower()
            if pr == "tool":
                prev_was_tool = tool_content_indicates_success(_message_text(prev))

        if validate_evidence_turn(user_before, text, prev_was_tool):
            continue

        if i == 0:
            return False, "evidence_trigger_at_first_message"

        pr_prev = (messages[i - 1].get("role") or "").lower()
        if pr_prev == "tool":
            tb = _message_text(messages[i - 1])
            if not tool_content_indicates_success(tb):
                return False, "preceding_tool_not_success"

        return False, f"evidence_requires_tool_prev_got_{pr_prev}"

    return True, None


def _assistant_preview_for_evidence_log(messages: list[dict[str, Any]], max_len: int = 150) -> str:
    """Último assistant con texto no vacío (tras clean_content), truncado para logs."""
    for m in reversed(messages):
        if (m.get("role") or "").lower() != "assistant":
            continue
        t = clean_content(_message_text(m))
        if t:
            return t if len(t) <= max_len else t[:max_len] + "..."
    return ""


def _tool_calls_to_xml(tool_calls: Any) -> str:
    if not tool_calls:
        return ""
    chunks: list[str] = []
    for tc in tool_calls:
        name: str | None = None
        arguments: Any = None
        if isinstance(tc, dict):
            if "function" in tc and isinstance(tc["function"], dict):
                fn = tc["function"]
                name = (fn.get("name") or "").strip() or None
                arguments = fn.get("arguments")
            else:
                name = (tc.get("name") or "").strip() or None
                arguments = tc.get("arguments")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                pass
        payload = json.dumps({"name": name or "", "arguments": arguments}, ensure_ascii=False)
        chunks.append(f"<tool_call>\n{payload}\n</tool_call>")
    return "\n".join(chunks).strip()


def apply_gemma_template(messages: list[dict[str, Any]]) -> str:
    """
    ChatML -> un solo string con turnos Gemma (user/model).
    System se fusiona al primer turno user.
    """
    system_text = ""
    rest: list[dict[str, Any]] = []
    for m in messages:
        r = (m.get("role") or "").lower()
        if r == "system":
            system_text = clean_content(_message_text(m))
        else:
            rest.append(m)

    parts: list[str] = []
    first_user = True

    for m in rest:
        r = (m.get("role") or "").lower()
        if r == "user":
            body = clean_content(_message_text(m))
            if first_user:
                if system_text:
                    body = f"{system_text}\n\n{body}".strip()
                first_user = False
            parts.append(f"<start_of_turn>user\n{body}<end_of_turn>")
        elif r == "assistant":
            tc_xml = _tool_calls_to_xml(m.get("tool_calls"))
            content = clean_content(_message_text(m))
            if tc_xml and content:
                model_body = f"{tc_xml}\n\n{content}".strip()
            elif tc_xml:
                model_body = tc_xml
            else:
                model_body = content
            parts.append(f"<start_of_turn>model\n{model_body}<end_of_turn>")
        elif r == "tool":
            name = (m.get("name") or "tool").strip()
            body = clean_content(_message_text(m))
            wrapped = f"[Tool {name} result]\n{body}"
            parts.append(f"<start_of_turn>user\n{wrapped}<end_of_turn>")
        else:
            _LOG.debug("skip role %s", r)

    return "\n".join(parts)


class SftGemmaRow(BaseModel):
    text: str = Field(..., min_length=1)
    session_id: str | None = None
    timestamp: str | None = None
    status: str | None = None
    worker_id: str | None = None


class GemmaSanitizer:
    def __init__(
        self,
        *,
        input_root: Path,
        output_root: Path,
        input_glob: str = "**/traces.jsonl",
    ) -> None:
        self.input_root = input_root.resolve()
        self.output_root = output_root.resolve()
        self.input_glob = input_glob

    def iter_input_files(self) -> list[Path]:
        if not self.input_root.is_dir():
            _LOG.warning("input_root does not exist: %s", self.input_root)
            return []
        return sorted(self.input_root.glob(self.input_glob))

    def output_path_for(self, input_file: Path) -> Path:
        try:
            rel = input_file.resolve().relative_to(self.input_root)
        except ValueError:
            rel = Path(input_file.name)
        return self.output_root / rel

    def load_trace_line(self, line: str) -> dict[str, Any] | None:
        line = line.strip()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            _LOG.warning("skip invalid json line")
            return None

    def validate_evidence_rule(self, messages: list[dict[str, Any]]) -> tuple[bool, str | None]:
        return validate_evidence_rule(messages)

    def apply_gemma_template(self, messages: list[dict[str, Any]]) -> str:
        return apply_gemma_template(messages)

    def export_dataset(
        self,
        *,
        dry_run: bool = False,
    ) -> dict[str, int]:
        stats = {
            "files_seen": 0,
            "lines_read": 0,
            "lines_kept": 0,
            "lines_dropped_evidence": 0,
            "lines_dropped_other": 0,
        }
        for fp in self.iter_input_files():
            stats["files_seen"] += 1
            out_path = self.output_path_for(fp)
            out_lines: list[str] = []

            try:
                text = fp.read_text(encoding="utf-8")
            except OSError as e:
                _LOG.error("read failed %s: %s", fp, e)
                continue

            for line in text.splitlines():
                stats["lines_read"] += 1
                rec = self.load_trace_line(line)
                if rec is None:
                    stats["lines_dropped_other"] += 1
                    continue
                messages = rec.get("messages")
                if not isinstance(messages, list) or not messages:
                    stats["lines_dropped_other"] += 1
                    continue

                ok, reason = self.validate_evidence_rule(messages)
                if not ok:
                    stats["lines_dropped_evidence"] += 1
                    preview = _assistant_preview_for_evidence_log(messages)
                    _LOG.info(
                        "🔍 RECHAZADO POR EVIDENCIA: %s | reason=%s | session_id=%s | file=%s",
                        preview or "(sin texto assistant)",
                        reason,
                        rec.get("session_id"),
                        fp,
                    )
                    continue

                gemma_text = self.apply_gemma_template(messages)
                if not gemma_text.strip():
                    stats["lines_dropped_other"] += 1
                    continue

                row_data: dict[str, Any] = {"text": gemma_text}
                for key in ("session_id", "timestamp", "status", "worker_id"):
                    v = rec.get(key)
                    if v is not None and v != "":
                        row_data[key] = v
                row = SftGemmaRow(**row_data)
                out_obj = row.model_dump(exclude_none=True)

                out_lines.append(json.dumps(out_obj, ensure_ascii=False))
                stats["lines_kept"] += 1

            if out_lines and not dry_run:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
                _LOG.info("wrote %s (%s lines)", out_path, len(out_lines))
            elif out_lines and dry_run:
                _LOG.info("dry-run would write %s (%s lines)", out_path, len(out_lines))

        total_dropped = stats["lines_dropped_evidence"] + stats["lines_dropped_other"]
        if stats["lines_read"] > 0:
            drop_rate = total_dropped / stats["lines_read"]
            _LOG.info(
                "summary: read=%s kept=%s dropped_evidence=%s dropped_other=%s drop_rate=%.2f%%",
                stats["lines_read"],
                stats["lines_kept"],
                stats["lines_dropped_evidence"],
                stats["lines_dropped_other"],
                100.0 * drop_rate,
            )
            if drop_rate > 0.30:
                _LOG.warning(
                    "drop rate %.1f%% > 30%% — revisar alucinaciones en prod o relajar validador",
                    100.0 * drop_rate,
                )
        return stats


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    default_in = root / "packages" / "agents" / "train" / "conversation_traces"
    default_out = root / "packages" / "agents" / "train" / "gemma4"

    p = argparse.ArgumentParser(description="Sanitize conversation traces for Gemma 4 SFT")
    p.add_argument("--input-root", type=Path, default=default_in)
    p.add_argument("--output-root", type=Path, default=default_out)
    p.add_argument("--input-glob", default="**/traces.jsonl")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    san = GemmaSanitizer(
        input_root=args.input_root,
        output_root=args.output_root,
        input_glob=args.input_glob,
    )
    stats = san.export_dataset(dry_run=args.dry_run)
    if stats["lines_read"] == 0:
        _LOG.warning("no lines read — check --input-root and --input-glob (%s)", san.input_root)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
