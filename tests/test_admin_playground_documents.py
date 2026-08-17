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
    # El bloque marca el turno como adjunto aunque no haya copia en el vault.
    assert "[DOCUMENTOS_ADJUNTOS]" in msg
    assert "path=" not in msg


def test_enrich_persists_inbound_copy_when_tenant_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Con tenant, se guarda copia en inbound/ y el mensaje incluye path legible por tools."""
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(tmp_path))
    from routers.admin_domains.playground.chat_turn import enrich_message_with_playground_documents
    from routers.admin_domains.playground.schemas import PlaygroundDocumentIn

    raw = base64.b64encode("fila A\nfila B".encode("utf-8")).decode("ascii")
    docs = [PlaygroundDocumentIn(filename="tabla.csv", mime_type="text/csv", data_base64=raw)]
    msg, names = enrich_message_with_playground_documents("lee", docs, tenant_id="t_docs")
    assert names == ["tabla.csv"]
    assert "[DOCUMENTOS_ADJUNTOS]" in msg
    assert "path=" in msg
    assert "inbound" in msg.replace("\\", "/")
    # Copia real en vault
    inbound = tmp_path / "db" / "private" / "t_docs" / "inbound"
    files = list(inbound.glob("tabla_*.csv"))
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8") == "fila A\nfila B"


def test_resolve_readable_allows_tenant_inbound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS", raising=False)
    inbound = tmp_path / "db" / "private" / "t1" / "inbound"
    inbound.mkdir(parents=True)
    target = inbound / "nota_abc123.txt"
    target.write_text("hola", encoding="utf-8")

    from duckclaw.forge.rag.knowledge_paths import resolve_readable_document_path

    resolved = resolve_readable_document_path(relative_path=str(target))
    assert resolved == target.resolve()


def test_document_text_is_preserved_for_graph_handoff() -> None:
    """El historial puede guardar el nombre del adjunto, pero el worker recibe su texto."""
    from core.models import ChatRequest

    extracted = "[Documento adjunto: finanzas.txt]\nSaldo: 100"
    chat = ChatRequest(
        message=extracted,
        user_incoming="📎 finanzas.txt",
        graph_user_incoming=extracted,
        document_turn=True,
    )

    assert chat.user_incoming == "📎 finanzas.txt"
    assert chat.graph_user_incoming == extracted
    assert chat.document_turn is True


def test_document_turn_isolated_from_graph_history_without_erasing_chat_history() -> None:
    """The graph must not inherit a prior incorrect DB/menu reply for an attachment."""
    prepare_source = (
        Path(__file__).resolve().parent.parent
        / "services"
        / "api-gateway"
        / "core"
        / "chat_invoke_prepare.py"
    ).read_text(encoding="utf-8")
    runner_source = (
        Path(__file__).resolve().parent.parent
        / "services"
        / "api-gateway"
        / "core"
        / "chat_graph_runner.py"
    ).read_text(encoding="utf-8")

    assert "history_for_graph = [] if document_turn else history_for_model" in prepare_source
    assert "prepared.history_for_graph" in runner_source


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
