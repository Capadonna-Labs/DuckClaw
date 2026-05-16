"""Registro en memoria: token noVNC → puerto host, TTL y limpieza del sandbox browser.

specs/features/platform/STRIX_BROWSER_NOVNC.md
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import threading
import time
from typing import Any, Callable

_log = logging.getLogger(__name__)

_BROWSER_NOVNC_TTL_S = int(os.environ.get("DUCKCLAW_BROWSER_NOVNC_TTL_S", "600"))

_lock = threading.Lock()
_sessions: dict[str, dict[str, Any]] = {}
_by_token: dict[str, str] = {}
_timers: dict[str, threading.Timer] = {}


def sanitize_chat_to_session_id(chat_id: str) -> str:
    """Deriva un session_id estable para Docker (nombre strix_sandbox_<id>)."""
    raw = (chat_id or "").strip() or "default"
    s = re.sub(r"[^a-zA-Z0-9_]", "_", raw)
    s = s.strip("_") or "default"
    if len(s) > 48:
        s = s[:48]
    return s


def _cancel_timer(session_id: str) -> None:
    t = _timers.pop(session_id, None)
    if t is not None:
        try:
            t.cancel()
        except Exception:
            pass


def _run_expire(session_id: str) -> None:
    with _lock:
        info = _sessions.get(session_id)
        if not info:
            _timers.pop(session_id, None)
            return
        if time.time() < float(info.get("expires_at", 0)):
            need_reschedule = True
        else:
            need_reschedule = False
            tok = str(info.get("token") or "")
            if tok:
                _by_token.pop(tok, None)
            _sessions.pop(session_id, None)
            _timers.pop(session_id, None)
    if need_reschedule:
        _schedule_fire(session_id)
        return

    try:
        from duckclaw.graphs.sandbox import _get_manager  # noqa: PLC0415

        _get_manager().cleanup(session_id)
    except Exception as exc:  # noqa: BLE001
        _log.warning("novnc TTL cleanup failed session_id=%s: %s", session_id, exc)


def _schedule_fire(session_id: str) -> None:
    _cancel_timer(session_id)
    with _lock:
        info = _sessions.get(session_id)
        if not info:
            return
        remaining = float(info.get("expires_at", 0)) - time.time()
    if remaining <= 0:
        _run_expire(session_id)
        return
    # Cap single sleep to TTL max to avoid huge timers if clock skew
    wait = min(float(_BROWSER_NOVNC_TTL_S), max(0.5, remaining))
    timer = threading.Timer(wait, lambda: _run_expire(session_id))
    timer.daemon = True
    _timers[session_id] = timer
    timer.start()


def consume_initial_vnc_telegram_link(session_id: str) -> bool:
    """Primera difusión del enlace noVNC por Telegram para esta sesión: True y marca enviado.

    Tras un nuevo ``register_session_port`` (token/puerto nuevos) el flag vuelve a False.
    ``get_browser_session_url`` no usa esta función: el usuario puede pedir la URL explícitamente.
    """
    sid = (session_id or "").strip()
    if not sid:
        return True
    with _lock:
        info = _sessions.get(sid)
        if not info:
            return True
        if info.get("telegram_vnc_link_sent"):
            return False
        info["telegram_vnc_link_sent"] = True
        return True


def touch(session_id: str) -> None:
    """Renueva TTL (expires_at = now + TTL) y reprograma el timer."""
    sid = (session_id or "").strip()
    if not sid:
        return
    with _lock:
        if sid not in _sessions:
            return
        _sessions[sid]["expires_at"] = time.time() + float(_BROWSER_NOVNC_TTL_S)
    _schedule_fire(sid)


def register_session_port(session_id: str, host_port: int) -> str:
    """Registra o actualiza el puerto publicado; devuelve token opaco."""
    sid = (session_id or "").strip()
    if not sid or host_port <= 0:
        return ""
    with _lock:
        old_tok = (_sessions.get(sid) or {}).get("token")
        if isinstance(old_tok, str) and old_tok:
            _by_token.pop(old_tok, None)
        token = secrets.token_urlsafe(24)
        _sessions[sid] = {
            "token": token,
            "host_port": int(host_port),
            "expires_at": time.time() + float(_BROWSER_NOVNC_TTL_S),
            # Evita repetir el enlace noVNC en cada heartbeat de run_browser_sandbox (Telegram).
            "telegram_vnc_link_sent": False,
        }
        _by_token[token] = sid
    _schedule_fire(sid)
    return token


def revoke_session(session_id: str) -> None:
    """Invalida token y cancela timer (p. ej. tras cleanup manual)."""
    sid = (session_id or "").strip()
    with _lock:
        info = _sessions.pop(sid, None)
        if info:
            tok = str(info.get("token") or "")
            if tok:
                _by_token.pop(tok, None)
    _cancel_timer(sid)


def resolve_token(token: str) -> tuple[str | None, int | None]:
    """Devuelve (session_id, host_port) si el token es válido y no expiró."""
    t = (token or "").strip()
    if not t:
        return None, None
    with _lock:
        sid = _by_token.get(t)
        if not sid:
            return None, None
        info = _sessions.get(sid)
        if not info:
            return None, None
        if time.time() > float(info.get("expires_at", 0)):
            _by_token.pop(t, None)
            _sessions.pop(sid, None)
            return None, None
        port = int(info.get("host_port") or 0)
        if port <= 0:
            return None, None
        return sid, port


def get_existing_token_and_port(session_id: str) -> tuple[str | None, int | None]:
    """Token y puerto actuales si la sesión sigue vigente."""
    sid = (session_id or "").strip()
    with _lock:
        info = _sessions.get(sid)
        if not info:
            return None, None
        if time.time() > float(info.get("expires_at", 0)):
            return None, None
        tok = str(info.get("token") or "") or None
        port = int(info.get("host_port") or 0) or None
        return (tok, port) if tok and port else (None, None)


def build_vnc_url(token: str, host_port: int) -> str:
    """URL para abrir noVNC: pública si DUCKCLAW_PUBLIC_URL; si no, localhost directo al puerto."""
    from urllib.parse import quote

    base = (os.environ.get("DUCKCLAW_PUBLIC_URL") or "").strip().rstrip("/")
    if base:
        # noVNC arma ``wss://host:puerto/<path>`` con path por defecto ``websockify`` → ``/websockify`` en la raíz
        # del host. Tras el proxy el WebSocket está en
        # ``/api/v1/sandbox/novnc/view/{token}/websockify``; sin ``path=`` el navegador pide ``/websockify`` y el
        # gateway responde 403 (ruta inexistente). El query ``path=`` lo lee ``WebUtil.getConfigVar`` en noVNC.
        ws_path = f"api/v1/sandbox/novnc/view/{token}/websockify"
        path_q = quote(ws_path, safe="")
        return (
            f"{base}/api/v1/sandbox/novnc/view/{token}/vnc.html"
            f"?autoconnect=1&path={path_q}"
        )
    return f"http://127.0.0.1:{host_port}/vnc.html?autoconnect=1"
