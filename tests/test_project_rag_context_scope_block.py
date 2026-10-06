"""The [KNOWLEDGE_SCOPE] preamble is only prepended when retrieval returned something."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

_GATEWAY = Path(__file__).resolve().parents[1] / "services" / "api-gateway"
if str(_GATEWAY) not in sys.path:
    sys.path.insert(0, str(_GATEWAY))

from routers.admin_domains.playground import project_rag_context as prc  # noqa: E402


def _patch_retrieval(monkeypatch, *, rag_block: str) -> None:
    import core.admin_identity as ident
    import duckclaw.forge.rag.context_provider as cp
    import duckclaw.forge.rag.injection_policy as ip

    @contextmanager
    def _db(read_only=True):
        yield object()

    monkeypatch.setattr(ident, "open_gateway_db", _db)
    monkeypatch.setattr(ip, "should_inject_playground_context", lambda _m: True)
    monkeypatch.setattr(
        cp,
        "build_knowledge_context",
        lambda *_a, **_k: SimpleNamespace(
            context_count=1 if rag_block else 0, inventory_block="", rag_block=rag_block
        ),
    )


def _call(msg: str) -> str:
    out, _n = prc.project_context_message(
        msg=msg, project_context=None, worker_id="w", tenant_id="t", project_id="", knowledge_scope="platform"
    )
    return out


def test_no_scope_preamble_without_retrieved_chunks(monkeypatch) -> None:
    _patch_retrieval(monkeypatch, rag_block="")
    assert _call("Implementa el bloque condicional") == "Implementa el bloque condicional"


def test_scope_preamble_with_retrieved_chunks(monkeypatch) -> None:
    _patch_retrieval(monkeypatch, rag_block="[RAG]\nchunk\n[/RAG]")
    out = _call("¿qué dice el doc?")
    assert out.startswith("[KNOWLEDGE_SCOPE]") and "[RAG]" in out and out.endswith("¿qué dice el doc?")
