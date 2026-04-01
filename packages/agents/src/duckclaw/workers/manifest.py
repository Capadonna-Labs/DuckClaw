"""Load and validate worker manifest.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import os

# Claves de skills compuestas en manifest (no usar `name` + estas a la vez en el mismo dict).
_SKILL_DICT_RESERVED_KEYS = frozenset(
    {"github", "reddit", "google_trends", "research", "tailscale", "sft", "ibkr", "quant"}
)


def _find_templates_root() -> Path:
    """Project root: packages/agents/templates/workers/."""
    here = Path(__file__).resolve().parent
    # duckclaw/workers -> packages/agents (4 levels up)
    candidates = [
        here.parent.parent.parent.parent,  # packages/agents
        here.parent.parent.parent,         # packages/agents/src
        Path.cwd(),
        Path.cwd() / "packages" / "agents",
    ]
    for parent in candidates:
        d = parent / "templates" / "workers"
        if d.is_dir():
            return parent
    return Path.cwd()


def get_worker_dir(worker_id: str, templates_root: Optional[Path] = None) -> Path:
    """Return worker dir: forge/templates/<worker_id>/ or templates_root/templates/workers/<worker_id>/."""
    if templates_root is not None:
        path = templates_root / "templates" / "workers" / worker_id.strip()
    else:
        try:
            from duckclaw.forge import WORKERS_TEMPLATES_DIR
            path = WORKERS_TEMPLATES_DIR / worker_id.strip()
        except ImportError:
            root = _find_templates_root()
            path = root / "templates" / "workers" / worker_id.strip()
    if not path.is_dir():
        raise FileNotFoundError(f"Worker template not found: {path}")
    return path


def load_manifest(worker_id: str, templates_root: Optional[Path] = None) -> WorkerSpec:
    """Load and validate manifest.yaml for a worker. Raises if missing or invalid."""
    worker_dir = get_worker_dir(worker_id, templates_root)
    manifest_path = worker_dir / "manifest.yaml"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest.yaml not found in {worker_dir}")

    try:
        import yaml
    except ImportError:
        # Minimal YAML parse for required keys
        raw = manifest_path.read_text(encoding="utf-8")
        data = _minimal_yaml_parse(raw)
    else:
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}

    if not isinstance(data, dict):
        raise ValueError("manifest.yaml must be a YAML object")

    name = (data.get("name") or data.get("id") or worker_id).strip()
    logical_worker_id = (data.get("id") or worker_id).strip()
    schema_name = (data.get("schema_name") or data.get("schema") or _default_schema(worker_id)).strip()
    llm = (data.get("llm") or {}).copy() if isinstance(data.get("llm"), dict) else {}
    raw_required = llm.get("required")
    llm_required = (llm.get("model") or "").strip() if raw_required else None
    if raw_required and isinstance(raw_required, str):
        llm_required = raw_required.strip() or llm_required
    temperature = float(llm.get("temperature", 0.2))
    topology = (data.get("topology") or "general").strip().lower()
    skills_list = data.get("skills") or []
    if isinstance(skills_list, str):
        skills_list = [s.strip() for s in skills_list.split(",") if s.strip()]
    # skills: strings (nombres) o dicts (ej. {github: {...}}, {reddit: {...}}, {research: {...}}, ...)
    skills_names = [s for s in skills_list if isinstance(s, str)]
    for s in skills_list:
        if isinstance(s, dict) and not (set(s.keys()) & _SKILL_DICT_RESERVED_KEYS):
            raw_nm = s.get("name")
            if isinstance(raw_nm, str):
                nm = raw_nm.strip()
                if nm and nm not in skills_names:
                    skills_names.append(nm)
    github_config = None
    reddit_config = None
    google_trends_config = None
    research_config = None
    tailscale_config = None
    sft_config = None
    ibkr_config = None
    for s in skills_list:
        if isinstance(s, dict):
            if "github" in s and github_config is None:
                github_config = s["github"] if isinstance(s.get("github"), dict) else {}
            if "reddit" in s and reddit_config is None:
                reddit_config = s["reddit"] if isinstance(s.get("reddit"), dict) else {}
            if "google_trends" in s and google_trends_config is None:
                google_trends_config = s["google_trends"] if isinstance(s.get("google_trends"), dict) else {}
            if "research" in s and research_config is None:
                research_config = s["research"] if isinstance(s.get("research"), dict) else {}
            if "tailscale" in s and tailscale_config is None:
                tailscale_config = s["tailscale"] if isinstance(s.get("tailscale"), dict) else {}
            if "sft" in s and sft_config is None:
                sft_config = s["sft"] if isinstance(s.get("sft"), dict) else {}
            if "ibkr" in s and ibkr_config is None:
                ibkr_config = s["ibkr"] if isinstance(s.get("ibkr"), dict) else {}
    if github_config is None and isinstance(data.get("github"), dict):
        github_config = data["github"]
    if reddit_config is None and isinstance(data.get("reddit"), dict):
        reddit_config = data["reddit"]
    if google_trends_config is None and isinstance(data.get("google_trends"), dict):
        google_trends_config = data["google_trends"]
    if research_config is None and isinstance(data.get("research"), dict):
        research_config = data["research"]
    if tailscale_config is None and isinstance(data.get("tailscale"), dict):
        tailscale_config = data["tailscale"]
    if sft_config is None and isinstance(data.get("sft"), dict):
        sft_config = data["sft"]
    if ibkr_config is None and isinstance(data.get("ibkr"), dict):
        ibkr_config = data["ibkr"]
    quant_config = None
    for s in skills_list:
        if isinstance(s, dict) and "quant" in s and quant_config is None:
            quant_config = s["quant"] if isinstance(s.get("quant"), dict) else {}
    if quant_config is None and isinstance(data.get("quant"), dict):
        quant_config = data["quant"]
    risk_level = str(data.get("risk_level") or "conservative").strip().lower()
    if risk_level not in ("aggressive", "conservative"):
        risk_level = "conservative"
    inference_config = None
    if isinstance(data.get("inference"), dict):
        inference_config = data["inference"]
    homeostasis_config = _load_homeostasis_config(worker_dir, data)
    context_guard_config = None
    if isinstance(data.get("context_guard"), dict):
        context_guard_config = data["context_guard"]
    elif data.get("context_guard") is True:
        context_guard_config = {"enabled": True, "max_retries": 2}
    context_pruning_config: Optional[dict] = None
    if isinstance(data.get("context_pruning"), dict):
        context_pruning_config = data["context_pruning"]
    crm_config = None
    if isinstance(data.get("crm"), dict):
        crm_config = data["crm"]
    elif data.get("crm") is True:
        crm_config = {"enabled": True}
    allowed_tables = data.get("allowed_tables") or []
    if isinstance(allowed_tables, str):
        allowed_tables = [t.strip() for t in allowed_tables.split(",") if t.strip()]
    read_only = bool(data.get("read_only", False))

    forge_shared_db_path_env: Optional[str] = None
    forge_apply_schema_to_shared = False
    fc = data.get("forge_context")
    if isinstance(fc, dict):
        forge_shared_db_path_env = (fc.get("shared_db_path_env") or "").strip() or None
        forge_apply_schema_to_shared = bool(fc.get("apply_main_schema_to_shared"))

    duckdb_extensions: list[str] = []
    mem = data.get("memory")
    if isinstance(mem, dict):
        mem_sql = mem.get("sql")
        if isinstance(mem_sql, dict):
            raw_ext = mem_sql.get("extensions")
            if isinstance(raw_ext, list):
                duckdb_extensions = [str(x).strip() for x in raw_ext if str(x).strip()]
            elif isinstance(raw_ext, str):
                duckdb_extensions = [s.strip() for s in raw_ext.split(",") if s.strip()]
    top_ext = data.get("duckdb_extensions")
    if isinstance(top_ext, list) and top_ext:
        duckdb_extensions = [str(x).strip() for x in top_ext if str(x).strip()]
    elif isinstance(top_ext, str) and top_ext.strip():
        duckdb_extensions = [s.strip() for s in top_ext.split(",") if s.strip()]

    sec = data.get("security")
    network_access = bool(data.get("network_access", False))
    if isinstance(sec, dict) and sec.get("network_access") is not None:
        network_access = bool(sec.get("network_access"))

    tool_read_pool = True
    trp = data.get("tool_read_pool")
    if trp is False or trp == 0:
        tool_read_pool = False
    elif isinstance(trp, str):
        tool_read_pool = trp.strip().lower() not in ("0", "false", "no", "off")

    browser_sandbox = bool(data.get("browser_sandbox", False))

    return WorkerSpec(
        worker_id=worker_id,
        logical_worker_id=logical_worker_id,
        name=name,
        schema_name=schema_name,
        llm_required=llm_required or None,
        temperature=temperature,
        topology=topology,
        skills_list=skills_names,
        allowed_tables=allowed_tables,
        read_only=read_only,
        worker_dir=worker_dir,
        github_config=github_config,
        reddit_config=reddit_config,
        google_trends_config=google_trends_config,
        research_config=research_config,
        tailscale_config=tailscale_config,
        sft_config=sft_config,
        ibkr_config=ibkr_config,
        quant_config=quant_config,
        risk_level=risk_level,
        inference_config=inference_config,
        homeostasis_config=homeostasis_config,
        context_guard_config=context_guard_config,
        crm_config=crm_config,
        forge_shared_db_path_env=forge_shared_db_path_env,
        forge_apply_schema_to_shared=forge_apply_schema_to_shared,
        context_pruning_config=context_pruning_config,
        duckdb_extensions=duckdb_extensions,
        network_access=network_access,
        tool_read_pool=tool_read_pool,
        browser_sandbox=browser_sandbox,
    )


def _load_homeostasis_config(worker_dir: Path, manifest_data: dict) -> Optional[dict]:
    """Load homeostasis config from homeostasis.yaml or manifest homeostasis key."""
    # 1. Try homeostasis.yaml in worker dir
    yaml_path = worker_dir / "homeostasis.yaml"
    if yaml_path.is_file():
        try:
            import yaml
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            if isinstance(data, dict):
                return data.get("homeostasis") or data
        except Exception:
            pass
    # 2. Fallback to manifest homeostasis key
    h = manifest_data.get("homeostasis")
    if isinstance(h, dict):
        return h
    return None


def _default_schema(worker_id: str) -> str:
    return worker_id.lower().replace("-", "_") + "_worker"


def _minimal_yaml_parse(raw: str) -> dict:
    """Minimal YAML parse for key: value and nested key: value (no arrays)."""
    data: dict = {}
    current_key = None
    for line in raw.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if ":" in line:
            k, _, v = line.partition(":")
            k, v = k.strip(), v.strip().strip("'\"").strip()
            if indent == 0:
                data[k] = v
                current_key = k
            elif current_key and indent > 0:
                if current_key not in data or not isinstance(data[current_key], dict):
                    data[current_key] = {}
                data[current_key][k] = v
    return data


class WorkerSpec:
    """Validated worker template specification."""

    __slots__ = (
        "worker_id", "logical_worker_id", "name", "schema_name", "llm_required", "temperature",
        "topology", "skills_list", "allowed_tables", "read_only", "worker_dir",
        "github_config", "reddit_config", "google_trends_config", "research_config", "tailscale_config", "sft_config",
        "ibkr_config", "quant_config", "risk_level", "inference_config", "homeostasis_config", "context_guard_config", "crm_config",
        "forge_shared_db_path_env", "forge_apply_schema_to_shared",
        "context_pruning_config",
        "duckdb_extensions",
        "network_access",
        "tool_read_pool",
        "browser_sandbox",
    )

    def __init__(
        self,
        worker_id: str,
        logical_worker_id: str,
        name: str,
        schema_name: str,
        llm_required: Optional[str],
        temperature: float,
        topology: str,
        skills_list: list,
        allowed_tables: list,
        read_only: bool,
        worker_dir: Path,
        github_config: Optional[dict] = None,
        reddit_config: Optional[dict] = None,
        google_trends_config: Optional[dict] = None,
        research_config: Optional[dict] = None,
        tailscale_config: Optional[dict] = None,
        sft_config: Optional[dict] = None,
        ibkr_config: Optional[dict] = None,
        quant_config: Optional[dict] = None,
        risk_level: str = "conservative",
        inference_config: Optional[dict] = None,
        homeostasis_config: Optional[dict] = None,
        context_guard_config: Optional[dict] = None,
        crm_config: Optional[dict] = None,
        forge_shared_db_path_env: Optional[str] = None,
        forge_apply_schema_to_shared: bool = False,
        context_pruning_config: Optional[dict] = None,
        duckdb_extensions: Optional[list] = None,
        network_access: bool = False,
        tool_read_pool: bool = True,
        browser_sandbox: bool = False,
    ):
        self.worker_id = worker_id
        self.logical_worker_id = logical_worker_id
        self.name = name
        self.schema_name = schema_name
        self.llm_required = llm_required
        self.temperature = temperature
        self.topology = topology
        self.skills_list = skills_list
        self.allowed_tables = allowed_tables
        self.read_only = read_only
        self.worker_dir = worker_dir
        self.github_config = github_config
        self.reddit_config = reddit_config
        self.google_trends_config = google_trends_config
        self.research_config = research_config
        self.tailscale_config = tailscale_config
        self.sft_config = sft_config
        self.ibkr_config = ibkr_config
        self.quant_config = quant_config
        self.risk_level = risk_level if risk_level in ("aggressive", "conservative") else "conservative"
        self.inference_config = inference_config
        self.homeostasis_config = homeostasis_config
        self.context_guard_config = context_guard_config
        self.crm_config = crm_config
        self.forge_shared_db_path_env = forge_shared_db_path_env
        self.forge_apply_schema_to_shared = forge_apply_schema_to_shared
        self.context_pruning_config = context_pruning_config
        self.duckdb_extensions = list(duckdb_extensions or [])
        self.network_access = bool(network_access)
        self.tool_read_pool = bool(tool_read_pool)
        self.browser_sandbox = bool(browser_sandbox)
