"""Security policy schemas and loader for Strix sandbox."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field


class NetworkPolicy(BaseModel):
    default: Literal["allow", "deny"] = "deny"
    allow_list: List[str] = Field(default_factory=list, description="Dominios o IPs permitidas si default es deny")


class FileSystemPolicy(BaseModel):
    readonly_mounts: List[str] = Field(default_factory=list, description="Rutas del host a montar como RO")
    ephemeral_volumes: List[str] = Field(
        default_factory=lambda: ["/tmp/workspace"], description="Volumenes tmpfs efimeros en memoria"
    )


class SecretPolicy(BaseModel):
    in_memory_only: bool = True
    allowed_secrets: List[str] = Field(
        default_factory=list, description="Nombres de variables de entorno permitidas"
    )


class SecurityPolicy(BaseModel):
    network: NetworkPolicy = Field(default_factory=NetworkPolicy)
    filesystem: FileSystemPolicy = Field(default_factory=FileSystemPolicy)
    secrets: SecretPolicy = Field(default_factory=SecretPolicy)
    # Perfil browser / OSINT JobHunter puede requerir hasta 300s (spec Strix Browser Sandbox).
    max_execution_time_seconds: int = Field(default=30, le=600)


def _default_zero_trust_policy() -> SecurityPolicy:
    return SecurityPolicy(
        network=NetworkPolicy(default="deny", allow_list=[]),
        filesystem=FileSystemPolicy(readonly_mounts=[], ephemeral_volumes=["/workspace/output"]),
        secrets=SecretPolicy(in_memory_only=True, allowed_secrets=[]),
        max_execution_time_seconds=30,
    )


def load_security_policy(worker_id: str, worker_dir: Path | None = None) -> SecurityPolicy:
    """
    Load and validate worker security_policy.yaml.

    Missing file falls back to strict deny-by-default policy.
    """
    policy_path: Path | None = None
    if worker_dir is not None:
        policy_path = worker_dir / "security_policy.yaml"
    else:
        try:
            from duckclaw.workers.manifest import get_worker_dir

            wd = get_worker_dir(worker_id)
            policy_path = wd / "security_policy.yaml"
        except Exception:
            policy_path = None

    if policy_path is None or not policy_path.is_file():
        return _default_zero_trust_policy()

    try:
        import yaml

        raw = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return _default_zero_trust_policy()

    if not isinstance(raw, dict):
        return _default_zero_trust_policy()

    try:
        return SecurityPolicy.model_validate(raw)
    except Exception:
        return _default_zero_trust_policy()


def security_policy_to_docker_kwargs(policy: SecurityPolicy) -> Dict[str, object]:
    """
    Translate policy to secure docker run kwargs.
    """
    volumes: Dict[str, Dict[str, str]] = {}
    _repo_fallback = str(Path(__file__).resolve().parents[5])
    for mount in policy.filesystem.readonly_mounts:
        parts = [p.strip() for p in str(mount).split(":")]
        if len(parts) < 2:
            continue
        raw_host = parts[0].strip()
        rr = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip() or _repo_fallback
        if "${DUCKCLAW_REPO_ROOT}" in raw_host or "$DUCKCLAW_REPO_ROOT" in raw_host:
            raw_host = (
                raw_host.replace("${DUCKCLAW_REPO_ROOT}", rr).replace("$DUCKCLAW_REPO_ROOT", rr)
            )
        host_path = os.path.expanduser(os.path.expandvars(raw_host))
        if not host_path or re.search(r"\$\{", host_path):
            # P. ej. ${DUCKCLAW_DATA_DIR} sin variable en el entorno → Docker 400 al crear el contenedor
            continue
        container_path = parts[1]
        mode = parts[2] if len(parts) > 2 and parts[2] else "ro"
        volumes[host_path] = {"bind": container_path, "mode": mode}

    tmpfs = {str(vol): "" for vol in policy.filesystem.ephemeral_volumes or []}

    return {
        "network_mode": "none" if policy.network.default == "deny" else "bridge",
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges"],
        "user": "1000:1000",
        "mem_limit": "768m",
        "nano_cpus": int(1e9),
        "volumes": volumes,
        "tmpfs": tmpfs,
    }


def resolve_sandbox_network_policy(
    worker_id: str,
    chat_network: str | None = None,
    *,
    worker_dir: Path | None = None,
) -> tuple[SecurityPolicy, dict[str, Any]]:
    """
    Política efectiva de red: YAML del worker + override opcional por chat.

  chat_network: valor de agent_config ``sandbox_network_enabled`` (true/false/vacío).
  Si el YAML tiene ``deny``, el override no puede habilitar bridge (Zero-Trust).
    """
    base = load_security_policy(worker_id, worker_dir=worker_dir)
    yaml_default = base.network.default
    toggle_available = yaml_default == "allow"
    cn = (chat_network or "").strip().lower()
    meta: dict[str, Any] = {
        "yaml_default": yaml_default,
        "effective": yaml_default,
        "toggle_available": toggle_available,
        "chat_override": cn if cn in ("true", "false", "1", "0", "on", "off") else None,
    }
    if not toggle_available:
        return base, meta

    effective = base.model_copy(deep=True)
    if cn in ("false", "0", "off"):
        effective.network.default = "deny"
        meta["effective"] = "deny"
    elif cn in ("true", "1", "on"):
        effective.network.default = "allow"
        meta["effective"] = "allow"
    return effective, meta


def resolve_security_policy_for_chat(
    worker_id: str,
    db: Any,
    chat_id: Any,
    *,
    worker_dir: Path | None = None,
) -> tuple[SecurityPolicy, dict[str, Any]]:
    """Carga política del worker y aplica ``sandbox_network_enabled`` del chat si procede."""
    raw = ""
    if db is not None and chat_id is not None:
        try:
            from duckclaw.graphs.on_the_fly_commands import get_chat_state

            raw = get_chat_state(db, chat_id, "sandbox_network_enabled")
        except Exception:
            raw = ""
    return resolve_sandbox_network_policy(worker_id, raw or None, worker_dir=worker_dir)