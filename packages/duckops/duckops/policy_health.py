"""Framework prompt policy preflight for duckops doctor and TUI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from duckclaw.prompt_policies.framework_fallbacks import framework_fallback_content
from duckclaw.prompt_policies.health import (
    FRAMEWORK_PROMPT_POLICY_REQUIREMENTS,
    PromptPolicyRequirement,
    missing_prompt_policies,
)


@dataclass(frozen=True)
class FrameworkPolicyHealth:
    ok: bool
    degraded_keys: tuple[str, ...]
    missing_keys: tuple[str, ...]

    @property
    def degraded(self) -> bool:
        return bool(self.degraded_keys)

    def summary(self) -> str:
        if self.ok and not self.degraded:
            return "framework policies activas en DuckDB"
        if self.ok and self.degraded:
            return (
                f"degradado capa 0 ({len(self.degraded_keys)} sin fila DB): "
                + ", ".join(self.degraded_keys)
            )
        return f"faltan policies críticas: {', '.join(self.missing_keys)}"


def check_framework_prompt_policies(db: Any) -> FrameworkPolicyHealth:
    """Return health for the 4 framework keys required at runtime."""

    requirements = [
        PromptPolicyRequirement(policy_type, policy_name, source)
        for policy_type, policy_name, source in FRAMEWORK_PROMPT_POLICY_REQUIREMENTS
    ]
    missing_db = missing_prompt_policies(db, requirements)
    degraded: list[str] = []
    critical: list[str] = []
    for item in missing_db:
        key = f"{item.policy_type}/{item.policy_name}"
        if framework_fallback_content(item.policy_type, item.policy_name):
            degraded.append(key)
        else:
            critical.append(key)
    return FrameworkPolicyHealth(
        ok=not critical,
        degraded_keys=tuple(degraded),
        missing_keys=tuple(critical),
    )


def run_framework_policy_preflight(
    repo: Path,
    *,
    print_fn: Callable[[str], None],
    strict: bool = False,
) -> bool:
    """Post-migrate smoke: warn on degraded airbag; fail only when ``strict``."""

    del repo  # reserved for future hub path overrides
    try:
        from duckclaw.gateway_db import get_gateway_db_path
    except Exception as exc:
        print_fn(f"Policies framework — omitido ({exc})")
        return True

    db_path = (get_gateway_db_path() or "").strip()
    if not db_path:
        print_fn("Policies framework — sin ruta hub (duckops up o duckops configure)")
        return True

    try:
        import duckdb

        con = duckdb.connect(db_path, read_only=True)
        try:
            health = check_framework_prompt_policies(con)
        finally:
            con.close()
    except Exception as exc:
        msg = f"Policies framework — error de lectura: {exc}"
        print_fn(msg)
        return not strict

    if not health.ok:
        print_fn(f"Policies framework — {health.summary()}")
        if strict:
            print_fn("Policies framework — fallo (--strict)")
            return False
        return True

    if health.degraded:
        print_fn(f"Policies framework — {health.summary()}")
        print_fn(
            "  hint: uv run duckclaw-migrate o "
            "POST /prompt-policies/restore-framework en admin"
        )
        if strict:
            print_fn("Policies framework — fallo degradado (--strict)")
            return False
        return True

    print_fn(f"Policies framework — {health.summary()}")
    return True


@dataclass(frozen=True)
class CatalogPromptHealth:
    ok: bool
    missing_worker_ids: tuple[str, ...]

    def summary(self) -> str:
        if self.ok:
            return "workers de catálogo con system_prompt activo"
        return f"faltan system_prompt: {', '.join(self.missing_worker_ids)}"


def check_catalog_worker_system_prompts(db: Any) -> CatalogPromptHealth:
    """Warn when **in-use** catalog workers lack an active ``system_prompt`` row.

    Skips dormant catalog entries (p. ej. plantillas importadas sin proyecto ni
    asignación) so document/report flows do not depend on agents like
    ``aws-expert-agent`` sitting unused in the catalog.
    """

    rows = db.execute(
        """
        SELECT DISTINCT c.worker_id
        FROM main.admin_worker_catalog c
        WHERE c.active = true
          AND c.worker_id != 'default'
          AND (
            c.source_kind = 'runtime'
            OR EXISTS (
              SELECT 1
              FROM main.admin_project_agents pa
              INNER JOIN main.admin_projects p ON p.project_id = pa.project_id
              WHERE pa.worker_uid = c.worker_uid
                AND pa.active = true
                AND p.active = true
            )
            OR EXISTS (
              SELECT 1
              FROM main.admin_worker_assignments wa
              WHERE wa.worker_uid = c.worker_uid
            )
          )
        ORDER BY c.worker_id
        """
    ).fetchall()
    missing: list[str] = []
    for row in rows:
        worker_id = str(row[0] if not isinstance(row, dict) else row.get("worker_id") or "").strip()
        if not worker_id:
            continue
        has_policy = db.execute(
            """
            SELECT 1
            FROM main.prompt_policy_registry
            WHERE policy_type = 'system_prompt'
              AND policy_name = ?
              AND active = true
              AND status = 'active'
            LIMIT 1
            """,
            [worker_id],
        ).fetchone()
        if not has_policy:
            missing.append(worker_id)
    return CatalogPromptHealth(ok=not missing, missing_worker_ids=tuple(missing))
