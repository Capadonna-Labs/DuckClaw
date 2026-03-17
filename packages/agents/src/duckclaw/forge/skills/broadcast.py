from __future__ import annotations

from typing import Any

import os

import requests
from langchain_core.tools import tool

from duckclaw.gateway_db import get_gateway_db


def _get_send_telegram_url() -> str:
    url = os.getenv("DUCKCLAW_TELEGRAM_SEND_WEBHOOK_URL") or os.getenv(
        "DUCKCLAW_SEND_DM_WEBHOOK_URL"
    )
    if not url:
        raise RuntimeError(
            "DUCKCLAW_TELEGRAM_SEND_WEBHOOK_URL (o DUCKCLAW_SEND_DM_WEBHOOK_URL) no está configurado."
        )
    return url


def _send_telegram_message(chat_id: str, text: str) -> None:
    url = _get_send_telegram_url()
    payload = {"chat_id": str(chat_id), "text": text}
    # Mejor esfuerzo: no levantamos la herramienta por un fallo puntual de red
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception:
        # En un futuro se puede loggear en gateway_db o logger central
        pass


@tool
def broadcast_message(game_id: str, message: str) -> str:
    """
    Envía un mensaje público a todos los jugadores de la partida.
    Úsalo para anunciar el inicio del nivel, errores o victorias.
    """
    if not game_id or not message:
        return "Uso: broadcast_message(game_id, message) con ambos parámetros no vacíos."

    db = get_gateway_db()
    rows = list(
        db.execute(
            "SELECT DISTINCT chat_id FROM the_mind_players WHERE game_id = ?", (game_id,)
        )
    )
    if not rows:
        return f"No hay jugadores registrados para la partida {game_id}."

    for (chat_id,) in rows:
        if chat_id:
            _send_telegram_message(chat_id, message)

    return "Broadcast exitoso."


@tool
def deal_cards(game_id: str, level: int) -> str:
    """
    Reparte cartas a los jugadores según el nivel actual y se las envía por mensaje privado.
    """
    if not game_id:
        return "Uso: deal_cards(game_id, level) con game_id no vacío."
    try:
        lvl = int(level)
    except Exception:
        return "El parámetro level debe ser un entero."
    if lvl <= 0:
        return "El nivel debe ser un entero positivo."

    db = get_gateway_db()
    players = list(
        db.execute(
            "SELECT chat_id, username FROM the_mind_players WHERE game_id = ?", (game_id,)
        )
    )
    if not players:
        return f"No hay jugadores registrados para la partida {game_id}."

    import random

    for chat_id, username in players:
        if not chat_id:
            continue
        # Generar lvl cartas aleatorias (1-100)
        hand = sorted(random.randint(1, 100) for _ in range(lvl))
        # Persistir mano en the_mind_players
        db.execute(
            "UPDATE the_mind_players SET cards = ? WHERE game_id = ? AND chat_id = ?",
            (hand, game_id, chat_id),
        )
        # Enviar DM al jugador con sus cartas
        uname = username or ""
        text = (
            f"Tus cartas para el Nivel {lvl} son: {hand}"
            if not uname
            else f"{uname}, tus cartas para el Nivel {lvl} son: {hand}"
        )
        _send_telegram_message(chat_id, text)

    # Actualizar nivel actual del juego
    db.execute(
        "UPDATE the_mind_games SET current_level = ? WHERE game_id = ?",
        (lvl, game_id),
    )

    return "Cartas repartidas en secreto."

