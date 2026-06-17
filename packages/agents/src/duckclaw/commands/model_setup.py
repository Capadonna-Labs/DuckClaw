"""Chat-scoped LLM model, setup and prompt commands."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from duckclaw.commands.chat_state import _get_global_config, get_chat_state
from duckclaw.prompt_policies.system_prompt import resolve_effective_system_prompt
from duckclaw.runtime_session_settings import (
    RUNTIME_SESSION_DOMAIN,
    resolve_session_runtime_setting,
    runtime_session_actor,
    upsert_session_runtime_setting,
)
from duckclaw.write_commands import UpsertPromptPolicyCommand, UpsertRuntimeSettingCommand

PromptTemplateIdsProvider = Callable[[], Sequence[str]]
SystemPromptFallbackProvider = Callable[[str], str]

_prompt_template_ids_provider: PromptTemplateIdsProvider | None = None
_system_prompt_fallback_provider: SystemPromptFallbackProvider | None = None


def configure_prompt_template_ids_provider(provider: PromptTemplateIdsProvider | None) -> None:
    """Configure prompt worker validation without importing graph/runtime owners."""
    global _prompt_template_ids_provider
    _prompt_template_ids_provider = provider


def configure_prompt_system_fallback_provider(provider: SystemPromptFallbackProvider | None) -> None:
    """Configure default-worker prompt fallback without coupling this module to worker storage."""
    global _system_prompt_fallback_provider
    _system_prompt_fallback_provider = provider


def _debug_log_model_config(
    *,
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict[str, Any],
    run_id: str = "gemini_cfg_debug_v1",
) -> None:
    """Reserved for optional NDJSON debug (no-op)."""
    del hypothesis_id, location, message, data, run_id


def _available_prompt_template_ids() -> list[str]:
    if callable(_prompt_template_ids_provider):
        try:
            provided = _prompt_template_ids_provider()
            ids: list[str] = []
            seen: set[str] = set()
            for item in provided:
                template_id = str(item).strip()
                if template_id and template_id not in seen:
                    seen.add(template_id)
                    ids.append(template_id)
            return ids if ids else ["default"]
        except Exception:
            return ["default"]
    return ["default"]


def _system_prompt_fallback(worker_id: str) -> str:
    if callable(_system_prompt_fallback_provider):
        try:
            return (_system_prompt_fallback_provider(worker_id) or "").strip()
        except Exception:
            return ""
    return ""


def _system_prompt_policy_name(worker_id: Optional[str]) -> str:
    return (worker_id or "default").strip().lower() or "default"


def _ensure_prompt_policy_schema(db: Any) -> None:
    if bool(getattr(db, "_read_only", False)):
        return
    try:
        from duckclaw.schema_migrations import run_pending_migrations

        run_pending_migrations(db)
    except Exception:
        pass


def _set_system_prompt_policy(
    db: Any,
    worker_id: str,
    content: str,
    *,
    actor_email: str = "system",
) -> tuple[bool, str]:
    policy_name = _system_prompt_policy_name(worker_id)
    command = UpsertPromptPolicyCommand(
        tenant_id="default",
        actor_email=actor_email,
        policy_type="system_prompt",
        policy_name=policy_name,
        version=1,
        status="active",
        content=content,
        metadata={"owner": "duckclaw.commands.model_setup"},
    )
    if not bool(getattr(db, "_read_only", False)):
        _ensure_prompt_policy_schema(db)
        try:
            from duckclaw.write_command_handlers import dispatch_command

            target = getattr(db, "_con", None) or getattr(db, "_native", None) or db
            dispatch_command(target, command.model_dump())
            return True, ""
        except Exception as exc:
            return False, str(exc)[:500]

    raw_path = str(getattr(db, "_path", "") or "").strip()
    if not raw_path or raw_path == ":memory:":
        return False, "Ruta de bóveda no resuelta"
    try:
        target_db_path = str(Path(raw_path).expanduser().resolve())
    except OSError:
        target_db_path = raw_path

    try:
        from duckclaw.db_write_queue import enqueue_typed_command, poll_task_status_sync
    except Exception as exc:
        return False, f"cola DuckDB no disponible: {exc}"

    released_ro, resume = _release_ro_handle_for_writer(db)
    try:
        task_id = enqueue_typed_command(
            command,
            db_path=target_db_path,
            user_id=actor_email,
        )
        status = poll_task_status_sync(task_id, timeout_sec=30.0)
        if status is None:
            return False, "timeout esperando db-writer"
        if status.status != "success":
            return False, (status.detail or "db-writer failed")[:500]
        return True, ""
    finally:
        if released_ro and callable(resume):
            try:
                resume()
            except Exception:
                pass


def get_effective_system_prompt(
    db: Any,
    worker_id: Optional[str] = None,
    *,
    tenant_id: Optional[str] = None,
) -> str:
    """
    Return the DB-first effective system prompt for a worker.
    """
    policy_name = _system_prompt_policy_name(worker_id)
    return resolve_effective_system_prompt(
        db,
        worker_id=policy_name,
        tenant_id=tenant_id,
        filesystem_fallback=_system_prompt_fallback(policy_name),
    )


_PROVIDERS = ("mlx", "ollama", "openai", "anthropic", "deepseek", "groq", "gemini", "openrouter", "or")

_DEFAULT_MODEL_BY_PROVIDER = {
    "deepseek": "deepseek-chat",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-20241022",
    "groq": "llama-3.3-70b-versatile",
    "gemini": "gemini-2.0-flash",
    "openrouter": "deepseek/deepseek-v4-flash",
    "mlx": "",
    "ollama": "llama3.2",
}

_DEFAULT_BASE_URL_BY_PROVIDER = {
    "deepseek": "https://api.deepseek.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "",
    "anthropic": "",
    "gemini": "",
    "mlx": "",
    "ollama": "http://127.0.0.1:11434",
}


def _release_ro_handle_for_writer(db: Any) -> tuple[bool, Any]:
    release = getattr(db, "release_file_handle_for_external_writer", None)
    suspend = getattr(db, "suspend_readonly_file_handle", None)
    resume = getattr(db, "resume_readonly_file_handle", None)
    if callable(release):
        release()
        return bool(callable(resume)), resume
    if callable(suspend) and callable(resume):
        suspend()
        return True, resume
    return False, resume


def _llm_runtime_value(db: Any, chat_id: Any, key: str) -> str:
    return resolve_session_runtime_setting(db, chat_id, key)


def _set_llm_runtime_value(db: Any, chat_id: Any, key: str, value: str) -> tuple[bool, str]:
    if not bool(getattr(db, "_read_only", False)):
        upsert_session_runtime_setting(
            db,
            chat_id,
            key,
            value,
            updated_by="model-setup",
        )
        return True, ""

    raw_path = str(getattr(db, "_path", "") or "").strip()
    if not raw_path or raw_path == ":memory:":
        return False, "Ruta de bóveda no resuelta"
    try:
        target_db_path = str(Path(raw_path).expanduser().resolve())
    except OSError:
        target_db_path = raw_path

    command = UpsertRuntimeSettingCommand(
        tenant_id="default",
        actor_email=runtime_session_actor(chat_id),
        domain=RUNTIME_SESSION_DOMAIN,
        key=key,
        value=str(value)[:8192],
        value_kind="string",
    )
    try:
        from duckclaw.db_write_queue import enqueue_typed_command, poll_task_status_sync
    except Exception as exc:
        return False, f"cola DuckDB no disponible: {exc}"

    released_ro, resume = _release_ro_handle_for_writer(db)
    try:
        task_id = enqueue_typed_command(
            command,
            db_path=target_db_path,
            user_id=str(chat_id or "default").strip() or "default",
        )
        status = poll_task_status_sync(task_id, timeout_sec=30.0)
        if status is None:
            return False, "timeout esperando db-writer"
        if status.status != "success":
            return False, (status.detail or "db-writer failed")[:500]
        return True, ""
    finally:
        if released_ro and callable(resume):
            try:
                resume()
            except Exception:
                pass


def _effective_llm_triplet_for_chat_ui(db: Any, chat_id: Any) -> tuple[str, str, str]:
    """Return provider/model/base_url effective for UI display."""
    from duckclaw.integrations.llm_providers import (
        _ensure_duckclaw_llm_env_from_legacy_llm_vars,
        mlx_openai_compatible_base_url,
    )

    _ensure_duckclaw_llm_env_from_legacy_llm_vars()
    p_chat = (_llm_runtime_value(db, chat_id, "llm_provider") or "").strip()
    p_global = (_get_global_config(db, "llm_provider") or "").strip()
    p_env = (os.environ.get("DUCKCLAW_LLM_PROVIDER", "mlx") or "").strip()
    p = (p_chat or p_global or p_env).strip().lower()
    m_chat = (_llm_runtime_value(db, chat_id, "llm_model") or "").strip()
    m_global = (_get_global_config(db, "llm_model") or "").strip()
    m_env = (os.environ.get("DUCKCLAW_LLM_MODEL", "") or "").strip()
    m = (m_chat or m_global or m_env).strip()
    u_chat = (_llm_runtime_value(db, chat_id, "llm_base_url") or "").strip()
    u_global = (_get_global_config(db, "llm_base_url") or "").strip()
    u_env = (os.environ.get("DUCKCLAW_LLM_BASE_URL", "") or "").strip()
    u = (u_chat or u_global or u_env).strip()
    if p == "mlx":
        ul = u.lower()
        if (not u) or "groq.com" in ul or "deepseek.com" in ul:
            u = mlx_openai_compatible_base_url()
        if not m:
            m = (os.environ.get("MLX_MODEL_ID") or os.environ.get("MLX_MODEL_PATH") or "").strip()
    _debug_log_model_config(
        hypothesis_id="H_sources_priority",
        location="model_setup._effective_llm_triplet_for_chat_ui",
        message="effective_triplet_computed",
        data={
            "chat_id": str(chat_id),
            "provider": p,
            "model": m[:80],
            "base_url": u[:120],
            "src_provider": "chat" if p_chat else ("global" if p_global else "env"),
            "src_model": "chat" if m_chat else ("global" if m_global else "env"),
            "src_base_url": "chat" if u_chat else ("global" if u_global else "env"),
            "chat_provider": p_chat[:60],
            "chat_base_url": u_chat[:120],
            "global_provider": p_global[:60],
            "global_base_url": u_global[:120],
            "env_provider": p_env[:60],
            "env_base_url": u_env[:120],
        },
    )
    return (p, m, u)


def chat_has_llm_chat_state_override(db: Any, chat_id: Any) -> bool:
    cid = str(chat_id or "").strip()
    if not cid:
        return False
    for key in ("llm_provider", "llm_model", "llm_base_url"):
        if (_llm_runtime_value(db, cid, key) or "").strip():
            return True
    return False


def resolve_llm_triplet_for_chat_invocation(db: Any, chat_id: Any) -> tuple[str, str, str] | None:
    """Return a chat override triplet for graph invocation, or None to use cached env config."""
    has_override = chat_has_llm_chat_state_override(db, chat_id)
    _debug_log_model_config(
        hypothesis_id="H_override_gate",
        location="model_setup.resolve_llm_triplet_for_chat_invocation",
        message="chat_override_gate",
        data={"chat_id": str(chat_id), "has_override": bool(has_override)},
    )
    if not has_override:
        return None
    return _effective_llm_triplet_for_chat_ui(db, chat_id)


def _apply_provider_defaults(db: Any, chat_id: Any, provider: str) -> None:
    if provider == "mlx":
        from duckclaw.integrations.llm_providers import mlx_openai_compatible_base_url

        _set_llm_runtime_value(db, chat_id, "llm_base_url", mlx_openai_compatible_base_url())
        mid = (os.environ.get("MLX_MODEL_ID") or os.environ.get("MLX_MODEL_PATH") or "").strip()
        _set_llm_runtime_value(db, chat_id, "llm_model", mid)
        return
    default_model = _DEFAULT_MODEL_BY_PROVIDER.get(provider, "")
    _set_llm_runtime_value(db, chat_id, "llm_model", default_model)
    default_url = _DEFAULT_BASE_URL_BY_PROVIDER.get(provider, "")
    _set_llm_runtime_value(db, chat_id, "llm_base_url", default_url if default_url else "")


def execute_model(db: Any, chat_id: Any, args: str) -> str:
    """/model [provider=mlx] [model=...] [base_url=...]: change chat LLM settings."""
    _debug_log_model_config(
        hypothesis_id="H_write_apply",
        location="model_setup.execute_model",
        message="execute_model_entry",
        data={"chat_id": str(chat_id), "args": (args or "")[:180]},
    )
    if not args or not args.strip():
        provider, model, base_url = _effective_llm_triplet_for_chat_ui(db, chat_id)
        provider = provider or "—"
        model = model or "—"
        u_show = base_url or "—"
        base_url = u_show[:50] + "…" if len(u_show) > 50 else u_show
        return f"Modelo actual:\n- provider: {provider}\n- model: {model}\n- base_url: {base_url}\n\nUso: /model provider=mlx | /model provider=deepseek | /model provider=openrouter | /model provider=or model=google/gemini-2.5-pro | /model model=Slayer-8B"
    for part in args.split("|"):
        part = part.strip()
        if "=" not in part:
            continue
        k, _, v = part.partition("=")
        k, v = k.strip().lower(), v.strip()
        if k == "provider":
            if v and v.lower() not in _PROVIDERS:
                return f"Provider desconocido: {v}. Válidos: {', '.join(_PROVIDERS)}"
            pv = v.lower()
            if pv in ("or", "router"):
                pv = "openrouter"
            ok, err = _set_llm_runtime_value(db, chat_id, "llm_provider", pv)
            if not ok:
                return f"No se pudo guardar: {err}"
            _apply_provider_defaults(db, chat_id, pv)
            _debug_log_model_config(
                hypothesis_id="H_write_apply",
                location="model_setup.execute_model",
                message="provider_written",
                data={
                    "chat_id": str(chat_id),
                    "provider_arg": pv,
                    "default_model": (_DEFAULT_MODEL_BY_PROVIDER.get(pv, "") or "")[:80],
                    "default_base_url": (_DEFAULT_BASE_URL_BY_PROVIDER.get(pv, "") or "")[:120],
                },
            )
        elif k == "model":
            ok, err = _set_llm_runtime_value(db, chat_id, "llm_model", v)
            if not ok:
                return f"No se pudo guardar: {err}"
        elif k == "base_url":
            ok, err = _set_llm_runtime_value(db, chat_id, "llm_base_url", v)
            if not ok:
                return f"No se pudo guardar: {err}"
    _p, _m, _u = _effective_llm_triplet_for_chat_ui(db, chat_id)
    _debug_log_model_config(
        hypothesis_id="H_write_apply",
        location="model_setup.execute_model",
        message="execute_model_exit",
        data={"chat_id": str(chat_id), "provider": _p, "model": _m[:80], "base_url": _u[:120]},
    )
    return "✅ Modelo actualizado. Los próximos mensajes usarán esta config."


def _parse_pipe_kv_args(args: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in (args or "").split("|"):
        p = part.strip()
        if "=" not in p:
            continue
        k, _, v = p.partition("=")
        k = k.strip().lower()
        v = v.strip()
        if k:
            out[k] = v
    return out


def _gemini_models_list_from_api(api_key: str) -> tuple[list[str], str | None]:
    url = "https://generativelanguage.googleapis.com/v1beta/models"
    req = urllib.request.Request(
        f"{url}?key={urllib.parse.quote(api_key)}",
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            status = getattr(resp, "status", 200)
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        return [], f"Gemini API HTTP {e.code}: {(detail or '').strip()[:220] or 'sin detalle'}"
    except Exception as e:
        return [], f"No pude consultar Gemini models: {e}"
    if status < 200 or status >= 300:
        return [], f"Gemini API devolvió HTTP {status}."
    try:
        payload = json.loads(body or "{}")
    except json.JSONDecodeError:
        return [], "Gemini API devolvió una respuesta no-JSON."
    models = payload.get("models")
    if not isinstance(models, list):
        return [], "Gemini API no devolvió la lista de modelos."
    usable: list[str] = []
    for row in models:
        if not isinstance(row, dict):
            continue
        raw_name = str(row.get("name") or "").strip()
        if not raw_name:
            continue
        methods = row.get("supportedGenerationMethods") or []
        if isinstance(methods, list) and methods:
            method_names = {str(m).strip() for m in methods if str(m).strip()}
            if "generateContent" not in method_names:
                continue
        short_name = raw_name.split("/")[-1]
        if short_name:
            usable.append(short_name)
    dedup = sorted(set(usable))
    if "gemini-2.0-flash" in dedup:
        dedup = ["gemini-2.0-flash"] + [m for m in dedup if m != "gemini-2.0-flash"]
    return dedup, None


def execute_models(db: Any, chat_id: Any, args: str) -> str:
    """/models provider=gemini: list provider models."""
    kv = _parse_pipe_kv_args(args)
    provider = (kv.get("provider") or "").strip().lower()
    if not provider:
        provider = (_effective_llm_triplet_for_chat_ui(db, chat_id)[0] or "").strip().lower()
    if not provider:
        return "Uso: /models provider=gemini"
    if provider != "gemini":
        return "Por ahora /models soporta solo provider=gemini."
    key = ((os.environ.get("GOOGLE_API_KEY") or "").strip() or (os.environ.get("GEMINI_API_KEY") or "").strip())
    if not key:
        return "Falta GOOGLE_API_KEY (o GEMINI_API_KEY) para listar modelos de Gemini."
    models, err = _gemini_models_list_from_api(key)
    if err:
        return f"No se pudo listar modelos Gemini. {err}"
    if not models:
        return "Gemini no devolvió modelos utilizables para generateContent."
    preview = "\n".join(f"- {m}" for m in models[:30])
    more = "" if len(models) <= 30 else f"\n... y {len(models) - 30} más."
    hint = "\nSugerencia: /model provider=gemini | model=gemini-2.0-flash"
    return f"Modelos Gemini disponibles ({len(models)}):\n{preview}{more}{hint}"


def execute_prompt(db: Any, chat_id: Any, args: str) -> str:
    """/prompt <worker_id> [--change <nuevo prompt>]: view or change a system prompt override."""
    all_templates = _available_prompt_template_ids()
    raw = (args or "").strip()
    if not raw:
        return "Uso: /prompt <worker_id> [--change <texto>]. Ver templates: /roles"
    if raw.startswith("--"):
        return "Indica un worker_id (ej. default). Ver templates: /roles"
    change_marker = " --change "
    idx = raw.lower().find(change_marker)
    if idx >= 0:
        worker_id = raw[:idx].strip().lower()
        new_prompt = raw[idx + len(change_marker):].strip()
    else:
        worker_id = raw.split()[0].strip().lower() if raw.split() else ""
        new_prompt = ""
    if not worker_id:
        return "Uso: /prompt <worker_id> [--change <texto>]. Ver templates: /roles"
    if worker_id not in all_templates:
        return f"Template '{worker_id}' no encontrado. Disponibles (usa /roles): {', '.join(all_templates)}"
    if new_prompt:
        ok, err = _set_system_prompt_policy(
            db,
            worker_id,
            new_prompt,
            actor_email=f"chat:{str(chat_id or 'default').strip() or 'default'}",
        )
        if not ok:
            return f"No se pudo guardar: {err}"
        preview = new_prompt[:200] + "..." if len(new_prompt) > 200 else new_prompt
        return f"✅ System prompt de {worker_id} actualizado.\nVista previa: {preview}"
    current = get_effective_system_prompt(db, worker_id)
    if not current:
        return f"System prompt de {worker_id}: (vacío o por defecto del template).\nPara cambiar: /prompt {worker_id} --change <texto>"
    preview = current[:400] + "..." if len(current) > 400 else current
    return f"System prompt de {worker_id}:\n{preview}\n\nPara cambiar: /prompt {worker_id} --change <texto>"


def execute_setup(db: Any, chat_id: Any, args: str) -> str:
    """/setup [key=value | key=value]: Telegram-compatible config command."""
    if not args or not args.strip():
        p = _llm_runtime_value(db, chat_id, "llm_provider") or _get_global_config(db, "llm_provider")
        m = _llm_runtime_value(db, chat_id, "llm_model") or _get_global_config(db, "llm_model")
        wid = get_chat_state(db, chat_id, "worker_id")
        prompt = get_effective_system_prompt(db, "default") or ""
        return (
            f"Config actual:\n- llm_provider: {p or '—'}\n- llm_model: {m or '—'}\n"
            f"- worker_id: {wid or '—'}\n- system_prompt: {prompt[:80]}...\n\n"
            "Para cambiar: /setup llm_provider=deepseek | /setup system_prompt=..."
        )
    for part in args.split("|"):
        part = part.strip()
        if "=" not in part:
            continue
        k, _, v = part.partition("=")
        k, v = k.strip().lower(), v.strip()
        if k in ("llm_provider", "provider"):
            if v and v.lower() not in _PROVIDERS:
                return f"Provider desconocido: {v}. Válidos: {', '.join(_PROVIDERS)}"
            provider = v.lower()
            if provider in ("or", "router"):
                provider = "openrouter"
            ok, err = _set_llm_runtime_value(db, chat_id, "llm_provider", provider)
            if not ok:
                return f"No se pudo guardar: {err}"
            _apply_provider_defaults(db, chat_id, provider)
        elif k in ("llm_model", "model"):
            ok, err = _set_llm_runtime_value(db, chat_id, "llm_model", v)
            if not ok:
                return f"No se pudo guardar: {err}"
        elif k in ("llm_base_url", "base_url"):
            ok, err = _set_llm_runtime_value(db, chat_id, "llm_base_url", v)
            if not ok:
                return f"No se pudo guardar: {err}"
        elif k in ("system_prompt", "prompt"):
            ok, err = _set_system_prompt_policy(
                db,
                "default",
                v,
                actor_email=f"chat:{str(chat_id or 'default').strip() or 'default'}",
            )
            if not ok:
                return f"No se pudo guardar: {err}"
    return "✅ Config actualizado."


_execute_setup = execute_setup

