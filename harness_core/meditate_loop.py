"""
harness_core/meditate_loop.py

LangGraph sub-graph for self-healing loop:
  analyze_logs → propose_fix → create_pr → pr_ready

Respects MAX_ITERATIONS guard and terminates in pr_ready.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import duckdb
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_ITERATIONS = 3
LOGS_TABLE = "task_audit_log"
ERROR_LEVELS = ("ERROR", "CRITICAL")
LOOKBACK_HOURS = 24

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class MeditateState(BaseModel):
    """Pydantic-typed state for the meditate loop."""

    iteration_count: int = Field(
        default=0,
        description="Current iteration of the meditate loop.",
        ge=0,
        le=MAX_ITERATIONS,
    )
    logs: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Rows fetched from task_audit_log (last 24h errors).",
    )
    fix_suggestion: Optional[str] = Field(
        default=None,
        description="Code-change suggestion produced by propose_fix_node.",
    )
    pr_ready: bool = Field(
        default=False,
        description="True when create_pr_node has finished (terminal).",
    )
    error: Optional[str] = Field(
        default=None,
        description="Captured error message if a node fails.",
    )

    class Config:
        frozen = False  # mutable for LangGraph


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def analyze_logs_node(state: MeditateState) -> MeditateState:
    """Read DuckDB task_audit_log looking for ERROR/CRITICAL rows in the last
    LOOKBACK_HOURS.  Populates state.logs and increments iteration_count."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
        conn = duckdb.connect()
        query = f"""
            SELECT
                timestamp,
                task_id,
                level,
                message,
                context
            FROM {LOGS_TABLE}
            WHERE level IN ({','.join("'{}'".format(lvl) for lvl in ERROR_LEVELS)})
              AND timestamp >= ?
            ORDER BY timestamp DESC
            LIMIT 50
        """
        result = conn.execute(query, (cutoff.isoformat(),))
        rows = [
            {
                "timestamp": str(r[0]),
                "task_id": r[1],
                "level": r[2],
                "message": r[3],
                "context": r[4],
            }
            for r in result.fetchall()
        ]
        conn.close()
        state.logs = rows
        state.iteration_count += 1
        logger.info(
            "analyze_logs_node: found %d error rows in last %d h",
            len(rows),
            LOOKBACK_HOURS,
        )
    except Exception as exc:
        state.error = f"analyze_logs_node failed: {exc}"
        logger.error(state.error)
    return state


def propose_fix_node(state: MeditateState) -> MeditateState:
    """Use an LLM call to suggest a code change based on the error logs found.
    Stores the suggestion in state.fix_suggestion."""
    if state.error:
        logger.warning("propose_fix_node: skipping due to prior error")
        return state

    try:
        # --- Mock LLM call ---
        # In production this would invoke a model (e.g. OpenAI / local LLM)
        # with a prompt built from state.logs.
        suggestion_parts: List[str] = []
        for row in state.logs[:3]:  # top 3 errors
            suggestion_parts.append(
                f"- Error `{row.get('level')}` in task `{row.get('task_id')}`: "
                f"{row.get('message')}. "
                f"Suggested fix: review {row.get('context', 'the component')}."
            )
        state.fix_suggestion = (
            "## Auto-generated fix suggestions\n\n"
            + "\n".join(suggestion_parts)
            + "\n\n*Review and adjust before PR.*"
        )
        logger.info("propose_fix_node: suggestion generated (%d chars)", len(state.fix_suggestion or ""))
    except Exception as exc:
        state.error = f"propose_fix_node failed: {exc}"
        logger.error(state.error)
    return state


def create_pr_node(state: MeditateState) -> MeditateState:
    """Mock a GitHub MCP call to create a pull request with the fix.
    Sets pr_ready = True on success."""
    if state.error:
        logger.warning("create_pr_node: skipping due to prior error")
        state.pr_ready = True  # still terminate
        return state

    try:
        # --- Mock MCP call ---
        # In production this would call create_pull_request / push_files etc.
        pr_payload = {
            "title": "fix: auto-heal from meditate loop",
            "body": state.fix_suggestion or "No errors detected.",
            "branch": f"fix/meditate-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "status": "mocked_success",
        }
        logger.info("create_pr_node: PR created (mock) → %s", json.dumps(pr_payload))
        state.pr_ready = True
    except Exception as exc:
        state.error = f"create_pr_node failed: {exc}"
        logger.error(state.error)
        state.pr_ready = True  # terminate regardless
    return state


# ---------------------------------------------------------------------------
# Conditional edge logic
# ---------------------------------------------------------------------------


def should_continue(state: MeditateState) -> str:
    """Route to the next node or terminate."""
    if state.pr_ready:
        return "end"
    if state.iteration_count >= MAX_ITERATIONS:
        logger.info("should_continue: MAX_ITERATIONS (%d) reached → end", MAX_ITERATIONS)
        return "end"
    if state.error:
        logger.info("should_continue: error present → end")
        return "end"
    return "propose_fix"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_meditate_graph() -> StateGraph:
    """Construct the meditate StateGraph.

    Nodes:
        analyze_logs_node
        propose_fix_node
        create_pr_node

    Flow:
        START → analyze_logs_node
            → should_continue (conditional)
                → "propose_fix" → propose_fix_node → create_pr_node → END
                → "end" → END
    """
    builder = StateGraph(MeditateState)

    # Register nodes
    builder.add_node("analyze_logs", analyze_logs_node)
    builder.add_node("propose_fix", propose_fix_node)
    builder.add_node("create_pr", create_pr_node)

    # Edges
    builder.set_entry_point("analyze_logs")
    builder.add_conditional_edges(
        "analyze_logs",
        should_continue,
        {
            "propose_fix": "propose_fix",
            "end": END,
        },
    )
    builder.add_edge("propose_fix", "create_pr")
    builder.add_edge("create_pr", END)

    return builder


# ---------------------------------------------------------------------------
# Convenience instance
# ---------------------------------------------------------------------------

meditate_graph = build_meditate_graph().compile()

__all__ = [
    "MeditateState",
    "analyze_logs_node",
    "propose_fix_node",
    "create_pr_node",
    "build_meditate_graph",
    "meditate_graph",
    "MAX_ITERATIONS",
]