"""Filesystem-only trace collector for SFT datalake."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Optional

_TRAIN_DIR = Path(__file__).resolve().parents[3] / "train"
_FALLBACK_PATH = _TRAIN_DIR / "conversation_traces" / "_fallback" / "temp_traces.jsonl"
_FALLBACK_LOCK = threading.Lock()


class TraceCollector:
    """
    Sovereign trajectory collector for agent turns.

    Persists via ``append_conversation_trace`` (threading lock + UTC day paths).
    On I/O failure, appends to a local fallback JSONL file (no Redis / no db-writer).
    """

    def __init__(self, session_id: str, worker_id: str = "", *, tenant_id: str = ""):
        sid = (session_id or tenant_id or "").strip()
        if not sid:
            raise ValueError("session_id (or tenant_id alias) is required")
        self.session_id = sid
        self.worker_id = (worker_id or "").strip()

    @staticmethod
    def _validate_messages(messages: list[dict[str, Any]]) -> None:
        if not isinstance(messages, list) or len(messages) < 2:
            raise ValueError("messages must be a list with at least 2 turns")
        for item in messages:
            if not isinstance(item, dict):
                raise ValueError("each message must be a dict with role and content")
            if not str(item.get("role") or "").strip():
                raise ValueError("each message must include a non-empty role")
            if "content" not in item:
                raise ValueError("each message must include content")

    @staticmethod
    def _extract_user_assistant(messages: list[dict[str, Any]]) -> tuple[str, str]:
        user_msg = ""
        assistant_msg = ""
        for item in messages:
            role = str(item.get("role") or "").lower()
            content = str(item.get("content") or "")
            if role == "user":
                user_msg = content
            elif role == "assistant":
                assistant_msg = content
        return user_msg, assistant_msg

    def _write_fallback(
        self,
        messages: list[dict[str, Any]],
        status: str,
        metadata: Optional[dict[str, Any]],
        elapsed_ms: Optional[float],
    ) -> bool:
        ts_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        record: dict[str, Any] = {
            "messages": messages,
            "session_id": self.session_id[:128],
            "timestamp": ts_str,
            "elapsed_ms": int(elapsed_ms) if elapsed_ms is not None else None,
            "status": (status or "SUCCESS").upper()[:32],
        }
        if self.worker_id:
            record["worker_id"] = self.worker_id[:64]
        if metadata:
            record["metadata"] = metadata
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with _FALLBACK_LOCK:
            try:
                _FALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(_FALLBACK_PATH, "a", encoding="utf-8") as handle:
                    handle.write(line)
                return True
            except OSError:
                return False

    def collect(
        self,
        messages: list[dict[str, Any]],
        status: str = "SUCCESS",
        metadata: Optional[dict[str, Any]] = None,
        elapsed_ms: Optional[float] = 0.0,
    ) -> bool:
        """
        Package trajectory and persist through the canonical datalake append path.

        Returns True when primary or fallback write succeeds; False if both fail.
        """
        self._validate_messages(messages)
        user_msg, assistant_msg = self._extract_user_assistant(messages)
        system_prompt = None
        if metadata:
            raw = metadata.get("system_prompt")
            if raw:
                system_prompt = str(raw)

        try:
            from duckclaw.graphs.conversation_traces import append_conversation_trace

            append_conversation_trace(
                self.session_id,
                user_msg,
                assistant_msg,
                worker_id=self.worker_id or None,
                elapsed_ms=int(elapsed_ms) if elapsed_ms is not None else None,
                status=status,
                system_prompt=system_prompt,
                messages=list(messages),
            )
            return True
        except Exception:
            return self._write_fallback(messages, status, metadata, elapsed_ms)
