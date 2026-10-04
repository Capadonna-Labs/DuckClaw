"""Extension reply-audit hooks: rewrite, retry routing, and failure isolation (core is domain-free)."""

from __future__ import annotations

from langchain_core.messages import SystemMessage

from duckclaw.extensions import reply_audit
from duckclaw.workers.factory_graph_context import WorkerGraphContext
from duckclaw.workers.factory_graph_nodes_routing import make_route_after_set_reply


def _with_hooks(monkeypatch, *hooks) -> None:
    monkeypatch.setattr(reply_audit, "_HOOKS_CACHE", list(hooks))


def test_no_hooks_keeps_reply(monkeypatch) -> None:
    _with_hooks(monkeypatch)
    out = reply_audit.invoke_extension_reply_audit_hooks(reply="hola", messages=[], state={}, spec=None, db=None)
    assert out == ("hola", {}, None)


def test_hooks_rewrite_in_order_and_broken_hook_is_skipped(monkeypatch) -> None:
    def broken(**_kw):
        raise RuntimeError("boom")

    def upper(*, reply, messages, state, spec, db):
        return reply.upper(), {**state, "seen": True}, None

    _with_hooks(monkeypatch, broken, upper)
    reply, state, retry = reply_audit.invoke_extension_reply_audit_hooks(
        reply="hola", messages=[], state={}, spec=None, db=None
    )
    assert (reply, state, retry) == ("HOLA", {"seen": True}, None)


def test_retry_request_routes_back_to_agent(monkeypatch) -> None:
    def ask_retry(*, reply, messages, state, spec, db):
        return reply, state, [SystemMessage(content="cita evidencia")]

    _with_hooks(monkeypatch, ask_retry)
    _, _, retry = reply_audit.invoke_extension_reply_audit_hooks(
        reply="x", messages=[], state={}, spec=None, db=None
    )
    assert retry and retry[0].content == "cita evidencia"

    route = make_route_after_set_reply(WorkerGraphContext(worker_id="t", db=None, spec=None))
    assert route({"audit_graph_retry": True, "reply": ""}) == "agent"
    assert route({"reply": "ok"}) == "end"
