"""Resolución SLM (inferencia local / OpenAI-compatible) para admin playground."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from duckclaw.integrations.llm_providers import mlx_openai_compatible_base_url


def slm_base_url() -> str:
    """URL OpenAI-compat del SLM (runtime local o remoto vía Tailscale)."""
    explicit = (os.environ.get("DUCKCLAW_SLM_BASE_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit if explicit.endswith("/v1") else f"{explicit}/v1"
    return mlx_openai_compatible_base_url()


def slm_env_model() -> str:
    return (os.environ.get("MLX_MODEL_ID") or os.environ.get("MLX_MODEL_PATH") or "").strip()


def slm_env_adapter() -> str:
    return (os.environ.get("MLX_ADAPTER_PATH") or "").strip()


def _short_model_name(model: str) -> str:
    raw = (model or "").strip()
    if not raw:
        return "—"
    return Path(raw).name or raw.split("/")[-1] or raw


def _adapter_scan_roots(repo_root: Path) -> list[Path]:
    roots: list[Path] = []
    for rel in (
        "packages/agents/train/gemma4",
        "packages/agents/train/outputs",
    ):
        base = repo_root / rel
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if child.is_dir() and (
                child.name.startswith("adapters")
                or child.name in ("adapters_lora_yaml", "outputs")
            ):
                roots.append(child)
        if (base / "adapters_lora_yaml").is_dir():
            roots.append(base / "adapters_lora_yaml")
    seen: set[str] = set()
    out: list[Path] = []
    for p in roots:
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def discover_slm_adapters(repo_root: Path, *, active_adapter: str) -> list[dict[str, Any]]:
    """Lista adapters LoRA en disco (relativos al repo cuando aplica)."""
    active_norm = (active_adapter or "").strip().replace("\\", "/")
    adapters: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    def _add(adapter_id: str, label: str, path: str) -> None:
        aid = (adapter_id or "").strip()
        if not aid or aid in seen_ids:
            return
        seen_ids.add(aid)
        path_norm = path.replace("\\", "/")
        adapters.append(
            {
                "id": aid,
                "label": label,
                "path": path,
                "active": bool(active_norm and path_norm == active_norm),
            }
        )

    env_ad = slm_env_adapter()
    if env_ad:
        try:
            rel = str(Path(env_ad).resolve().relative_to(repo_root.resolve())).replace("\\", "/")
        except ValueError:
            rel = env_ad.replace("\\", "/")
        _add(rel, f"PM2 activo — {_short_model_name(rel)}", rel)

    for root in _adapter_scan_roots(repo_root):
        try:
            rel_root = str(root.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
        except ValueError:
            rel_root = str(root).replace("\\", "/")
        if (root / "adapter_config.json").is_file() or any(root.glob("*.safetensors")):
            _add(rel_root, _short_model_name(rel_root), rel_root)
            continue
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            if not (child / "adapter_config.json").is_file() and not any(child.glob("*.safetensors")):
                continue
            try:
                rel = str(child.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
            except ValueError:
                rel = str(child).replace("\\", "/")
            _add(rel, _short_model_name(child.name), rel)

    return adapters


async def probe_mlx_inference_status(base_url: str) -> str:
    """online si GET /v1/models responde 200."""
    import httpx

    base = (base_url or "").strip().rstrip("/")
    if not base:
        return "offline"
    url = f"{base}/models" if base.endswith("/v1") else f"{base}/v1/models"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                return "online"
    except Exception:
        pass
    return "offline"


def _session_slm_settings(db: Any, chat_id: str, tenant_id: str) -> dict[str, str]:
    from duckclaw.runtime_session_settings import resolve_session_runtime_setting

    tenant_candidates = [str(tenant_id or "default").strip() or "default"]
    if "default" not in tenant_candidates:
        tenant_candidates.append("default")

    def _get(key: str) -> str:
        for candidate in tenant_candidates:
            value = (
                resolve_session_runtime_setting(
                    db,
                    chat_id,
                    key,
                    tenant_id=candidate,
                )
                or ""
            ).strip()
            if value:
                return value
        return ""

    return {
        "slm_enabled": _get("slm_enabled"),
        "slm_adapter_path": _get("slm_adapter_path"),
        "slm_base_url": _get("slm_base_url"),
    }


def resolved_slm_for_playground(
    *,
    chat_id: str,
    tenant_id: str,
    repo_root: Path,
) -> dict[str, Any]:
    """SLM efectivo para una conversación admin (inferencia local)."""
    base = slm_base_url()
    model = slm_env_model()
    env_adapter = slm_env_adapter()
    enabled = False
    adapter_path = env_adapter
    scope = "env"

    cid = (chat_id or "").strip()
    gw_path = (os.environ.get("DUCKCLAW_GATEWAY_DB_PATH") or "").strip()
    if cid and gw_path and os.path.isfile(gw_path):
        try:
            from duckclaw import DuckClaw

            db = DuckClaw(gw_path, read_only=True, engine="python")
            try:
                session = _session_slm_settings(db, cid, tenant_id)
            finally:
                db.close()
            if session.get("slm_enabled"):
                enabled = session["slm_enabled"].lower() in ("1", "true", "yes", "on")
                scope = "chat"
            if session.get("slm_adapter_path"):
                adapter_path = session["slm_adapter_path"]
            if session.get("slm_base_url"):
                base = session["slm_base_url"].rstrip("/")
                if not base.endswith("/v1"):
                    base = f"{base}/v1"
        except Exception:
            pass

    try:
        if adapter_path and not os.path.isabs(adapter_path):
            adapter_path = str((repo_root / adapter_path).resolve())
    except Exception:
        pass

    adapters = discover_slm_adapters(repo_root, active_adapter=adapter_path)
    return {
        "enabled": enabled,
        "model": model,
        "model_short": _short_model_name(model),
        "adapter_path": adapter_path,
        "base_url": base,
        "mlx_status": "unknown",
        "pm2_name": (os.environ.get("DUCKCLAW_SLM_RUNTIME_NAME") or "local-inference").strip()
        or "local-inference",
        "adapters": adapters,
        "scope": scope,
        "hint": (
            "El runtime de inferencia local carga el adapter configurado (p. ej. vía variable "
            "de entorno del proceso PM2). Cambiar adapter en sesión puede requerir reiniciar "
            "ese proceso de inferencia local."
        ),
    }


async def resolved_slm_for_playground_async(
    *,
    chat_id: str,
    tenant_id: str,
    repo_root: Path,
) -> dict[str, Any]:
    payload = resolved_slm_for_playground(
        chat_id=chat_id,
        tenant_id=tenant_id,
        repo_root=repo_root,
    )
    payload["mlx_status"] = await probe_mlx_inference_status(payload.get("base_url", ""))
    return payload
