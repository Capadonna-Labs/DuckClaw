"""Security policy schemas and loader for Strix sandbox."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Literal

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
    for mount in policy.filesystem.readonly_mounts:
        parts = [p.strip() for p in str(mount).split(":")]
        if len(parts) < 2:
            continue
        host_path = parts[0]
        container_path = parts[1]
        mode = parts[2] if len(parts) > 2 and parts[2] else "ro"
        volumes[host_path] = {"bind": container_path, "mode": mode}

    tmpfs = {str(vol): "" for vol in policy.filesystem.ephemeral_volumes or []}

    return {
        "network_mode": "none" if policy.network.default == "deny" else "bridge",
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges"],
        "user": "1000:1000",
        "mem_limit": "512m",
        "nano_cpus": int(1e9),
        "volumes": volumes,
        "tmpfs": tmpfs,
    }