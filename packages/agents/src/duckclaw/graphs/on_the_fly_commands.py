"""
On-the-Fly CLI: comandos de Telegram que mutan estado del grafo sin reiniciar.

Spec: specs/interfaz_de_comandos_dinamicos_On-the-Fly_CLI.md
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Optional, Tuple

_PREFIX = "chat_"

# Caracteres que Telegram Markdown/MarkdownV2 interpretan; escapar para evitar "Can't find end of entity"
# MarkdownV2 requiere: _ * [ ] ( ) ~ ` > # + - = | { } . !
_TELEGRAM_MD_ESCAPE = ("\\", "_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!")


def _telegram_safe(text: str) -> str:
    """Escapa caracteres para que el texto sea seguro con parse_mode=Markdown o MarkdownV2 en Telegram."""
    if not text:
        return ""
    t = str(text)
    # Escapar backslash primero para evitar doble escape
    t = t.replace("\\", "\\\\")
    for c in _TELEGRAM_MD_ESCAPE:
        if c == "\\":
            continue
        t = t.replace(c, "\\" + c)
    return t


def _chat_key(chat_id: Any, suffix: str) -> str:
    """Key for agent_config; supports numeric (Telegram) and string (API session_id)."""
    try:
        cid = int(chat_id)
        return f"{_PREFIX}{cid}_{suffix}"
    except (TypeError, ValueError):
        return f"{_PREFIX}{str(chat_id)[:64]}_{suffix}"


_AGENT_CONFIG_TABLE = "agent_config"


def _ensure_agent_config(db: Any) -> None:
    db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_AGENT_CONFIG_TABLE} (
            key VARCHAR PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def get_chat_state(db: Any, chat_id: Any, key: str) -> str:
    """Read a chat-scoped config key from agent_config."""
    _ensure_agent_config(db)
    k = _chat_key(chat_id, key).replace("'", "''")[:200]
    try:
        r = db.query(f"SELECT value FROM {_AGENT_CONFIG_TABLE} WHERE key = '{k}' LIMIT 1")
        rows = json.loads(r) if isinstance(r, str) else (r or [])
        if rows and isinstance(rows[0], dict):
            return (rows[0].get("value") or "").strip()
    except Exception:
        pass
    return ""


def set_chat_state(db: Any, chat_id: Any, key: str, value: str) -> None:
    """Write a chat-scoped config key to agent_config."""
    _ensure_agent_config(db)
    k = _chat_key(chat_id, key).replace("'", "''")[:128]
    v = str(value).replace("'", "''")[:16384]
    db.execute(
        f"""
        INSERT INTO {_AGENT_CONFIG_TABLE} (key, value) VALUES ('{k}', '{v}')
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """
    )


def parse_command(text: str) -> Tuple[str, str]:
    """Parse /command or /command args. Returns (name, args)."""
    if not text or not text.strip().startswith("/"):
        return "", ""
    parts = text.strip().split(maxsplit=1)
    name = (parts[0] or "").lstrip("/").lower()
    args = (parts[1] if len(parts) > 1 else "").strip()
    return name, args


def get_team_templates(db: Any, chat_id: Any) -> list:
    """Templates disponibles en el equipo para este chat. Vacío = todos los de list_workers()."""
    raw = get_chat_state(db, chat_id, "team_templates")
    if not raw:
        return []
    try:
        out = json.loads(raw)
        return out if isinstance(out, list) else []
    except Exception:
        return []


def set_team_templates(db: Any, chat_id: Any, template_ids: list) -> None:
    """Define los templates del equipo para este chat. Lista vacía = usar todos (list_workers)."""
    set_chat_state(db, chat_id, "team_templates", json.dumps([str(x).strip().lower() for x in template_ids]))


def execute_team(db: Any, chat_id: Any, args: str) -> str:
    """/team [id1 id2 ...] [--add id...] [--rm worker_id]: equipo del chat. Sin args: lista. Con ids: reemplaza. --add: añade; --rm: quita uno."""
    from duckclaw.workers.factory import list_workers
    all_templates = list_workers()
    team = get_team_templates(db, chat_id)
    if not args or not args.strip():
        display_list = team if team else all_templates
        if not display_list:
            return _telegram_safe("No hay templates en forge/templates. Añade al menos uno.")
        label = _telegram_safe("Equipo (este chat):") if team else _telegram_safe("Equipo: todos los templates")
        lines = "\n".join(f"\\- {_telegram_safe(w)}" for w in display_list)
        hint = _telegram_safe("Reemplazar: /team id1 id2 | Añadir: /team --add id | Quitar: /team --rm id | Ver todos: /roles")
        return f"🦆 {label}\n{lines}\n\n{hint}"
    raw = args.strip()
    # --rm <worker_id>
    if raw.startswith("--rm "):
        wid = raw[5:].strip().lower().split()[0]
        current = team if team else list(all_templates)
        if wid not in current:
            return _telegram_safe(f"'{wid}' no está en el equipo. Equipo actual: {', '.join(current) or 'todos'}")
        new_team = [x for x in current if x != wid]
        set_team_templates(db, chat_id, new_team)
        return _telegram_safe(f"✅ Quitado {wid} del equipo. Quedan: {', '.join(new_team) or 'ninguno (el manager usará todos)'}.")
    # --add id1 id2 ... (insert/appendix al equipo actual)
    if raw.startswith("--add ") or raw.strip() == "--add":
        ids_str = raw[6:].strip() if raw.startswith("--add ") else ""
        ids = [x.strip().lower() for x in ids_str.split() if x.strip()]
        valid = [i for i in ids if i in all_templates]
        invalid = [i for i in ids if i not in all_templates]
        if invalid:
            return _telegram_safe(f"Templates no encontrados: {', '.join(invalid)}. Disponibles: {', '.join(all_templates)}")
        current = team if team else list(all_templates)
        for i in valid:
            if i not in current:
                current.append(i)
        set_team_templates(db, chat_id, current)
        return _telegram_safe(f"✅ Añadidos al equipo: {', '.join(valid)}. Equipo: {', '.join(current)}.")
    # id1 id2 ... → reemplazar equipo
    ids = [x.strip().lower() for x in raw.split() if x.strip()]
    valid = [i for i in ids if i in all_templates]
    invalid = [i for i in ids if i not in all_templates]
    if invalid:
        return _telegram_safe(f"Templates no encontrados: {', '.join(invalid)}. Disponibles: {', '.join(all_templates)}")
    set_team_templates(db, chat_id, valid)
    return _telegram_safe(f"✅ Equipo de este chat: {', '.join(valid)}. El manager delegará solo a estos.")


def execute_roles(db: Any, chat_id: Any) -> str:
    """/roles: lista todos los trabajadores virtuales (templates) disponibles. El manager solo delegará a los que estén en /team."""
    from duckclaw.workers.factory import list_workers
    all_templates = list_workers()
    if not all_templates:
        return _telegram_safe("No hay templates en forge/templates. Añade al menos uno.")
    lines = "\n".join(f"\\- {_telegram_safe(w)}" for w in all_templates)
    return (
        f"🦆 {_telegram_safe('Trabajadores virtuales (templates) disponibles:')}\n\n{lines}\n\n"
        f"{_telegram_safe('El manager solo delegará a los que estén en tu equipo. Para añadirlos: /team id1 id2 ...')}"
    )


# Worker por defecto: el manager orquesta y delega a los trabajadores en forge/templates
_DEFAULT_WORKER = "manager"


def execute_role_switch(db: Any, chat_id: Any, worker_id: str) -> str:
    """/role <worker_id>: cambia el rol. Por defecto 'manager' delega a los templates. Sin args: muestra rol actual y disponibles."""
    from duckclaw.workers.factory import list_workers
    available = list_workers()  # solo templates (finanz, research_worker, etc.)
    wid = (worker_id or "").strip().lower()
    if not wid:
        current = get_chat_state(db, chat_id, "worker_id") or _DEFAULT_WORKER
        if current == "manager":
            current_display = _telegram_safe("Manager (delega a trabajadores en templates)")
        else:
            try:
                from duckclaw.workers.manifest import load_manifest
                spec = load_manifest(current)
                current_display = _telegram_safe(f"{spec.name} ({current})")
            except Exception:
                current_display = _telegram_safe(current)
        avail_str = "\n".join(f"\\- {_telegram_safe(w)}" for w in available) if available else "ninguna"
        return f"🦆 {_telegram_safe('Rol:')} {current_display}\n\n{_telegram_safe('Disponibles:')} {_telegram_safe('manager (por defecto)')}\n{avail_str}\n{_telegram_safe('/role <id>')}"
    if wid == "manager":
        set_chat_state(db, chat_id, "worker_id", "manager")
        return _telegram_safe("✅ Manager. Delega a los trabajadores en templates.")
    if wid not in available:
        avail_str = "\n".join(f"\\- {_telegram_safe(w)}" for w in available) if available else "ninguna"
        return _telegram_safe(f"Rol '{wid}' no existe.") + f"\n{_telegram_safe('Disponibles:')}\n{avail_str}"
    try:
        from duckclaw.workers.manifest import load_manifest
        spec = load_manifest(wid)
        set_chat_state(db, chat_id, "worker_id", wid)
        skills = ", ".join(_telegram_safe(s) for s in (spec.skills_list or [])) or "run_sql"
        return _telegram_safe(f"✅ {spec.name} ({wid}). Herramientas: {skills}")
    except Exception as e:
        return f"Error al cargar rol: {e}."


def execute_skills_list(db: Any, chat_id: Any, args: str) -> str:
    """/skills <worker_id>: lista herramientas del template. worker_id debe ser uno de /roles."""
    from duckclaw.workers.factory import list_workers
    available = list_workers()
    wid = (args or "").strip().lower()
    if not wid:
        return _telegram_safe("Uso: /skills <worker_id>. Ver templates: /roles")
    if wid.startswith("--"):
        return _telegram_safe("Indica un worker_id (ej. finanz, research_worker). Ver templates: /roles")
    if wid not in available:
        return _telegram_safe(f"Template '{wid}' no encontrado. Disponibles (usa /roles): {', '.join(available)}")
    try:
        from duckclaw.workers.manifest import load_manifest
        spec = load_manifest(wid)
        skills_safe = [_telegram_safe(s) for s in (spec.skills_list or [])]
        lines = [f"\\- {s}" for s in skills_safe]
        lines.append(f"\\- {_telegram_safe('run_sql')}")
        return _telegram_safe(f"🔧 {spec.name} ({wid})\n") + "\n".join(lines)
    except Exception as e:
        return f"Error: {e}."


def execute_forget(db: Any, chat_id: Any) -> str:
    """/forget: borra historial de la conversación y reinicia estado."""
    try:
        cid = int(chat_id)
        # Telegram: chat_id is numeric, use telegram_conversation
        db.execute(f"DELETE FROM telegram_conversation WHERE chat_id = {cid}")
    except (TypeError, ValueError):
        # API gateway: session_id is string (e.g. "default"), use api_conversation
        sid = str(chat_id).replace("'", "''")[:256]
        try:
            db.execute(f"DELETE FROM api_conversation WHERE session_id = '{sid}'")
        except Exception:
            pass  # Table may not exist if only Telegram used
    try:
        set_chat_state(db, chat_id, "last_audit", "")
    except Exception:
        pass
    if os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true":
        try:
            import langsmith
            # Log evento Habeas Data (opcional: run_id no disponible aquí)
            pass
        except Exception:
            pass
    return _telegram_safe("✅ Historial borrado.")


def execute_context_toggle(db: Any, chat_id: Any, on_off: str) -> str:
    """/context on|off: activa o desactiva inyección de memoria a largo plazo."""
    v = (on_off or "").strip().lower()
    if v in ("on", "1", "true", "sí", "si"):
        set_chat_state(db, chat_id, "use_rag", "true")
        return _telegram_safe("✅ Contexto largo activado (más mensajes en historial).")
    if v in ("off", "0", "false"):
        set_chat_state(db, chat_id, "use_rag", "false")
        return _telegram_safe("✅ Contexto largo desactivado (solo historial reciente).")
    current = get_chat_state(db, chat_id, "use_rag")
    return _telegram_safe(f"Uso: /context on | /context off\nEstado actual: {'on' if current != 'false' else 'off'}.")


def execute_audit(db: Any, chat_id: Any) -> str:
    """/audit: evidencia de la última ejecución (SQL, latencia, run_id)."""
    raw = get_chat_state(db, chat_id, "last_audit")
    if not raw:
        return _telegram_safe("No hay evidencia de última ejecución. Envía un mensaje y vuelve a usar /audit.")
    try:
        data = json.loads(raw)
        sql = data.get("sql") or "(no registrado)"
        latency_ms = data.get("latency_ms") or "—"
        tokens = data.get("tokens") or "—"
        run_id = data.get("run_id") or "—"
        return _telegram_safe(
            f"📋 Última ejecución\nSQL: {str(sql)[:300]}\nLatencia: {latency_ms} ms\nTokens: {tokens}\nLangSmith run_id: {run_id}"
        )
    except Exception:
        return _telegram_safe("Datos de auditoría no válidos.")


def execute_health(db: Any) -> str:
    """/health: estado de infraestructura (MLX, DuckDB, latencia)."""
    lines = []
    # DuckDB
    try:
        db.query("SELECT 1")
        lines.append("✅ DuckDB: conectado")
    except Exception as e:
        lines.append(f"❌ DuckDB: {e}")
    # MLX / inference
    base_url = os.environ.get("DUCKCLAW_LLM_BASE_URL", "").strip() or "http://127.0.0.1:8080"
    if base_url:
        base = base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        url = base + "/health"
        try:
            import urllib.request
            t0 = time.perf_counter()
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                elapsed = int((time.perf_counter() - t0) * 1000)
                lines.append(f"✅ Inferencia ({url[:40]}...): {elapsed} ms")
        except Exception as e:
            lines.append(f"⚠️ Inferencia: {e}")
    return _telegram_safe("\n".join(lines) or "Sin comprobaciones.")


def execute_approve_reject(db: Any, chat_id: Any, approved: bool) -> str:
    """/approve o /reject: HITL (grafo en interrupt). Sin interrupt implementado: mensaje informativo."""
    return _telegram_safe("No hay operación pendiente de aprobación. (El grafo no está en estado interrupt en esta versión.)")


def _normalize_belief_key(key: str) -> str:
    """Normaliza key para DB: alfanumérico y guión bajo."""
    return "".join(c if c.isalnum() or c == "_" else "_" for c in (key or "").strip())


def _get_goals_registry_for_manager() -> Optional[Any]:
    """Registro de goals válidos para el manager (desde el primer template con homeostasis, ej. finanz)."""
    try:
        from duckclaw.workers.factory import list_workers
        from duckclaw.workers.manifest import load_manifest
        from duckclaw.forge.homeostasis.belief_registry import BeliefRegistry
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
    """Guarda la lista de goals del chat (manager). Cada item: belief_key, target_value, threshold, observed_value opcional, title (resumen)."""
    set_chat_state(db, chat_id, "goals", json.dumps(goals))


def _goal_title(goal: dict, fallback_key: str) -> str:
    """Título resumen del goal para listar en /goals."""
    t = (goal.get("title") or "").strip()
    if t:
        return t[:80] + ("…" if len((goal.get("title") or "").strip()) > 80 else "")
    return (goal.get("belief_key") or fallback_key or "").strip()


def _natural_language_goal_to_params(db: Any, chat_id: Any, text: str) -> Optional[dict]:
    """Convierte un objetivo en lenguaje natural a parámetros homeostasis (belief_key, target_value, threshold, title). Usa LLM del manager."""
    text = (text or "").strip()[:500]
    if not text:
        return None
    try:
        from langchain_core.messages import HumanMessage
        provider = get_chat_state(db, chat_id, "llm_provider") or _get_global_config(db, "llm_provider") or os.environ.get("DUCKCLAW_LLM_PROVIDER", "mlx")
        model = get_chat_state(db, chat_id, "llm_model") or _get_global_config(db, "llm_model") or os.environ.get("DUCKCLAW_LLM_MODEL", "")
        base_url = get_chat_state(db, chat_id, "llm_base_url") or _get_global_config(db, "llm_base_url") or os.environ.get("DUCKCLAW_LLM_BASE_URL", "http://127.0.0.1:8080")
        from duckclaw.integrations.llm_providers import build_llm
        llm = build_llm(provider, model, base_url)
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
        # Extraer JSON si viene envuelto en ```json ... ```
        if "```" in content:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                content = content[start:end]
        data = json.loads(content)
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


def execute_goals(db: Any, chat_id: Any, args: str) -> str:
    """/goals [--reset] | /goals <goal>: listar, resetear o añadir. Acepta clave (presupuesto_mensual) o lenguaje natural; el manager convierte a parámetros homeostasis."""
    from duckclaw.forge.homeostasis.surprise import compute_surprise
    registry = _get_goals_registry_for_manager()
    valid_keys = [b.key for b in (registry.beliefs if registry else [])]
    goals = get_manager_goals(db, chat_id)

    raw = (args or "").strip()
    do_reset = raw.lower() == "--reset"

    if do_reset:
        set_manager_goals(db, chat_id, [])
        return _telegram_safe("✅ Objetivos reiniciados. Crea con /goals <objetivo en lenguaje natural o clave>.")

    # Añadir: /goals <clave o lenguaje natural>
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
            new_goal = {
                "belief_key": belief.key,
                "target_value": belief.target,
                "threshold": belief.threshold,
                "observed_value": None,
                "title": belief.key,
            }
        else:
            # Lenguaje natural: manager convierte a parámetros homeostasis vía LLM
            params = _natural_language_goal_to_params(db, chat_id, raw)
            if params:
                new_goal = {
                    "belief_key": params["belief_key"],
                    "target_value": params["target_value"],
                    "threshold": params["threshold"],
                    "observed_value": None,
                    "title": params["title"],
                }
            else:
                new_goal = {
                    "belief_key": key_norm or "objetivo",
                    "target_value": 0.0,
                    "threshold": 0.0,
                    "observed_value": None,
                    "title": raw[:120].strip(),
                }
        existing = [g for g in goals if (g.get("belief_key") or "").strip() == new_goal["belief_key"]]
        if existing:
            goals = [g for g in goals if (g.get("belief_key") or "").strip() != new_goal["belief_key"]]
        goals.append(new_goal)
        set_manager_goals(db, chat_id, goals)
        title_display = _telegram_safe(new_goal.get("title") or new_goal["belief_key"])
        return _telegram_safe(f"✅ Objetivo añadido: {title_display}")

    # Listar (por defecto vacío)
    if not goals:
        return _telegram_safe("🎯 Manager\nNo hay goals. Crea con /goals <objetivo>, ej. /goals disminuir gasto en recreación.")

    lines = ["🎯 Manager"]
    try:
        key_to_belief = {b.key.strip(): b for b in (registry.beliefs if registry else [])}
        for g in goals:
            key = (g.get("belief_key") or "").strip()
            b = key_to_belief.get(key)
            target = float(g.get("target_value")) if g.get("target_value") is not None else None
            thresh = float(g.get("threshold")) if g.get("threshold") is not None else None
            if b is not None:
                target = target if target is not None else b.target
                thresh = thresh if thresh is not None else b.threshold
            try:
                observed = float(g.get("observed_value")) if g.get("observed_value") is not None else None
            except (TypeError, ValueError):
                observed = None
            title = _telegram_safe(_goal_title(g, key))
            if observed is not None and target is not None and thresh is not None and (target != 0 or thresh != 0):
                res = compute_surprise(observed, target, thresh)
                st = "⚠️" if res.is_anomaly else "✓"
                lines.append(f"\\- {title}: target={target} (obs: {observed}) {st}")
            elif target is not None and thresh is not None:
                lines.append(f"\\- {title}: target={target}, thresh={thresh} (sin dato)")
            else:
                lines.append(f"\\- {title}")
    except Exception as e:
        return _telegram_safe(f"Error: {e}.")
    return _telegram_safe("\n".join(lines) + "\n\n/goals --reset")


def execute_tasks(db: Any, chat_id: Any) -> str:
    """/tasks: estado del ActivityManager (Redis): IDLE, BUSY, subagente, tarea actual, tiempo en ejecución."""
    from duckclaw.graphs.activity import get_activity
    data = get_activity(chat_id)
    if data is None:
        return _telegram_safe("⏸ IDLE (Redis no configurado).")
    status = data.get("status", "IDLE")
    task = data.get("task", "")
    worker_id = data.get("worker_id", "") or ""
    started_at = data.get("started_at", 0)
    elapsed_s = ""
    if started_at and status == "BUSY":
        try:
            elapsed_s = f" · {int(time.time()) - int(started_at)}s"
        except Exception:
            pass
    worker_s = f" · {_telegram_safe(worker_id)}" if worker_id else ""
    task_preview = _telegram_safe(str(task)[:60]) if task else _telegram_safe("—")
    icon = "▶" if status == "BUSY" else "⏸"
    return _telegram_safe(f"{icon} {status}{elapsed_s}{worker_s}\n") + task_preview


def _get_global_config(db: Any, key: str) -> str:
    """Read a global config key from agent_config (e.g. system_prompt)."""
    _ensure_agent_config(db)
    k = str(key).replace("'", "''")[:128]
    try:
        r = db.query(f"SELECT value FROM {_AGENT_CONFIG_TABLE} WHERE key = '{k}' LIMIT 1")
        rows = json.loads(r) if isinstance(r, str) else (r or [])
        if rows and isinstance(rows[0], dict):
            return (rows[0].get("value") or "").strip()
    except Exception:
        pass
    return ""


def _set_global_config(db: Any, key: str, value: str) -> None:
    """Write a global config key to agent_config."""
    _ensure_agent_config(db)
    k = str(key).replace("'", "''")[:128]
    v = str(value).replace("'", "''")[:16384]
    db.execute(
        f"""
        INSERT INTO {_AGENT_CONFIG_TABLE} (key, value) VALUES ('{k}', '{v}')
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """
    )


def get_effective_system_prompt(db: Any, worker_id: Optional[str] = None) -> str:
    """
    Devuelve el system prompt efectivo para un worker:
    - Si worker_id está definido: 1) override system_prompt_<worker_id>, 2) system_prompt.md del template. No usa global.
    - Si worker_id vacío: global system_prompt o "".
    """
    wid = (worker_id or "").strip()
    if wid:
        override = _get_global_config(db, f"system_prompt_{wid}")
        if override:
            return override
        try:
            from duckclaw.workers.manifest import load_manifest
            from duckclaw.workers.loader import load_system_prompt
            spec = load_manifest(wid)
            return (load_system_prompt(spec) or "").strip()
        except Exception:
            pass
        return ""
    current = _get_global_config(db, "system_prompt")
    return current if current else ""


_PROVIDERS = ("mlx", "ollama", "openai", "anthropic", "deepseek", "groq")

# Modelo por defecto al cambiar provider (evita "Model Not Exist" al pasar de MLX a cloud)
_DEFAULT_MODEL_BY_PROVIDER = {
    "deepseek": "deepseek-chat",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-20241022",
    "groq": "llama-3.3-70b-versatile",
    "mlx": "",  # usa MLX_MODEL_ID o /v1/models
    "ollama": "llama3.2",
}


def execute_model(db: Any, chat_id: Any, args: str) -> str:
    """/model [provider=mlx] [model=...] [base_url=...]: cambia proveedor/modelo LLM en caliente. Sin args muestra el actual."""
    if not args or not args.strip():
        p = get_chat_state(db, chat_id, "llm_provider") or _get_global_config(db, "llm_provider")
        m = get_chat_state(db, chat_id, "llm_model") or _get_global_config(db, "llm_model")
        u = get_chat_state(db, chat_id, "llm_base_url") or _get_global_config(db, "llm_base_url")
        env_p = os.environ.get("DUCKCLAW_LLM_PROVIDER", "").strip()
        env_m = os.environ.get("DUCKCLAW_LLM_MODEL", "").strip()
        env_u = os.environ.get("DUCKCLAW_LLM_BASE_URL", "").strip()
        provider = p or env_p or "—"
        model = m or env_m or "—"
        base_url = (u or env_u or "—")[:50] + "…" if (u or env_u) and len((u or env_u) or "") > 50 else (u or env_u or "—")
        return _telegram_safe(f"Modelo actual:\n- provider: {provider}\n- model: {model}\n- base_url: {base_url}\n\nUso: /model provider=mlx | /model provider=deepseek | /model model=Slayer-8B")
    for part in args.split("|"):
        part = part.strip()
        if "=" in part:
            k, _, v = part.partition("=")
            k, v = k.strip().lower(), v.strip()
            if k == "provider":
                if v and v.lower() not in _PROVIDERS:
                    return _telegram_safe(f"Provider desconocido: {v}. Válidos: {', '.join(_PROVIDERS)}")
                set_chat_state(db, chat_id, "llm_provider", v)
                # Al cambiar provider, resetear model al default para evitar "Model Not Exist"
                # (ej. Slayer-8B-v1.1 no existe en DeepSeak)
                default_model = _DEFAULT_MODEL_BY_PROVIDER.get(v.lower(), "")
                set_chat_state(db, chat_id, "llm_model", default_model)
            elif k == "model":
                set_chat_state(db, chat_id, "llm_model", v)
            elif k == "base_url":
                set_chat_state(db, chat_id, "llm_base_url", v)
    return _telegram_safe("✅ Modelo actualizado. Los próximos mensajes usarán esta config.")


def execute_prompt(db: Any, chat_id: Any, args: str) -> str:
    """/prompt <worker_id> [--change <nuevo prompt>]: ver o cambiar el system prompt del template. worker_id debe ser uno de /roles."""
    from duckclaw.workers.factory import list_workers
    all_templates = list_workers()
    raw = (args or "").strip()
    if not raw:
        return _telegram_safe("Uso: /prompt <worker_id> [--change <texto>]. Ver templates: /roles")
    if raw.startswith("--"):
        return _telegram_safe("Indica un worker_id (ej. finanz, research_worker). Ver templates: /roles")
    change_marker = " --change "
    idx = raw.lower().find(change_marker)
    if idx >= 0:
        worker_id = raw[:idx].strip().lower()
        new_prompt = raw[idx + len(change_marker):].strip()
    else:
        worker_id = raw.split()[0].strip().lower() if raw.split() else ""
        new_prompt = ""
    if not worker_id:
        return _telegram_safe("Uso: /prompt <worker_id> [--change <texto>]. Ver templates: /roles")
    if worker_id not in all_templates:
        return _telegram_safe(f"Template '{worker_id}' no encontrado. Disponibles (usa /roles): {', '.join(all_templates)}")
    if new_prompt:
        _set_global_config(db, f"system_prompt_{worker_id}", new_prompt)
        preview = new_prompt[:200] + "..." if len(new_prompt) > 200 else new_prompt
        return _telegram_safe(f"✅ System prompt de {worker_id} actualizado.\nVista previa: {preview}")
    current = get_effective_system_prompt(db, worker_id)
    if not current:
        return _telegram_safe(f"System prompt de {worker_id}: (vacío o por defecto del template).\nPara cambiar: /prompt {worker_id} --change <texto>")
    preview = current[:400] + "..." if len(current) > 400 else current
    return _telegram_safe(f"System prompt de {worker_id}:\n{preview}\n\nPara cambiar: /prompt {worker_id} --change <texto>")


def execute_help(db: Any, chat_id: Any) -> str:
    """/help: lista los fly commands disponibles."""
    lines = [
        (_telegram_safe("/team"), _telegram_safe("Ver o definir equipo (solo a estos delega el manager)")),
        (_telegram_safe("/roles"), _telegram_safe("Ver todos los trabajadores virtuales (templates)")),
        (_telegram_safe("/tasks"), _telegram_safe("Estado actual: BUSY/IDLE, subagente, tarea")),
        (_telegram_safe("/history"), _telegram_safe("Historial de tareas (quién hizo qué)")),
        (_telegram_safe("/goals"), _telegram_safe("Objetivos de homeostasis")),
        (_telegram_safe("/prompt <worker_id>"), _telegram_safe("Ver prompt; --change <texto> para cambiar")),
        (_telegram_safe("/model"), _telegram_safe("Ver o cambiar LLM (provider/model)")),
        (_telegram_safe("/skills <worker_id>"), _telegram_safe("Herramientas del template")),
        (_telegram_safe("/forget"), _telegram_safe("Borrar historial de la conversación")),
        (_telegram_safe("/context"), _telegram_safe("Toggle contexto largo/corto")),
        (_telegram_safe("/audit"), _telegram_safe("Última auditoría de ejecución")),
        (_telegram_safe("/health"), _telegram_safe("Estado del servicio")),
        (_telegram_safe("/setup"), _telegram_safe("Config key=value")),
        (_telegram_safe("/approve"), _telegram_safe("Aprobar última acción")),
        (_telegram_safe("/reject"), _telegram_safe("Rechazar última acción")),
    ]
    block = "\n".join(f"{cmd} \\- {desc}" for cmd, desc in lines)
    return f"🦆 {_telegram_safe('Fly commands:')}\n\n{block}"


def handle_command(db: Any, chat_id: Any, text: str) -> Optional[str]:
    """
    Middleware: si el mensaje es un comando on-the-fly, ejecuta y retorna la respuesta.
    Si no es comando o no es manejado, retorna None.
    """
    name, args = parse_command(text)
    if not name:
        return None
    if name == "help":
        return execute_help(db, chat_id)
    if name == "role":
        return _telegram_safe("El comando /role ya no existe. Usa /team para ver o definir el equipo, /help para ver todos los comandos.")
    if name == "roles":
        return execute_roles(db, chat_id)
    if name == "team":
        return execute_team(db, chat_id, args)
    if name == "skills":
        return execute_skills_list(db, chat_id, args)
    if name == "forget":
        return execute_forget(db, chat_id)
    if name == "context":
        return execute_context_toggle(db, chat_id, args)
    if name == "audit":
        return execute_audit(db, chat_id)
    if name == "health":
        return execute_health(db)
    if name == "approve":
        return execute_approve_reject(db, chat_id, True)
    if name == "reject":
        return execute_approve_reject(db, chat_id, False)
    if name in ("prompt", "system_prompt", "system"):
        return execute_prompt(db, chat_id, args)
    if name in ("model", "provider", "llm"):
        return execute_model(db, chat_id, args)
    if name == "setup":
        return _execute_setup(db, chat_id, args)
    if name == "goals":
        return execute_goals(db, chat_id, args)
    if name == "tasks":
        return execute_tasks(db, chat_id)
    if name == "history":
        return execute_history(db, chat_id, args)
    return None


def _execute_setup(db: Any, chat_id: Any, args: str) -> str:
    """/setup [key=value | key=value]: formato compatible con Telegram. Sin args muestra config."""
    if not args or not args.strip():
        p = get_chat_state(db, chat_id, "llm_provider") or _get_global_config(db, "llm_provider")
        m = get_chat_state(db, chat_id, "llm_model") or _get_global_config(db, "llm_model")
        wid = get_chat_state(db, chat_id, "worker_id")
        prompt = _get_global_config(db, "system_prompt") or ""
        return _telegram_safe(
            f"Config actual:\n- llm_provider: {p or '—'}\n- llm_model: {m or '—'}\n"
            f"- worker_id: {wid or '—'}\n- system_prompt: {prompt[:80]}...\n\n"
            "Para cambiar: /setup llm_provider=deepseek | /setup system_prompt=..."
        )
    for part in args.split("|"):
        part = part.strip()
        if "=" in part:
            k, _, v = part.partition("=")
            k, v = k.strip().lower(), v.strip()
            if k in ("llm_provider", "provider"):
                if v and v.lower() not in _PROVIDERS:
                    return _telegram_safe(f"Provider desconocido: {v}. Válidos: {', '.join(_PROVIDERS)}")
                set_chat_state(db, chat_id, "llm_provider", v)
                default_model = _DEFAULT_MODEL_BY_PROVIDER.get(v.lower(), "")
                set_chat_state(db, chat_id, "llm_model", default_model)
            elif k in ("llm_model", "model"):
                set_chat_state(db, chat_id, "llm_model", v)
            elif k in ("llm_base_url", "base_url"):
                set_chat_state(db, chat_id, "llm_base_url", v)
            elif k in ("system_prompt", "prompt"):
                _set_global_config(db, "system_prompt", v)
    return _telegram_safe("✅ Config actualizado.")


def get_history_limit_for_chat(db: Any, chat_id: Any, default: int = 10) -> int:
    """Devuelve el límite de historial según use_rag del chat (para /context off = menos contexto)."""
    use_rag = get_chat_state(db, chat_id, "use_rag")
    if use_rag == "false":
        return 3
    return default


def get_worker_id_for_chat(db: Any, chat_id: Any) -> str:
    """Devuelve el worker_id asignado a este chat. Por defecto: manager (orquesta y delega a templates)."""
    return get_chat_state(db, chat_id, "worker_id") or _DEFAULT_WORKER


def save_last_audit(db: Any, chat_id: Any, latency_ms: int, sql: str = "", run_id: str = "", tokens: Any = None) -> None:
    """Guarda datos de la última ejecución para /audit."""
    data = {"latency_ms": latency_ms, "sql": sql or "", "run_id": run_id or "", "tokens": tokens or ""}
    set_chat_state(db, chat_id, "last_audit", json.dumps(data))


_TASK_AUDIT_TABLE = "task_audit_log"


def _ensure_task_audit_log(db: Any) -> None:
    db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_TASK_AUDIT_TABLE} (
            task_id VARCHAR PRIMARY KEY,
            tenant_id VARCHAR NOT NULL,
            worker_id VARCHAR,
            query_prefix VARCHAR,
            status VARCHAR NOT NULL,
            duration_ms INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def append_task_audit(
    db: Any,
    tenant_id: Any,
    worker_id: str,
    query_prefix: str,
    status: str,
    duration_ms: int,
) -> None:
    """Append a task to task_audit_log for /history. Spec: Fly comando history (Auditoría de Rendimiento)."""
    import uuid
    _ensure_task_audit_log(db)
    task_id = f"TASK-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    tenant_s = str(tenant_id).replace("'", "''")[:128]
    worker_s = (worker_id or "").replace("'", "''")[:64]
    prefix_s = (query_prefix or "")[:256].replace("'", "''")
    status_s = (status or "SUCCESS").upper().replace("'", "''")[:32]
    status_s = "SUCCESS" if status_s not in ("SUCCESS", "FAILED") else status_s
    db.execute(
        f"""
        INSERT INTO {_TASK_AUDIT_TABLE} (task_id, tenant_id, worker_id, query_prefix, status, duration_ms)
        VALUES ('{task_id}', '{tenant_s}', '{worker_s}', '{prefix_s}', '{status_s}', {int(duration_ms)})
        """
    )


def _is_simple_greeting(prefix: str) -> bool:
    """True si el mensaje es un saludo corto (hola, hi, etc.) sin tarea real."""
    p = (prefix or "").strip().lower()[:50]
    if len(p) > 35:
        return False
    greetings = (
        "hola", "hi", "hey", "hello", "buenas", "qué tal", "que tal",
        "buenos días", "buenos dias", "buenas tardes", "buenas noches",
        "ola", "saludos", "ciao", "adios", "chao",
    )
    return p in greetings or p.rstrip("!?.") in greetings


def _is_complex_task(row: dict) -> bool:
    """True si la tarea usó herramientas (tool use) o no es un saludo simple."""
    prefix = (row.get("query_prefix") or "").strip()
    if _is_simple_greeting(prefix):
        return False
    try:
        dur_ms = int(row.get("duration_ms") or 0)
    except (TypeError, ValueError):
        dur_ms = 0
    return dur_ms >= 1500 or len(prefix) > 20


def execute_history(db: Any, chat_id: Any, args: str) -> str:
    """/history [n]: historial de tareas complejas (tool use). Saludos simples (hola) se muestran como máximo uno."""
    tenant_s = str(chat_id).replace("'", "''")[:128]
    try:
        n = int((args or "5").strip())
        n = max(1, min(n, 20))
    except ValueError:
        n = 5
    _ensure_task_audit_log(db)
    try:
        r = db.query(
            f"""
            SELECT task_id, query_prefix, status, duration_ms, created_at, worker_id
            FROM {_TASK_AUDIT_TABLE}
            WHERE tenant_id = '{tenant_s}'
            ORDER BY created_at DESC
            LIMIT 100
            """
        )
        rows = json.loads(r) if isinstance(r, str) else (r or [])
    except Exception as e:
        return _telegram_safe(f"Error al cargar historial: {e}.")

    if not rows:
        return _telegram_safe("📋 Sin tareas registradas.")

    # Filtrar: tareas complejas + como máximo 1 saludo simple
    complex_rows = []
    one_greeting = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _is_complex_task(row):
            complex_rows.append(row)
        elif one_greeting is None and _is_simple_greeting(row.get("query_prefix") or ""):
            one_greeting = row
    filtered = complex_rows[:n]
    if one_greeting is not None and len(filtered) < n:
        filtered.append(one_greeting)

    if not filtered:
        return _telegram_safe("📋 Sin tareas complejas.")

    lines = [f"📋 Últimas {len(filtered)}"]
    for i, row in enumerate(filtered, 1):
        if not isinstance(row, dict):
            continue
        prefix = (row.get("query_prefix") or "").strip()[:50]
        status = (row.get("status") or "UNKNOWN").upper()
        wid = (row.get("worker_id") or "").strip()
        try:
            dur_ms = int(row.get("duration_ms") or 0)
        except (TypeError, ValueError):
            dur_ms = 0
        dur_s = f"{dur_ms / 1000:.1f}s"
        icon = "✅" if status == "SUCCESS" else "❌"
        subagente = f"[{_telegram_safe(wid)}] " if wid else ""
        lines.append(f"{i}. {icon} {dur_s} · {subagente}{_telegram_safe(prefix) or '—'}")

    success_rows = [r for r in filtered if isinstance(r, dict) and (r.get("status") or "").upper() == "SUCCESS"]
    def _dur(r):
        try:
            return int(r.get("duration_ms") or 0)
        except (TypeError, ValueError):
            return 0
    avg_ms = sum(_dur(r) for r in success_rows) / len(success_rows) if success_rows else 0
    try:
        r24 = db.query(
            f"""
            SELECT COUNT(*) as cnt FROM {_TASK_AUDIT_TABLE}
            WHERE tenant_id = '{tenant_s}' AND status = 'FAILED'
            AND created_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
            """
        )
        rows24 = json.loads(r24) if isinstance(r24, str) else (r24 or [])
        failed_24h = rows24[0].get("cnt", 0) if rows24 else 0
    except Exception:
        failed_24h = 0
    lines.append(f"— avg {avg_ms/1000:.1f}s · fallidas 24h: {failed_24h}")

    return _telegram_safe("\n".join(lines))
