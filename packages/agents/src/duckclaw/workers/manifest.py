"""Load and validate worker manifest.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import os
_DEFAULT_FILESYSTEM_WORKER_ID = "default"


def _is_default_filesystem_worker(worker_id: str) -> bool:
    return (worker_id or "").strip().lower() == _DEFAULT_FILESYSTEM_WORKER_ID


def _reject_non_default_filesystem_worker(worker_id: str) -> None:
    if _is_default_filesystem_worker(worker_id):
        return
    raise FileNotFoundError(
        "Only the default filesystem worker may be loaded from layout; "
        f"extra workers must come from the DB catalog: {worker_id}"
    )


def _find_templates_root() -> Path:
    """Legacy fallback; canónico: ``duckclaw.forge.WORKERS_TEMPLATES_DIR`` (forge/seed o catálogo DB)."""
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
    """Return worker dir: catálogo DB / forge/seed ``<worker_id>/`` (o legacy ``templates/workers/<id>/``)."""
    _reject_non_default_filesystem_worker(worker_id)
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


def load_manifest(
    worker_id: str,
    templates_root: Optional[Path] = None,
    db: Any = None,
    tenant_id: str = "default",
) -> WorkerSpec:
    """Load WorkerSpec from DB catalog (if ``db`` provided) or filesystem fallback."""
    if db is not None:
        try:
            from duckclaw.catalog_worker import load_manifest_from_catalog

            return load_manifest_from_catalog(db, worker_id, tenant_id)
        except Exception:
            if not _is_default_filesystem_worker(worker_id):
                raise

    worker_dir = get_worker_dir(worker_id, templates_root)
    manifest_path = worker_dir / "manifest.yaml"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest.yaml not found in {worker_dir}")

    try:
        import yaml
    except ImportError:
        raw = manifest_path.read_text(encoding="utf-8")
        data = _minimal_yaml_parse(raw)
    else:
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}

    if not isinstance(data, dict):
        raise ValueError("manifest.yaml must be a YAML object")

    return build_spec_from_manifest(data, worker_id, worker_dir)


def _normalize_skill_name(raw: Any) -> str:
    return str(raw or "").strip().lower().replace("-", "_")


def _parse_skill_bindings(skills_list: list[Any]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """Parse manifest skill declarations without knowing vendor/domain names."""
    skill_names: list[str] = []
    skill_configs: dict[str, dict[str, Any]] = {}

    def _add_skill(name: Any, config: Any = None) -> None:
        normalized = _normalize_skill_name(name)
        if not normalized:
            return
        if normalized not in skill_names:
            skill_names.append(normalized)
        if normalized not in skill_configs:
            skill_configs[normalized] = (
                dict(config) if isinstance(config, dict) else {}
            )

    for item in skills_list:
        if isinstance(item, str):
            _add_skill(item)
            continue
        if not isinstance(item, dict):
            continue
        raw_name = item.get("name")
        if isinstance(raw_name, str):
            raw_config = item.get("config")
            if raw_config is None:
                raw_config = {
                    str(k): v
                    for k, v in item.items()
                    if str(k) not in {"name", "id"}
                }
            _add_skill(raw_name, raw_config)
            continue
        if len(item) == 1:
            name, config = next(iter(item.items()))
            _add_skill(name, config)

    return skill_names, skill_configs


def build_spec_from_manifest(
    data: dict,
    worker_id: str,
    worker_dir: Path,
) -> WorkerSpec:
    """Build WorkerSpec from parsed manifest dict (filesystem or catalog source)."""
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
    skills_names, skill_configs = _parse_skill_bindings(skills_list)
    try:
        from duckclaw.framework_tool_pack import (
            ensure_baseline_skill_configs,
            ensure_baseline_skills,
        )

        skills_names = ensure_baseline_skills(skills_names, manifest=data)
        skill_configs = ensure_baseline_skill_configs(
            skill_configs,
            skills=skills_names,
            manifest=data,
        )
    except Exception:
        pass
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
    allowed_tables = data.get("allowed_tables") or []
    if isinstance(allowed_tables, str):
        allowed_tables = [t.strip() for t in allowed_tables.split(",") if t.strip()]
    read_only = bool(data.get("read_only", False))

    forge_shared_db_path_env: Optional[str] = None
    forge_apply_schema_to_shared = False
    forge_vault_binding: Optional[dict] = None
    fc = data.get("forge_context")
    if isinstance(fc, dict):
        forge_shared_db_path_env = (fc.get("shared_db_path_env") or "").strip() or None
        forge_apply_schema_to_shared = bool(fc.get("apply_main_schema_to_shared"))
        try:
            from duckclaw.vaults import normalize_vault_binding

            forge_vault_binding = normalize_vault_binding(fc.get("vault_binding"))
        except Exception:
            forge_vault_binding = None

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

    field_reflection_config: Optional[dict] = None
    fr = data.get("field_reflection")
    if isinstance(fr, dict):
        field_reflection_config = fr
    elif fr is True:
        field_reflection_config = {"enabled": True}
    elif fr is False:
        field_reflection_config = {"enabled": False}

    agent_node_heuristic_first_tool: bool | None = None
    agent_node_max_tool_rounds: int | None = None
    _anc = data.get("agent_node")
    if isinstance(_anc, dict):
        if "heuristic_first_tool" in _anc:
            agent_node_heuristic_first_tool = bool(_anc.get("heuristic_first_tool"))
        _mtr = _anc.get("max_tool_rounds")
        if _mtr is not None:
            try:
                agent_node_max_tool_rounds = max(1, int(_mtr))
            except (TypeError, ValueError):
                agent_node_max_tool_rounds = None

    # Telegram / egress: síntesis LLM para evitar JSON crudo (default on; docs/architecture/GATEWAY_PROCESS_BOUNDARIES.md)
    _enl = data.get("egress_natural_language_synthesis")
    if _enl is None:
        egress_natural_language_synthesis = True
    elif isinstance(_enl, str):
        egress_natural_language_synthesis = _enl.strip().lower() not in ("0", "false", "no", "off")
    else:
        egress_natural_language_synthesis = bool(_enl)

    tool_orchestration_config: Optional[dict] = None
    if isinstance(data.get("tool_orchestration"), dict):
        tool_orchestration_config = data["tool_orchestration"]

    tool_surface_config: Optional[dict] = None
    if isinstance(data.get("tool_surface"), dict):
        tool_surface_config = data["tool_surface"]

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
        skill_configs=skill_configs,
        risk_level=risk_level,
        inference_config=inference_config,
        homeostasis_config=homeostasis_config,
        context_guard_config=context_guard_config,
        forge_shared_db_path_env=forge_shared_db_path_env,
        forge_apply_schema_to_shared=forge_apply_schema_to_shared,
        forge_vault_binding=forge_vault_binding,
        context_pruning_config=context_pruning_config,
        duckdb_extensions=duckdb_extensions,
        network_access=network_access,
        tool_read_pool=tool_read_pool,
        browser_sandbox=browser_sandbox,
        field_reflection_config=field_reflection_config,
        agent_node_heuristic_first_tool=agent_node_heuristic_first_tool,
        agent_node_max_tool_rounds=agent_node_max_tool_rounds,
        egress_natural_language_synthesis=egress_natural_language_synthesis,
        tool_orchestration_config=tool_orchestration_config,
        tool_surface_config=tool_surface_config,
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
        "skill_configs",
        "risk_level", "inference_config", "homeostasis_config", "context_guard_config",
        "forge_shared_db_path_env", "forge_apply_schema_to_shared", "forge_vault_binding",
        "context_pruning_config",
        "duckdb_extensions",
        "network_access",
        "tool_read_pool",
        "browser_sandbox",
        "field_reflection_config",
        "agent_node_heuristic_first_tool",
        "agent_node_max_tool_rounds",
        "egress_natural_language_synthesis",
        "tool_orchestration_config",
        "tool_surface_config",
        "runtime_policy",
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
        skill_configs: Optional[dict[str, dict[str, Any]]] = None,
        risk_level: str = "conservative",
        inference_config: Optional[dict] = None,
        homeostasis_config: Optional[dict] = None,
        context_guard_config: Optional[dict] = None,
        forge_shared_db_path_env: Optional[str] = None,
        forge_apply_schema_to_shared: bool = False,
        forge_vault_binding: Optional[dict] = None,
        context_pruning_config: Optional[dict] = None,
        duckdb_extensions: Optional[list] = None,
        network_access: bool = False,
        tool_read_pool: bool = True,
        browser_sandbox: bool = False,
        field_reflection_config: Optional[dict] = None,
        agent_node_heuristic_first_tool: bool | None = None,
        agent_node_max_tool_rounds: int | None = None,
        egress_natural_language_synthesis: bool = True,
        tool_orchestration_config: Optional[dict] = None,
        tool_surface_config: Optional[dict] = None,
        runtime_policy: Any = None,
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
        self.skill_configs = {
            _normalize_skill_name(name): dict(config)
            for name, config in (skill_configs or {}).items()
            if _normalize_skill_name(name)
        }
        self.risk_level = risk_level if risk_level in ("aggressive", "conservative") else "conservative"
        self.inference_config = inference_config
        self.homeostasis_config = homeostasis_config
        self.context_guard_config = context_guard_config
        self.forge_shared_db_path_env = forge_shared_db_path_env
        self.forge_apply_schema_to_shared = forge_apply_schema_to_shared
        self.forge_vault_binding = forge_vault_binding
        self.context_pruning_config = context_pruning_config
        self.duckdb_extensions = list(duckdb_extensions or [])
        self.network_access = bool(network_access)
        self.tool_read_pool = bool(tool_read_pool)
        self.browser_sandbox = bool(browser_sandbox)
        self.field_reflection_config = field_reflection_config
        self.agent_node_heuristic_first_tool = agent_node_heuristic_first_tool
        self.agent_node_max_tool_rounds = agent_node_max_tool_rounds
        self.egress_natural_language_synthesis = bool(egress_natural_language_synthesis)
        self.tool_orchestration_config = tool_orchestration_config
        self.tool_surface_config = tool_surface_config
        self.runtime_policy = runtime_policy
