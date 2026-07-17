"""DB-first system prompt resolution for workers and chat surfaces."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from duckclaw.prompt_policies.resolver import PromptPolicyResolver

if TYPE_CHECKING:
    from duckclaw.workers.manifest import WorkerSpec

_log = logging.getLogger(__name__)


def normalize_worker_id(worker_id: Optional[str]) -> str:
    return (worker_id or "default").strip().lower() or "default"


def format_system_prompt_template(
    content: str,
    *,
    worker_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> str:
    raw = (content or "").strip()
    if not raw:
        return ""
    wid = normalize_worker_id(worker_id)
    tid = (tenant_id or "default").strip() or "default"
    try:
        return raw.format(tenant_id=tid, worker_id=wid)
    except KeyError:
        return raw


def _filesystem_system_prompt(spec: WorkerSpec | None) -> str:
    if spec is None:
        return ""
    try:
        from duckclaw.workers.loader import load_system_prompt

        return (load_system_prompt(spec) or "").strip()
    except Exception:
        return ""


def resolve_effective_system_prompt(
    db: Any,
    *,
    worker_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    spec: WorkerSpec | None = None,
    filesystem_fallback: str = "",
) -> str:
    """
    Resolve the effective system prompt for a worker turn.

    Order:
    1. DuckDB ``system_prompt/<worker>`` (inherits ``default`` via PromptPolicyResolver)
    2. Capa 0 airbag for ``system_prompt/default`` when DB row is missing
    3. Filesystem ``soul.md`` + ``system_prompt.md`` from ``spec`` (legacy templates)
    4. Optional injected filesystem fallback (e.g. default worker provider)
    """
    policy_name = normalize_worker_id(worker_id)
    tid = (tenant_id or "default").strip() or "default"
    raw = ""

    try:
        raw = PromptPolicyResolver(db=db).load("system_prompt", policy_name)
        if raw:
            _log.debug(
                "system_prompt resolved from DB for %s (tenant=%s)",
                policy_name,
                tid,
            )
    except FileNotFoundError:
        raw = ""
    except Exception as exc:
        _log.warning(
            "system_prompt DB resolution failed for %s: %s",
            policy_name,
            exc,
        )
        raw = ""

    if not raw.strip():
        raw = _filesystem_system_prompt(spec)
        if raw:
            _log.debug(
                "system_prompt filesystem fallback for %s via template dir",
                policy_name,
            )

    if not raw.strip():
        raw = (filesystem_fallback or "").strip()
        if raw:
            _log.debug(
                "system_prompt injected filesystem fallback for %s",
                policy_name,
            )

    return format_system_prompt_template(
        raw,
        worker_id=policy_name,
        tenant_id=tid,
    )


_REPORT_ENGINE_SKILL_MARKERS = frozenset({"report_engine", "reports"})


def worker_has_report_engine_skill(spec: WorkerSpec | None) -> bool:
    """True si el worker optó por el atom Report Engine (no dashboards HTML)."""
    if spec is None:
        return False
    skills = {
        str(skill).strip().lower().replace("-", "_")
        for skill in (getattr(spec, "skills_list", None) or [])
        if str(skill or "").strip()
    }
    if skills & _REPORT_ENGINE_SKILL_MARKERS:
        return True
    configs = getattr(spec, "skill_configs", None) or {}
    return any(key in configs for key in _REPORT_ENGINE_SKILL_MARKERS)


def _worker_includes_report_engine_directive(spec: WorkerSpec | None) -> bool:
    return worker_has_report_engine_skill(spec)


def _append_framework_directive(db: Any, base: str, directive_name: str) -> str:
    body = (base or "").strip()
    if not body:
        return body
    try:
        directive = PromptPolicyResolver(db=db).load("directive", directive_name)
    except (FileNotFoundError, RuntimeError):
        # RuntimeError: tabla/policy ausente (p. ej. probe con DB efímera).
        # No tumbar el init del grafo ni vaciar tools_runtime.
        return body
    directive = (directive or "").strip()
    if not directive:
        return body
    return f"{body}\n\n---\n\n{directive}"


def resolve_effective_system_prompt_with_directives(
    db: Any,
    *,
    worker_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    spec: WorkerSpec | None = None,
    filesystem_fallback: str = "",
) -> str:
    """Resolve system prompt and append optional framework directives (e.g. report_engine)."""
    base = resolve_effective_system_prompt(
        db,
        worker_id=worker_id,
        tenant_id=tenant_id,
        spec=spec,
        filesystem_fallback=filesystem_fallback,
    )
    if db is None:
        return base
    if not _worker_includes_report_engine_directive(spec):
        return base
    return _append_framework_directive(db, base, "report_engine")


def resolve_effective_system_prompt_for_worker(
    db: Any,
    spec: WorkerSpec,
    *,
    tenant_id: Optional[str] = None,
) -> str:
    worker_id = (
        getattr(spec, "logical_worker_id", None) or spec.worker_id or "default"
    )
    return resolve_effective_system_prompt_with_directives(
        db,
        worker_id=worker_id,
        tenant_id=tenant_id,
        spec=spec,
    )
