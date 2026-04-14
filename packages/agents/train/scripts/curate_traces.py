#!/usr/bin/env python3
"""
Curate conversation traces for Gemma4 SFT.

Reads:
  conversation_traces/2026/**/*.jsonl

Writes:
  sft_data_dir/curated_v2.jsonl

Rules implemented from request:
  EXCLUDE turns where assistant content:
    - has market figures but no tool_calls in that assistant message
    - is > 1200 chars and has no tool_calls
    - contains "300 123 4567"
    - contains "admin@leilastore.com"
    - claims balance update while tool_calls are empty

  INCLUDE only turns where:
    - there are successful tool calls before asserting a result
    - response follows single-domain contract
    - failures declare "Ceguera Sensorial" correctly
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


PHONE_BLOCK = "300 123 4567"
EMAIL_BLOCK = "admin@leilastore.com"

RE_HAS_NUMBER = re.compile(r"\b\d+(?:[.,]\d+)?\b")
RE_MARKET_TERM = re.compile(
    r"\b("
    r"precio|volatilidad|ohlcv|masa|densidad|temperatura|viscosidad|"
    r"close|open|high|low|ticker|cfd|market|mercado|fluido"
    r")\b",
    re.IGNORECASE,
)
RE_BALANCE_UPDATE_CLAIM = re.compile(
    r"\b("
    r"saldo\s+(actualizado|qued[oó]|quedo)|"
    r"actualic[ée]\s+.*saldo|"
    r"resta[dr][oa]?\s+\$?\s*\d+|"
    r"efectivo\s+actualizado|"
    r"total\s+cuentas?\s+locales"
    r")\b",
    re.IGNORECASE,
)

RE_TOOL_SUCCESS = re.compile(
    r'"status"\s*:\s*"(SUCCESS|success|ok|OK)"|'
    r'"status"\s*:\s*true|'
    r'"result"\s*:\s*"(SUCCESS|success)"',
    re.IGNORECASE,
)
RE_TOOL_ERROR = re.compile(r'"error"\s*:|Traceback|Exception', re.IGNORECASE)


def message_text(msg: dict[str, Any]) -> str:
    content = msg.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                txt = item.get("text")
                if isinstance(txt, str):
                    parts.append(txt)
        return "\n".join(parts)
    return str(content or "")


def has_tool_calls(msg: dict[str, Any]) -> bool:
    tc = msg.get("tool_calls")
    return isinstance(tc, list) and len(tc) > 0


def market_figures_without_tools(assistant_text: str, assistant_msg: dict[str, Any]) -> bool:
    if has_tool_calls(assistant_msg):
        return False
    return bool(RE_MARKET_TERM.search(assistant_text) and RE_HAS_NUMBER.search(assistant_text))


def is_single_domain_response(text: str) -> bool:
    t = text.lower()
    domains = {
        "mercado": bool(re.search(r"\b(cfd|ohlcv|mercado|ticker|volatilidad|fluido)\b", t)),
        "cuentas": bool(re.search(r"\b(cuentas?|saldo|ibkr|bancolombia|nequi|efectivo)\b", t)),
        "deudas": bool(re.search(r"\b(deuda|deudas|acreedor|vencimien)\b", t)),
        "presupuestos": bool(re.search(r"\b(presupuesto|presupuestos|categor[ií]a|vs real)\b", t)),
        "contexto": bool(re.search(r"\b(s[ií]ntesis|contexto|resumen de contexto|vlm_context)\b", t)),
    }
    active = sum(1 for v in domains.values() if v)
    # If we cannot classify (active=0), do not fail by default.
    return active <= 1


def is_ceguera_sensorial_ok(text: str) -> bool:
    t = text.lower()
    if "ceguera sensorial" not in t:
        return False
    return (
        ("lake capadonna" in t)
        and ("fuera de alcance" in t or "no hay datos ohlcv" in t)
        and ("no puedo calcular" in t)
    )


def prior_tool_success(messages: list[dict[str, Any]], assistant_idx: int) -> bool:
    for m in messages[:assistant_idx]:
        role = str(m.get("role", "")).lower()
        if role != "tool":
            continue
        content = message_text(m)
        if RE_TOOL_SUCCESS.search(content):
            return True
        # Fallback: if it looks like JSON rows and not an error, treat as successful.
        if content.strip().startswith("[") and not RE_TOOL_ERROR.search(content):
            return True
        if content.strip().startswith("{") and not RE_TOOL_ERROR.search(content):
            return True
    return False


def turn_window(messages: list[dict[str, Any]], assistant_idx: int) -> list[dict[str, Any]]:
    # Find latest user message before assistant.
    user_idx = -1
    for i in range(assistant_idx - 1, -1, -1):
        if str(messages[i].get("role", "")).lower() == "user":
            user_idx = i
            break
    start = user_idx if user_idx >= 0 else 0
    out: list[dict[str, Any]] = []
    if messages and str(messages[0].get("role", "")).lower() == "system":
        out.append(messages[0])
    out.extend(messages[start : assistant_idx + 1])
    return out


def should_keep_turn(messages: list[dict[str, Any]], assistant_idx: int) -> tuple[bool, str]:
    m = messages[assistant_idx]
    text = message_text(m).strip()
    if not text:
        return False, "empty_assistant"

    tc_present = has_tool_calls(m)

    if PHONE_BLOCK in text:
        return False, "blocked_phone"
    if EMAIL_BLOCK in text:
        return False, "blocked_email"
    if market_figures_without_tools(text, m):
        return False, "market_figures_without_tool_calls"
    if len(text) > 1200 and not tc_present:
        return False, "too_long_without_tool_calls"
    if RE_BALANCE_UPDATE_CLAIM.search(text) and not tc_present:
        return False, "balance_update_claim_without_tool_calls"

    ceguera_declared = "ceguera sensorial" in text.lower()
    if ceguera_declared:
        return (is_ceguera_sensorial_ok(text), "ceguera_sensorial_check")

    if not is_single_domain_response(text):
        return False, "multi_domain_violation"

    if not prior_tool_success(messages, assistant_idx):
        return False, "no_prior_successful_tool_call"

    return True, "kept"


def iter_trace_files(root: Path) -> list[Path]:
    return sorted(root.glob("2026/**/*.jsonl"))


def curate(input_root: Path, output_file: Path) -> tuple[int, int]:
    files = iter_trace_files(input_root)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    total_turns = 0
    kept_turns = 0

    with output_file.open("w", encoding="utf-8") as out:
        for fp in files:
            with fp.open("r", encoding="utf-8") as f:
                for line_no, raw in enumerate(f, start=1):
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        rec = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    msgs = rec.get("messages")
                    if not isinstance(msgs, list):
                        continue
                    normalized = [m for m in msgs if isinstance(m, dict)]
                    if not normalized:
                        continue

                    for i, m in enumerate(normalized):
                        if str(m.get("role", "")).lower() != "assistant":
                            continue
                        total_turns += 1
                        keep, reason = should_keep_turn(normalized, i)
                        if not keep:
                            continue
                        kept_turns += 1
                        row = {
                            "source_file": str(fp),
                            "line_no": line_no,
                            "turn_index": i,
                            "filter_reason": reason,
                            "messages": turn_window(normalized, i),
                        }
                        out.write(json.dumps(row, ensure_ascii=False) + "\n")

    return kept_turns, total_turns


def main() -> None:
    parser = argparse.ArgumentParser(description="Curate conversation traces for Gemma4 SFT")
    parser.add_argument(
        "--input-root",
        default=str(Path(__file__).resolve().parents[1] / "conversation_traces"),
        help="Root folder containing year directories (default: packages/agents/train/conversation_traces)",
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parents[1] / "sft_data_dir" / "curated_v2.jsonl"),
        help="Output JSONL file (default: packages/agents/train/sft_data_dir/curated_v2.jsonl)",
    )
    args = parser.parse_args()

    kept, total = curate(Path(args.input_root), Path(args.output))
    ratio = (kept / total) if total else 0.0
    print(f"curation_done kept={kept} total={total} ratio={ratio:.4f}")


if __name__ == "__main__":
    main()
