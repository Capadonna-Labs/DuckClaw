"""DB-first homeostasis manifest commands for /goals."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Optional

from duckclaw.commands.chat_state import get_chat_state, set_chat_state

LlmTripletResolver = Callable[[Any, Any], tuple[str, str, str]]
VaultUserIdResolver = Callable[..., str]

_goals_llm_triplet_resolver: LlmTripletResolver | None = None
_goals_vault_user_id_resolver: VaultUserIdResolver | None = None


def configure_goals_llm_triplet_resolver(resolver: LlmTripletResolver | None) -> None:
    """Configure graph-owned LLM settings lookup without importing the graph here."""
    global _goals_llm_triplet_resolver
    _goals_llm_triplet_resolver = resolver


def configure_goals_vault_user_id_resolver(resolver: VaultUserIdResolver | None) -> None:
    """Configure graph-owned vault user resolution without importing the graph here."""
    global _goals_vault_user_id_resolver
    _goals_vault_user_id_resolver = resolver


def _normalize_belief_key(key: str) -> str:
    """Normaliza key para DB: alfanumérico y guión bajo."""
    return "".join(c if c.isalnum() or c == "_" else "_" for c in (key or "").strip())


def _get_goals_registry_fallback_first() -> Optional[Any]:
    """Compatibility hook: goals registry must not fallback to filesystem manifests."""
    return None


def list_goal_signal_autocomplete(
    db: Any,
    *,
    tenant_id: str,
    worker_id: str,
) -> list[dict[str, Any]]:
    """Stub RO para autocompletar metas /goals desde señales de calidad DB-first."""
    from duckclaw.worker_quality_signals import list_worker_quality_signal_options

    return [
        {
            "key": option.key,
            "label": option.label,
            "target": option.target,
            "threshold": option.threshold,
            "comparison": option.comparison,
        }
        for option in list_worker_quality_signal_options(
            db,
            tenant_id=str(tenant_id or "default").strip() or "default",
            worker_id=str(worker_id or "").strip(),
        )
    ]


def _get_goals_registry_for_chat(
    db: Any,
    chat_id: Any,
    *,
    tenant_id: str = "default",
    worker_id: str = "",
) -> Optional[Any]:
    """Return DB-first quality signals as a homeostasis belief registry."""
    from duckclaw.homeostasis.belief_registry import Belief, BeliefRegistry
    from duckclaw.worker_quality_signals import list_worker_quality_signals

    wid = (worker_id or get_chat_state(db, chat_id, "worker_id") or "").strip()
    if not wid:
        return _get_goals_registry_fallback_first()
    signals = list_worker_quality_signals(
        db,
        tenant_id=str(tenant_id or "default").strip() or "default",
        worker_id=wid,
    )
    if not signals:
        return _get_goals_registry_fallback_first()
    return BeliefRegistry(
        beliefs=[
            Belief(
                key=signal.key,
                target=float(signal.target),
                threshold=float(signal.threshold),
                comparison=signal.comparison,
            )
            for signal in signals
        ],
        actions={},
    )


def get_manager_goals(db: Any, chat_id: Any) -> list:
    """Goals del chat guardados por el manager. Por defecto vacío."""
    raw = get_chat_state(db, chat_id, "goals")
    if not raw:
        return []
    try:
        out = json.loads(raw)
        return out if isinstance(out, list) else []
    except Exception:
        return []


def set_manager_goals(db: Any, chat_id: Any, goals: list) -> None:
    """Guarda la lista legacy de goals del chat en agent_config."""
    set_chat_state(db, chat_id, "goals", json.dumps(goals))


def _goal_title(goal: dict, fallback_key: str) -> str:
    """Título resumen del goal para listados."""
    t = (goal.get("title") or "").strip()
    if t:
        return t[:80] + ("…" if len((goal.get("title") or "").strip()) > 80 else "")
    return (goal.get("belief_key") or fallback_key or "").strip()


def _extract_json_object(content: str) -> str:
    start = content.find("{")
    end = content.rfind("}") + 1
    if start >= 0 and end > start:
        return content[start:end]
    return content


def _natural_language_goal_to_params(db: Any, chat_id: Any, text: str) -> Optional[dict]:
    """Convierte un objetivo en lenguaje natural a parámetros homeostasis con el LLM configurado."""
    text = (text or "").strip()[:500]
    if not text or _goals_llm_triplet_resolver is None:
        return None
    try:
        from duckclaw.integrations.llm_providers import build_llm
        from langchain_core.messages import HumanMessage

        provider, model, base_url = _goals_llm_triplet_resolver(db, chat_id)
        llm = build_llm(provider, model, base_url, prefer_env_provider=False)
        if llm is None:
            return None
        prompt = (
            "Convierte este objetivo en lenguaje natural a parámetros para homeostasis (Active Inference). "
            "Responde ÚNICAMENTE un JSON válido con estas claves: belief_key (slug en snake_case, inglés o español), "
            "target_value (número; 0 si el objetivo es minimizar o cualitativo), threshold (número >= 0, tolerancia), "
            "title (resumen corto en español, máx 60 caracteres). Sin explicación, solo el JSON.\n\nObjetivo: "
        ) + text
        resp = llm.invoke([HumanMessage(content=prompt)])
        content = (getattr(resp, "content", None) or "").strip()
        if not content:
            return None
        data = json.loads(_extract_json_object(content))
        if not isinstance(data, dict):
            return None
        key = (data.get("belief_key") or "").strip() or _normalize_belief_key(text)
        key = _normalize_belief_key(key) or "objetivo"
        target = float(data.get("target_value", 0))
        thresh = max(0.0, float(data.get("threshold", 0)))
        title = (data.get("title") or text)[:120].strip()
        return {"belief_key": key, "target_value": target, "threshold": thresh, "title": title}
    except Exception:
        return None


def _default_vault_user_id_resolver(
    db: Any,
    *,
    vault_user_id: Any = None,
    chat_id: Any = None,
    tenant_id: str = "default",
) -> str:
    from duckclaw.vaults import resolve_user_id_for_db_path

    vault = str(Path(getattr(db, "_path", "") or "").expanduser().resolve())
    if not vault:
        return str(vault_user_id or chat_id or tenant_id or "default")
    tid = str(tenant_id or "default").strip() or "default"
    for candidate in (vault_user_id, chat_id, tid):
        uid = resolve_user_id_for_db_path(candidate, vault, tenant_id=tid)
        if uid:
            return uid
    return str(vault_user_id or chat_id or tid or "default")


def _persist_homeostasis_manifest_db(
    db: Any,
    chat_id: Any,
    tenant_id: str,
    manifest: Any,
    *,
    vault_user_id: Any = None,
) -> tuple[bool, str]:
    from harness_core.targets import save_homeostasis_manifest

    vault = str(Path(getattr(db, "_path", "") or "").expanduser().resolve())
    if not vault:
        return False, "vault_db_path missing"
    resolver = _goals_vault_user_id_resolver or _default_vault_user_id_resolver
    uid = resolver(
        db,
        vault_user_id=vault_user_id,
        chat_id=chat_id,
        tenant_id=tenant_id,
    )
    # Prefer sync write when vault handle is RW (worker / fly). Skip async enqueue when
    # sync succeeded — duplicate UPSERTs contend on DuckDB lock with gateway sessions.
    sync_ok = _try_sync_write_homeostasis_manifest(db, tenant_id, manifest)
    if sync_ok:
        return True, ""
    queued = save_homeostasis_manifest(
        tenant_id=tenant_id,
        user_id=uid,
        target_db_path=vault,
        manifest=manifest,
    )
    if queued:
        return True, ""
    return False, "cola meditate/homeostasis no disponible y vault RO"


def _try_sync_write_homeostasis_manifest(db: Any, tenant_id: str, manifest: Any) -> bool:
    """Write harness_core.homeostasis_targets when the DuckClaw handle is writable."""
    if bool(getattr(db, "_read_only", False)):
        return False
    tid = str(tenant_id or "default").strip() or "default"
    try:
        payload = json.dumps(
            manifest.model_dump() if hasattr(manifest, "model_dump") else manifest,
            ensure_ascii=False,
            default=str,
        )
    except Exception:
        return False
    try:
        # Ensure schema + upsert (same shape as db-writer meditate_state_delta).
        for stmt in (
            "CREATE SCHEMA IF NOT EXISTS harness_core",
            """
            CREATE TABLE IF NOT EXISTS harness_core.homeostasis_targets (
              tenant_id VARCHAR PRIMARY KEY,
              targets_json JSON,
              updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
        ):
            if hasattr(db, "execute"):
                db.execute(stmt)
            elif hasattr(db, "query"):
                db.query(stmt)
            else:
                return False
        upsert = (
            "INSERT INTO harness_core.homeostasis_targets (tenant_id, targets_json) "
            "VALUES (?, ?) "
            "ON CONFLICT (tenant_id) DO UPDATE SET "
            "targets_json = excluded.targets_json, updated_at = now()"
        )
        if hasattr(db, "execute"):
            db.execute(upsert, [tid, payload])
        else:
            # fallback: escape via single-quote JSON string
            esc_tid = tid.replace("'", "''")
            esc_payload = payload.replace("'", "''")
            db.query(
                "INSERT INTO harness_core.homeostasis_targets (tenant_id, targets_json) "
                f"VALUES ('{esc_tid}', '{esc_payload}'::JSON) "
                "ON CONFLICT (tenant_id) DO UPDATE SET "
                "targets_json = excluded.targets_json, updated_at = now()"
            )
        return True
    except Exception:
        return False


def _clear_legacy_manager_goals(db: Any, chat_id: Any) -> None:
    """Drop agent_config goals so migrate_legacy cannot revive deleted metas."""
    try:
        set_manager_goals(db, chat_id, [])
    except Exception:
        pass


def _resolve_goal_id(manifest: Any, token: str) -> str | None:
    """Resuelve goal-id: índice 1-based (orden prioridad), belief_key o título exacto."""
    from harness_core.goal_priority import sort_goals_by_priority

    t = (token or "").strip()
    if not t:
        return None
    goals = sort_goals_by_priority(list(manifest.goals or []))
    if t.isdigit():
        idx = int(t)
        if 1 <= idx <= len(goals):
            return (goals[idx - 1].belief_key or "").strip() or None
    norm = _normalize_belief_key(t)
    for g in goals:
        key = (g.belief_key or "").strip()
        if key == t or _normalize_belief_key(key) == norm:
            return key
    title_low = t.lower()
    for g in goals:
        if (g.title or "").strip().lower() == title_low:
            return (g.belief_key or "").strip() or None
    return None


def _apply_goals_rm(manifest: Any, target: str) -> tuple[Any, str | None]:
    """Aplica rm all o rm goal_id. Devuelve (manifest, error); error None si OK."""
    tgt = (target or "").strip()
    if tgt.lower() == "all":
        if not manifest.goals:
            return manifest, "No hay metas de dominio que eliminar."
        updated = manifest.model_copy(update={"goals": []})
        return updated, None
    key_rm = _resolve_goal_id(manifest, tgt)
    if not key_rm:
        return manifest, f"No encontré meta `{tgt}` en el manifiesto."
    new_goals = [g for g in manifest.goals if (g.belief_key or "").strip() != key_rm]
    if len(new_goals) == len(manifest.goals):
        return manifest, f"No encontré meta `{tgt}` en el manifiesto."
    return manifest.model_copy(update={"goals": new_goals}), None


def _apply_goals_kind(manifest: Any, target: str, *, goal_kind: str) -> tuple[Any, str | None]:
    """Marca meta como monitor (revisión continua) o task (discreta)."""
    tgt = (target or "").strip()
    if not tgt:
        return manifest, "Falta goal_id."
    key = _resolve_goal_id(manifest, tgt)
    if not key:
        return manifest, f"No encontré meta `{tgt}` en el manifiesto."
    found = False
    new_goals = []
    for g in manifest.goals:
        if (g.belief_key or "").strip() == key:
            found = True
            new_goals.append(g.model_copy(update={"goal_kind": goal_kind}))
        else:
            new_goals.append(g)
    if not found:
        return manifest, f"No encontré meta `{tgt}` en el manifiesto."
    return manifest.model_copy(update={"goals": new_goals}), None


def _apply_goals_priority(manifest: Any, target: str, priority: int) -> tuple[Any, str | None]:
    """Asigna prioridad numérica (1 = atender primero)."""
    tgt = (target or "").strip()
    if not tgt:
        return manifest, "Falta goal_id."
    if priority < 1:
        return manifest, "Prioridad debe ser un entero >= 1."
    key = _resolve_goal_id(manifest, tgt)
    if not key:
        return manifest, f"No encontré meta `{tgt}` en el manifiesto."
    found = False
    new_goals = []
    for g in manifest.goals:
        if (g.belief_key or "").strip() == key:
            found = True
            new_goals.append(g.model_copy(update={"priority": priority}))
        else:
            new_goals.append(g)
    if not found:
        return manifest, f"No encontré meta `{tgt}` en el manifiesto."
    return manifest.model_copy(update={"goals": new_goals}), None


def _format_homeostasis_manifest_listing(
    db: Any,
    chat_id: Any,
    manifest: Any,
    *,
    registry: Any = None,
) -> str:
    from duckclaw.homeostasis.surprise import compute_surprise
    from harness_core.goal_priority import goal_priority_display, sort_goals_by_priority

    lines = ["Manifiesto homeostasis", ""]
    reg = registry if registry is not None else _get_goals_registry_for_chat(db, chat_id)
    key_to_belief = {b.key.strip(): b for b in (reg.beliefs if reg else [])}
    lines.append("Metas / señales de calidad (menor P = atender antes):")
    sorted_goals = sort_goals_by_priority(list(manifest.goals or []))
    if not sorted_goals:
        lines.append("- (ninguna). Añade con /goals <objetivo>")
    else:
        for rank, g in enumerate(sorted_goals, start=1):
            key = (g.belief_key or "").strip()
            b = key_to_belief.get(key)
            target = float(g.target_value)
            thresh = float(g.threshold)
            if b is not None:
                target = float(b.target) if b.target is not None else target
                thresh = float(b.threshold) if b.threshold is not None else thresh
            observed = g.observed_value
            title = _goal_title(g.model_dump(), key)
            comp = getattr(b, "comparison", "symmetric") if b is not None else "symmetric"
            id_label = f"**{key}**" if key else "(sin id)"
            kind = getattr(g, "goal_kind", None) or "task"
            kind_tag = " · tipo=monitor" if kind == "monitor" else ""
            prio_tag = f"**{goal_priority_display(g, rank=rank)}** · "
            if observed is not None and (target != 0 or thresh != 0):
                res = compute_surprise(float(observed), target, thresh, comparison=comp)
                st = "⚠️" if res.is_anomaly else "✓"
                lines.append(
                    f"- {prio_tag}{id_label} · {title}{kind_tag}: target={target} (obs: {observed}) {st}"
                )
            else:
                lines.append(
                    f"- {prio_tag}{id_label} · {title}{kind_tag}: target={target}, thresh={thresh} (sin dato)"
                )
    infra = manifest.infra
    lines.append("")
    lines.append("Umbrales infra (contraste /loop):")
    lines.append(f"- error_rate_pct ≤ {infra.error_rate_pct}")
    lines.append(f"- stale_tasks_count ≤ {infra.stale_tasks_count}")
    lines.append(f"- memory_fragmentation_index ≤ {infra.memory_fragmentation_index}")
    lines.append(f"- avg_latency_ms ≤ {infra.avg_latency_ms}")
    lines.append(f"- db_lock_events ≤ {infra.db_lock_events}")
    return "\n".join(lines)


def execute_homeostasis_goals(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    tenant_id: Any = None,
    vault_user_id: Any = None,
) -> str:
    """/goals — CRUD del manifiesto homeostasis (metas + umbrales infra) contrastado por /loop."""
    from harness_core.goal_priority import assign_sequential_priorities, next_goal_priority
    from harness_core.states.loop_state import DomainGoal, HomeostasisManifest
    from harness_core.targets import load_homeostasis_manifest, set_infra_field

    tid = str(tenant_id or "default").strip() or "default"
    registry = _get_goals_registry_for_chat(db, chat_id, tenant_id=tid)
    raw = (args or "").strip()
    toks = raw.split()
    manifest = load_homeostasis_manifest(db, tid, chat_id=chat_id)

    if toks and toks[0] == "--migrate":
        manifest = load_homeostasis_manifest(db, tid, chat_id=chat_id, migrate_legacy=False)
        legacy = get_manager_goals(db, chat_id)
        if not legacy:
            return "No hay metas legacy en agent_config para migrar."
        if manifest.goals:
            return f"El manifiesto ya tiene {len(manifest.goals)} meta(s). Usa /goals --reset antes de migrar."
        goals = []
        for g in legacy:
            if not isinstance(g, dict) or not (g.get("belief_key") or "").strip():
                continue
            gk_raw = str(g.get("goal_kind") or "task").strip().lower()
            goal_kind = "monitor" if gk_raw == "monitor" else "task"
            goals.append(
            DomainGoal(
                belief_key=str(g.get("belief_key") or ""),
                target_value=float(g.get("target_value") or 0),
                threshold=float(g.get("threshold") or 0),
                title=str(g.get("title") or g.get("belief_key") or ""),
                goal_kind=goal_kind,
                observed_value=(
                    float(g["observed_value"]) if g.get("observed_value") is not None else None
                ),
                priority=int(g.get("priority") or 100),
            )
            )
        goals = assign_sequential_priorities(goals)  # type: ignore[arg-type]
        manifest = manifest.model_copy(update={"goals": goals})
        ok, err = _persist_homeostasis_manifest_db(
            db, chat_id, tid, manifest, vault_user_id=vault_user_id
        )
        if not ok:
            return f"Migración falló: {err}"
        return f"✅ Migradas {len(goals)} meta(s) desde agent_config al manifiesto homeostasis."

    if toks and toks[0] == "--reset":
        manifest = HomeostasisManifest()
        ok, err = _persist_homeostasis_manifest_db(
            db, chat_id, tid, manifest, vault_user_id=vault_user_id
        )
        if not ok:
            return f"No se pudo resetear: {err}"
        _clear_legacy_manager_goals(db, chat_id)
        return "✅ Manifiesto homeostasis restaurado a defaults. Añade metas con /goals <objetivo>."

    if toks and toks[0] in ("rm", "--rm"):
        if len(toks) < 2:
            return "Uso: /goals rm <goal_id> · /goals rm all"
        target = " ".join(toks[1:]).strip()
        removed_count = len(manifest.goals)
        key_for_msg = target
        if target.lower() == "all":
            updated, err = _apply_goals_rm(manifest, "all")
            if err:
                return err
            ok, err_save = _persist_homeostasis_manifest_db(
                db, chat_id, tid, updated, vault_user_id=vault_user_id
            )
            if not ok:
                return f"No se pudo guardar: {err_save}"
            _clear_legacy_manager_goals(db, chat_id)
            return f"✅ Eliminadas {removed_count} meta(s) del manifiesto."
        key_resolved = _resolve_goal_id(manifest, target)
        updated, err = _apply_goals_rm(manifest, target)
        if err:
            return err
        ok, err_save = _persist_homeostasis_manifest_db(
            db, chat_id, tid, updated, vault_user_id=vault_user_id
        )
        if not ok:
            return f"No se pudo guardar: {err_save}"
        if not updated.goals:
            _clear_legacy_manager_goals(db, chat_id)
        return f"✅ Meta `{key_resolved or key_for_msg}` eliminada del manifiesto."

    if toks and toks[0] == "--set" and len(toks) >= 3:
        field = toks[1].strip()
        try:
            val: Any = float(toks[2])
            if field == "stale_tasks_count" or field == "db_lock_events":
                val = int(val)
            manifest = set_infra_field(manifest, field, val)
        except ValueError as exc:
            return str(exc)
        ok, err = _persist_homeostasis_manifest_db(
            db, chat_id, tid, manifest, vault_user_id=vault_user_id
        )
        if not ok:
            return f"No se pudo guardar: {err}"
        return f"✅ Umbral infra `{field}` = {val}"

    if toks and toks[0] == "--monitor":
        if len(toks) < 2:
            return "Uso: /goals --monitor <goal_id>"
        target = " ".join(toks[1:]).strip()
        key_resolved = _resolve_goal_id(manifest, target)
        updated, err = _apply_goals_kind(manifest, target, goal_kind="monitor")
        if err:
            return err
        ok, err_save = _persist_homeostasis_manifest_db(
            db, chat_id, tid, updated, vault_user_id=vault_user_id
        )
        if not ok:
            return f"No se pudo guardar: {err_save}"
        kid = key_resolved or target
        return f"✅ Meta `{kid}` marcada como monitor (revisión continua)."

    if toks and toks[0] == "--task":
        if len(toks) < 2:
            return "Uso: /goals --task <goal_id>"
        target = " ".join(toks[1:]).strip()
        key_resolved = _resolve_goal_id(manifest, target)
        updated, err = _apply_goals_kind(manifest, target, goal_kind="task")
        if err:
            return err
        ok, err_save = _persist_homeostasis_manifest_db(
            db, chat_id, tid, updated, vault_user_id=vault_user_id
        )
        if not ok:
            return f"No se pudo guardar: {err_save}"
        kid = key_resolved or target
        return f"✅ Meta `{kid}` marcada como tarea discreta (goal_kind=task)."

    if toks and toks[0] == "--priority":
        if len(toks) < 3:
            return "Uso: /goals --priority <goal_id> <n>  (1 = mayor prioridad)"
        try:
            prio = int(toks[-1])
        except ValueError:
            return "Prioridad debe ser un entero >= 1."
        target = " ".join(toks[1:-1]).strip()
        key_resolved = _resolve_goal_id(manifest, target)
        updated, err = _apply_goals_priority(manifest, target, prio)
        if err:
            return err
        ok, err_save = _persist_homeostasis_manifest_db(
            db, chat_id, tid, updated, vault_user_id=vault_user_id
        )
        if not ok:
            return f"No se pudo guardar: {err_save}"
        kid = key_resolved or target
        listing = _format_homeostasis_manifest_listing(
            db, chat_id, updated, registry=registry
        )
        return (
            f"✅ Meta `{kid}` → **P{prio}** (menor número = atender antes).\n\n{listing}"
        )

    if raw and not raw.startswith("--") and toks[0] != "rm":
        key_norm = _normalize_belief_key(raw)
        belief = None
        if registry:
            belief = registry.get_belief(raw.strip())
            if not belief:
                for b in registry.beliefs:
                    if _normalize_belief_key(b.key) == key_norm:
                        belief = b
                        break
        if belief:
            new_goal = DomainGoal(
                belief_key=belief.key,
                target_value=float(belief.target),
                threshold=float(belief.threshold),
                title=belief.key,
                priority=next_goal_priority(manifest.goals),
            )
        else:
            params = _natural_language_goal_to_params(db, chat_id, raw)
            if params:
                new_goal = DomainGoal(
                    belief_key=params["belief_key"],
                    target_value=float(params["target_value"]),
                    threshold=float(params["threshold"]),
                    title=str(params.get("title") or params["belief_key"]),
                    priority=next_goal_priority(manifest.goals),
                )
            else:
                new_goal = DomainGoal(
                    belief_key=key_norm or "objetivo",
                    target_value=0.0,
                    threshold=0.0,
                    title=raw[:120].strip(),
                    priority=next_goal_priority(manifest.goals),
                )
        goals = [g for g in manifest.goals if (g.belief_key or "").strip() != new_goal.belief_key]
        goals.append(new_goal)
        manifest = manifest.model_copy(update={"goals": goals})
        ok, err = _persist_homeostasis_manifest_db(
            db, chat_id, tid, manifest, vault_user_id=vault_user_id
        )
        if not ok:
            return f"No se pudo guardar manifiesto: {err}"
        title_display = new_goal.title or new_goal.belief_key
        return (
            f"✅ Meta homeostasis añadida: {title_display} "
            f"(prioridad P{new_goal.priority})"
        )

    return (
        _format_homeostasis_manifest_listing(db, chat_id, manifest, registry=registry)
        + "\n\nUso: /goals <objetivo> · /goals --set error_rate_pct 2 · "
        "/goals rm <goal_id> · /goals rm all · /goals --priority <goal_id> <n> · "
        "/goals --monitor <goal_id> · "
        "/goals --task <goal_id> · /goals --migrate · /goals --reset"
    )
