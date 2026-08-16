"""Adjuntos de documento en playground chat (MarkItDown / texto nativo)."""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest

_gw = Path(__file__).resolve().parent.parent / "services" / "api-gateway"
if str(_gw) not in sys.path:
    sys.path.insert(0, str(_gw))


def test_playground_chat_body_accepts_documents() -> None:
    from routers.admin_domains.playground.schemas import PlaygroundChatBody, PlaygroundDocumentIn

    raw = base64.b64encode(b"hola mundo").decode("ascii")
    body = PlaygroundChatBody(
        worker_id="default",
        message="",
        documents=[
            PlaygroundDocumentIn(
                filename="nota.txt",
                mime_type="text/plain",
                data_base64=raw,
            )
        ],
    )
    assert len(body.documents) == 1
    assert body.documents[0].filename == "nota.txt"


def test_playground_chat_body_rejects_empty_without_attachments() -> None:
    from pydantic import ValidationError
    from routers.admin_domains.playground.schemas import PlaygroundChatBody

    with pytest.raises(ValidationError):
        PlaygroundChatBody(worker_id="default", message="", images=[], documents=[])


def test_enrich_message_with_playground_documents_txt() -> None:
    from routers.admin_domains.playground.chat_turn import enrich_message_with_playground_documents
    from routers.admin_domains.playground.schemas import PlaygroundDocumentIn

    raw = base64.b64encode("Saldo: 100\nDeuda: 20".encode("utf-8")).decode("ascii")
    docs = [
        PlaygroundDocumentIn(filename="finanzas.txt", mime_type="text/plain", data_base64=raw)
    ]
    msg, names = enrich_message_with_playground_documents("resume esto", docs)
    assert names == ["finanzas.txt"]
    assert "Documento adjunto: finanzas.txt" in msg
    assert "Saldo: 100" in msg
    assert "--- Mensaje del usuario ---" in msg
    assert "resume esto" in msg


def test_enrich_message_with_playground_documents_rejects_bad_ext() -> None:
    from routers.admin_domains.playground.chat_turn import enrich_message_with_playground_documents
    from routers.admin_domains.playground.schemas import PlaygroundDocumentIn

    raw = base64.b64encode(b"MZ").decode("ascii")
    docs = [
        PlaygroundDocumentIn(filename="malware.exe", mime_type="application/octet-stream", data_base64=raw)
    ]
    with pytest.raises(ValueError, match="Extensión no admitida"):
        enrich_message_with_playground_documents("", docs)


def test_enrich_message_with_playground_documents_rejects_oversize(monkeypatch: pytest.MonkeyPatch) -> None:
    from routers.admin_domains.playground import chat_turn
    from routers.admin_domains.playground.schemas import PlaygroundDocumentIn

    monkeypatch.setattr(chat_turn, "_CHAT_DOC_MAX_BYTES", 10)
    raw = base64.b64encode(b"0123456789abcdef").decode("ascii")
    docs = [PlaygroundDocumentIn(filename="big.txt", mime_type="text/plain", data_base64=raw)]
    with pytest.raises(ValueError, match="supera"):
        chat_turn.enrich_message_with_playground_documents("", docs)
