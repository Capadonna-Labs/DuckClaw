"""Replies must not pass off un-run tool actions as done (zero-trust egress)."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from duckclaw.egress.claim_guard import append_unexecuted_claims_warning

TOOLS = ["create_skill", "list_skills", "read_sql", "search_project_knowledge", "invoke_worker"]
FAKE = (
    "## ✅ `/notificaciones` creado y confirmado\n"
    "| `create_skill` | ✅ Guardado en el hub |\n"
    "| `list_skills` | ✅ Aparece en el catálogo |"
)


def _turn(*tool_names: str) -> list:
    msgs: list = [HumanMessage(content="crea la skill")]
    for i, name in enumerate(tool_names):
        msgs.append(AIMessage(content="", tool_calls=[{"name": name, "args": {}, "id": f"c{i}"}]))
        msgs.append(ToolMessage(content="{}", name=name, tool_call_id=f"c{i}"))
    return msgs


def test_flags_claimed_actions_that_never_ran() -> None:
    # Real case (Flash, 1-Oct): only read_sql + search_project_knowledge ran.
    out = append_unexecuted_claims_warning(FAKE, _turn("read_sql", "search_project_knowledge"), 0, TOOLS)
    assert "Verificación automática" in out and "`create_skill`" in out and "`list_skills`" in out


def test_silent_when_the_tools_did_run() -> None:
    out = append_unexecuted_claims_warning(FAKE, _turn("create_skill", "list_skills"), 0, TOOLS)
    assert out == FAKE


def test_silent_on_mentions_without_success_claims_and_on_delegation() -> None:
    advice = "Puedes usar `create_skill` para guardarla en el catálogo."
    assert append_unexecuted_claims_warning(advice, _turn("read_sql"), 0, TOOLS) == advice
    # A delegate may have run it; we can't see its tools, so don't accuse.
    assert append_unexecuted_claims_warning(FAKE, _turn("invoke_worker"), 0, TOOLS) == FAKE
