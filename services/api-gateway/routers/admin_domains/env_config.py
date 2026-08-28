from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from routers.admin_domains.admin_common import (
    actor_from_header,
    mask_secret,
    problem,
    repo_root,
    require_admin_key,
)

router = APIRouter(tags=["admin-env-config"])

_ENV_ALLOW_PREFIXES = (
    "ANDROID_",
    "TELEGRAM_",
    "DUCKDB_",
    "DUCKCLAW_",
    "LANGCHAIN_",
    "OPENAI_",
    "GROQ_",
    "DEEPSEEK_",
)
_ENV_ALLOW_EXACT = frozenset({"LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "REDIS_URL"})


class EnvPatchBody(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


def env_file() -> Path:
    raw_root = (os.environ.get("DUCKCLAW_ROOT") or "").strip()
    if raw_root:
        candidate = Path(raw_root) / ".env"
        if candidate.is_file():
            return candidate
    code_root = Path(__file__).resolve().parents[4]
    code_env = code_root / ".env"
    if code_env.is_file():
        return code_env
    return repo_root() / ".env"


def read_env_key_unmasked(key: str) -> str:
    env_path = env_file()
    if not env_path.is_file():
        return ""
    want = (key or "").strip()
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        if k.strip() == want:
            return v.strip().strip("'\"")
    return ""


def is_env_key_allowed(key: str) -> bool:
    k = (key or "").strip()
    if not k or k.startswith("#"):
        return False
    if k in _ENV_ALLOW_EXACT:
        return True
    return any(k.startswith(p) for p in _ENV_ALLOW_PREFIXES)


def merge_env_lines(values: dict[str, str]) -> tuple[Path, list[str]]:
    """Actualiza .env en disco; retorna (backup_path, claves_actualizadas)."""
    env_path = env_file()
    if not env_path.is_file():
        raise problem(404, ".env no encontrado", str(env_path))
    backup = env_path.with_suffix(".env.bak")
    shutil.copy2(env_path, backup)
    lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
    key_to_idx: dict[str, int] = {}
    for i, raw in enumerate(lines):
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key_to_idx[s.split("=", 1)[0].strip()] = i
    updated: list[str] = []
    for k, v in values.items():
        if not is_env_key_allowed(k):
            raise problem(400, "Clave no permitida", k)
        line = f"{k}={v}\n"
        if k in key_to_idx:
            lines[key_to_idx[k]] = line
        else:
            lines.append(line)
        updated.append(k)
    env_path.write_text("".join(lines), encoding="utf-8")
    for k, v in values.items():
        os.environ[k] = v
    return backup, updated


@router.get("/env", dependencies=[Depends(require_admin_key)])
async def get_env_config() -> dict[str, Any]:
    env_path = env_file()
    values: dict[str, str] = {}
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            if is_env_key_allowed(k):
                values[k] = mask_secret(v.strip().strip("'\""))
    return {"path": str(env_path), "values": values}


@router.patch("/env", dependencies=[Depends(require_admin_key)])
async def patch_env_config(
    body: EnvPatchBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    raise problem(
        410,
        "Edición genérica de .env retirada",
        "Usa Runtime Settings para configuración visible y Secret Settings para API keys.",
    )
