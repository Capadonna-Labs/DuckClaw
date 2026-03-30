"""
The Mind — outbound Telegram/n8n y reparto de cartas.

Usado por fly commands (`on_the_fly_commands`) y por herramientas LangChain (con `db` inyectada).
"""

from __future__ import annotations

import logging
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any

import requests
from langchain_core.tools import tool
from duckclaw.utils.logger import get_obs_logger, log_fly
from duckclaw.utils.telegram_markdown_v2 import escape_telegram_markdown_v2

_log = logging.getLogger("duckclaw.the_mind_outbound")
_obs = get_obs_logger("duckclaw.fly")


def _preview_text(text: str, max_len: int = 50) -> str:
    t = (text or "").replace("\n", " ").strip()
    return t[:max_len]


def _telegram_safe(text: str) -> str:
    """Escapa texto para nodos outbound configurados con Markdown/MarkdownV2."""
    return escape_telegram_markdown_v2(text)


def _team_username_by_user_id(db: Any, tenant_id: str, user_id: str) -> str:
    """Best-effort lookup en whitelist para logs legibles."""
    try:
        rows = list(
            db.execute(
                """
                SELECT username
                FROM main.authorized_users
                WHERE tenant_id = ? AND user_id = ?
                LIMIT 1
                """,
                (tenant_id, user_id),
            )
        )
        if rows and rows[0] and rows[0][0]:
            return str(rows[0][0]).strip()
    except Exception:
        pass
    return ""


def _pm2_identity_label(
    chat_id: str,
    *,
    username: str = "",
    db: Any | None = None,
    tenant_id: str | None = None,
) -> str:
    cid = str(chat_id or "").strip() or "unknown"
    uname = str(username or "").strip()
    if not uname and db is not None and cid:
        tid = str(tenant_id or "default").strip() or "default"
        uname = _team_username_by_user_id(db, tid, cid)
    return f"@{uname} ({cid})" if uname else cid


@dataclass(frozen=True)
class TelegramDmOutcome:
    """Resultado de un intento de envío DM vía webhook."""

    ok: bool
    reason: str
    detail: str = ""

    @staticmethod
    def success() -> "TelegramDmOutcome":
        return TelegramDmOutcome(True, "ok", "")

    @staticmethod
    def skipped_no_url() -> "TelegramDmOutcome":
        return TelegramDmOutcome(False, "skipped_no_url", "ninguna URL outbound configurada")

    @staticmethod
    def skipped_no_chat_id() -> "TelegramDmOutcome":
        return TelegramDmOutcome(False, "skipped_no_chat_id", "chat_id vacío")

    @staticmethod
    def http_error(status_code: int, body_snippet: str) -> "TelegramDmOutcome":
        return TelegramDmOutcome(
            False,
            "http_error",
            f"HTTP {status_code}: {body_snippet[:200]}",
        )

    @staticmethod
    def from_exception(exc: BaseException) -> "TelegramDmOutcome":
        return TelegramDmOutcome(False, "exception", str(exc)[:300])


@dataclass
class DealCardsResult:
    """Reparto persistido + resultados de cada DM."""

    summary_line: str
    dm_outcomes: list[TelegramDmOutcome] = field(default_factory=list)

    def __str__(self) -> str:
        return self.summary_line


@dataclass
class BroadcastResult:
    """Broadcast a todos los jugadores de una partida."""

    summary_line: str
    dm_outcomes: list[TelegramDmOutcome] = field(default_factory=list)

    def __str__(self) -> str:
        return self.summary_line


def resolve_telegram_outbound_url() -> str | None:
    """
    Misma URL que `send_proactive_message` / homeostasis: N8N_OUTBOUND_WEBHOOK_URL primero.

    Después, overrides opcionales solo si hace falta un endpoint distinto para Telegram/DM.
    """
    for key in (
        "N8N_OUTBOUND_WEBHOOK_URL",
        "DUCKCLAW_TELEGRAM_SEND_WEBHOOK_URL",
        "DUCKCLAW_SEND_DM_WEBHOOK_URL",
    ):
        v = (os.environ.get(key) or "").strip()
        if v:
            return v
    return None


def outbound_request_headers() -> dict[str, str]:
    """
    Cabeceras para POST al webhook de salida.

    - N8N_AUTH_KEY → X-N8N-Auth (flujos n8n clásicos).
    - DUCKCLAW_WEBHOOK_SECRET → X-DuckClaw-Secret (mismo contrato que alertas del gateway).
    Si solo existe N8N_AUTH_KEY, se envían ambas cabeceras con el mismo valor para máxima compatibilidad.
    """
    h: dict[str, str] = {"Content-Type": "application/json"}
    n8n_auth = (os.environ.get("N8N_AUTH_KEY") or "").strip()
    duck_secret = (os.environ.get("DUCKCLAW_WEBHOOK_SECRET") or "").strip()
    if duck_secret:
        h["X-DuckClaw-Secret"] = duck_secret
    if n8n_auth:
        h["X-N8N-Auth"] = n8n_auth
        if not duck_secret:
            h["X-DuckClaw-Secret"] = n8n_auth
    return h


def send_telegram_dm(
    chat_id: str,
    text: str,
    *,
    username: str = "",
    db: Any | None = None,
    tenant_id: str | None = None,
) -> TelegramDmOutcome:
    """
    POST JSON {chat_id, text, user_id} al webhook de n8n / Telegram.

    Incluye `user_id` igual a `chat_id` para flujos que solo lean user_id.
    """
    url = resolve_telegram_outbound_url()
    if not url:
        _log.warning(
            "The Mind outbound: sin URL (define N8N_OUTBOUND_WEBHOOK_URL como el resto de "
            "mensajes salientes, o DUCKCLAW_TELEGRAM_SEND_WEBHOOK_URL / DUCKCLAW_SEND_DM_WEBHOOK_URL)"
        )
        return TelegramDmOutcome.skipped_no_url()
    cid = (chat_id or "").strip()
    ident = _pm2_identity_label(cid, username=username, db=db, tenant_id=tenant_id)
    if not cid:
        _log.warning("The Mind outbound: chat_id vacío, no se envía DM")
        return TelegramDmOutcome.skipped_no_chat_id()

    safe_text = _telegram_safe(text or "")
    payload = {"chat_id": cid, "user_id": cid, "text": safe_text}
    try:
        log_fly(
            _obs,
            "outbound pre -> to=%s chat_id=%s url=%s text=%s",
            ident,
            cid,
            url,
            _preview_text(safe_text, max_len=50),
        )
        t0 = time.perf_counter()
        resp = requests.post(url, json=payload, headers=outbound_request_headers(), timeout=5)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        snippet = (resp.text or "").strip().replace("\n", " ")
        log_fly(
            _obs,
            "outbound post -> to=%s chat_id=%s status=%s elapsed_ms=%s body=%s",
            ident,
            cid,
            resp.status_code,
            elapsed_ms,
            snippet[:500],
        )
        if resp.ok:
            return TelegramDmOutcome.success()
        _log.warning(
            "The Mind outbound: webhook respondió %s para to=%s chat_id=%s — %s",
            resp.status_code,
            ident,
            cid,
            snippet[:500],
        )
        return TelegramDmOutcome.http_error(resp.status_code, snippet)
    except Exception as exc:
        _log.warning(
            "The Mind outbound: error enviando DM a to=%s chat_id=%s: %s",
            ident,
            cid,
            exc,
            exc_info=_log.isEnabledFor(logging.DEBUG),
        )
        return TelegramDmOutcome.from_exception(exc)


def _aggregate_dm_line(prefix: str, outcomes: list[TelegramDmOutcome]) -> str:
    if not outcomes:
        return f"{prefix} (sin destinatarios)."
    ok = sum(1 for o in outcomes if o.ok)
    fail = len(outcomes) - ok
    if fail == 0:
        return f"{prefix}: {ok} enviado(s) OK."
    reasons = ", ".join(sorted({o.reason for o in outcomes if not o.ok}))
    return f"{prefix}: {ok} OK, {fail} fallido(s) ({reasons})."


def broadcast_message_to_players(
    db: Any,
    game_id: str,
    message: str,
    *,
    exclude_chat_id: str | None = None,
) -> BroadcastResult:
    """
    Avisos generales del juego: el mismo texto a cada DM (chat_id) de la partida.
    (Las cartas van con deal_cards: mensaje distinto por jugador.)
    """
    if not game_id or not message:
        return BroadcastResult(
            "Uso: broadcast_message(game_id, message) con ambos parámetros no vacíos.",
            [],
        )

    rows = list(
        db.execute(
            "SELECT DISTINCT chat_id, username FROM the_mind_players WHERE game_id = ?",
            (game_id,),
        )
    )
    if not rows:
        return BroadcastResult(
            f"No hay jugadores registrados para la partida {game_id}.",
            [],
        )

    outcomes: list[TelegramDmOutcome] = []
    exclude = (exclude_chat_id or "").strip()
    for chat_id, username in rows:
        cid = str(chat_id or "").strip()
        if cid and cid != exclude:
            outcomes.append(
                send_telegram_dm(
                    cid,
                    message,
                    username=str(username or ""),
                    db=db,
                )
            )

    line = _aggregate_dm_line("Avisos DM", outcomes)
    return BroadcastResult(line, outcomes)


def deal_cards_for_level(
    db: Any,
    game_id: str,
    level: int,
    *,
    exclude_chat_id: str | None = None,
) -> DealCardsResult:
    """
    Reparte `level` cartas (1–100) a cada jugador, persiste en the_mind_players,
    actualiza current_level en the_mind_games y envía DM a cada jugador.
    """
    if not game_id:
        return DealCardsResult("Uso: deal_cards(game_id, level) con game_id no vacío.", [])
    try:
        lvl = int(level)
    except Exception:
        return DealCardsResult("El parámetro level debe ser un entero.", [])
    if lvl <= 0:
        return DealCardsResult("El nivel debe ser un entero positivo.", [])

    players = list(
        db.execute(
            "SELECT chat_id, username FROM the_mind_players WHERE game_id = ?", (game_id,)
        )
    )
    if not players:
        return DealCardsResult(
            f"No hay jugadores registrados para la partida {game_id}.",
            [],
        )

    n_players = len(players)
    total_needed = n_players * lvl
    if total_needed > 100:
        return DealCardsResult(
            f"No se puede repartir nivel {lvl}: {n_players} jugador(es) requieren {total_needed} cartas únicas y el mazo es 1..100.",
            [],
        )

    # Cartas únicas globales por nivel: sin repetición entre jugadores ni dentro de una mano.
    deck = random.sample(range(1, 101), total_needed)

    outcomes: list[TelegramDmOutcome] = []
    exclude = (exclude_chat_id or "").strip()
    for idx, (chat_id, username) in enumerate(players):
        if not chat_id:
            continue
        cid = str(chat_id).strip()
        start = idx * lvl
        hand = sorted(deck[start:start + lvl])
        db.execute(
            "UPDATE the_mind_players SET cards = ? WHERE game_id = ? AND chat_id = ?",
            (hand, game_id, cid),
        )
        if cid != exclude:
            uname = username or ""
            text = (
                f"Tus cartas para el Nivel {lvl} son: {hand}"
                if not uname
                else f"{uname}, tus cartas para el Nivel {lvl} son: {hand}"
            )
            outcomes.append(send_telegram_dm(cid, text, username=str(uname), db=db))

    db.execute(
        "UPDATE the_mind_games SET current_level = ? WHERE game_id = ?",
        (lvl, game_id),
    )

    line = _aggregate_dm_line("Cartas (DM por jugador)", outcomes)
    return DealCardsResult(line, outcomes)


def make_broadcast_message_tool(db: Any):
    """Herramienta LangChain con conexión DuckDB inyectada (bóveda activa del grafo)."""

    @tool
    def broadcast_message(game_id: str, message: str) -> str:
        """
        Envía un mensaje público a todos los jugadores de la partida.
        Úsalo para anunciar el inicio del nivel, errores o victorias.
        """
        return str(broadcast_message_to_players(db, game_id, message))

    return broadcast_message


def make_deal_cards_tool(db: Any):
    """Herramienta LangChain con conexión DuckDB inyectada."""

    @tool
    def deal_cards(game_id: str, level: int) -> str:
        """
        Reparte cartas a los jugadores según el nivel actual y se las envía por mensaje privado.
        """
        return str(deal_cards_for_level(db, game_id, level))

    return deal_cards
