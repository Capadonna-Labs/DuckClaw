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
    """Primer template con homeostasis (orden del FS); solo como fallback."""
    try:
        from duckclaw.forge.homeostasis.belief_registry import BeliefRegistry
        from duckclaw.workers.factory import list_workers
        from duckclaw.workers.manifest import load_manifest

        for wid in list_workers():
            try:
                spec = load_manifest(wid)
                config = getattr(spec, "homeostasis_config", None) or {}
                registry = BeliefRegistry.from_config(config)
                if registry.beliefs:
                    return registry
            except Exception:
                continue
    except Exception:
        pass
    return None


def _get_goals_registry_for_chat(db: Any, chat_id: Any) -> Optional[Any]:
    """Registro homeostasis del worker activo del chat; fallback al primer template con YAML."""
    from duckclaw.forge.homeostasis.belief_registry import BeliefRegistry
    from duckclaw.workers.manifest import load_manifest

    wid = (get_chat_state(db, chat_id, "worker_id") or "").strip()
    if wid and wid.lower() != "manager":
        try:
            spec = load_manifest(wid)
            config = getattr(spec, "homeostasis_config", None) or {}
            registry = BeliefRegistry.from_config(config)
            if registry.beliefs:
                return registry
        except Exception:
            pass
    return _get_goals_registry_fallback_first()


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
    ok = save_homeostasis_manifest(
        tenant_id=tenant_id,
        user_id=uid,
        target_db_path=vault,
        manifest=manifest,
    )
    return (True, "") if ok else (False, "cola meditate/homeostasis no disponible")


def _format_homeostasis_manifest_listing(
    db: Any,
    chat_id: Any,
    manifest: Any,
    *,
    registry: Any = None,
) -> str:
    from duckclaw.forge.homeostasis.surprise import compute_surprise

    lines = ["Manifiesto homeostasis", ""]
    reg = registry if registry is not None else _get_goals_registry_for_chat(db, chat_id)
    key_to_belief = {b.key.strip(): b for b in (reg.beliefs if reg else [])}
    lines.append("Metas de dominio:")
    if not manifest.goals:
        lines.append("- (ninguna). Añade con /goals <objetivo>")
    else:
        for g in manifest.goals:
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
            if observed is not None and (target != 0 or thresh != 0):
                res = compute_surprise(float(observed), target, thresh, comparison=comp)
                st = "⚠️" if res.is_anomaly else "✓"
                lines.append(f"- {title}: target={target} (obs: {observed}) {st}")
            else:
                lines.append(f"- {title}: target={target}, thresh={thresh} (sin dato)")
    infra = manifest.infra
    lines.append("")
    lines.append("Umbrales infra (contraste /meditate):")
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
    """/goals — CRUD del manifiesto homeostasis (metas + umbrales infra) contrastado por /meditate."""
    from harness_core.states.meditate_state import DomainGoal, HomeostasisManifest
    from harness_core.targets import load_homeostasis_manifest, set_infra_field

    tid = str(tenant_id or "default").strip() or "default"
    registry = _get_goals_registry_for_chat(db, chat_id)
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
        goals = [
            DomainGoal(
                belief_key=str(g.get("belief_key") or ""),
                target_value=float(g.get("target_value") or 0),
                threshold=float(g.get("threshold") or 0),
                title=str(g.get("title") or g.get("belief_key") or ""),
                observed_value=(
                    float(g["observed_value"]) if g.get("observed_value") is not None else None
                ),
            )
            for g in legacy
            if isinstance(g, dict) and (g.get("belief_key") or "").strip()
        ]
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
        return "✅ Manifiesto homeostasis restaurado a defaults. Añade metas con /goals <objetivo>."

    if toks and toks[0] == "--rm" and len(toks) >= 2:
        key_rm = _normalize_belief_key(" ".join(toks[1:]))
        new_goals = [g for g in manifest.goals if (g.belief_key or "").strip() != key_rm]
        if len(new_goals) == len(manifest.goals):
            return f"No encontré meta `{key_rm}` en el manifiesto."
        manifest = manifest.model_copy(update={"goals": new_goals})
        ok, err = _persist_homeostasis_manifest_db(
            db, chat_id, tid, manifest, vault_user_id=vault_user_id
        )
        if not ok:
            return f"No se pudo guardar: {err}"
        return f"✅ Meta `{key_rm}` eliminada del manifiesto."

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

    if raw and not raw.startswith("--"):
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
            )
        else:
            params = _natural_language_goal_to_params(db, chat_id, raw)
            if params:
                new_goal = DomainGoal(
                    belief_key=params["belief_key"],
                    target_value=float(params["target_value"]),
                    threshold=float(params["threshold"]),
                    title=str(params.get("title") or params["belief_key"]),
                )
            else:
                new_goal = DomainGoal(
                    belief_key=key_norm or "objetivo",
                    target_value=0.0,
                    threshold=0.0,
                    title=raw[:120].strip(),
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
        return f"✅ Meta homeostasis añadida: {title_display}"

    return (
        _format_homeostasis_manifest_listing(db, chat_id, manifest, registry=registry)
        + "\n\nUso: /goals <objetivo> · /goals --set error_rate_pct 2 · /goals --rm <key> · "
        "/goals --migrate · /goals --reset"
    )
