from __future__ import annotations

from pathlib import Path

from duckclaw.forge.schema import SecurityPolicy, load_security_policy
from duckclaw.graphs.sandbox import ExecutionResult, _is_security_violation


def test_load_security_policy_missing_file_defaults_to_deny() -> None:
    policy = load_security_policy("unknown_worker_xyz", worker_dir=Path("/tmp/does-not-exist"))
    assert isinstance(policy, SecurityPolicy)
    assert policy.network.default == "deny"
    assert policy.secrets.allowed_secrets == []
    assert policy.max_execution_time_seconds <= 600


def test_load_security_policy_finanz_file_is_valid() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    worker_dir = repo_root / "packages" / "agents" / "src" / "duckclaw" / "forge" / "templates" / "finanz"
    policy = load_security_policy("finanz", worker_dir=worker_dir)
    assert isinstance(policy, SecurityPolicy)
    assert policy.network.default == "deny"
    assert policy.max_execution_time_seconds == 45


def test_job_hunter_security_policy_browser_ttl() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    worker_dir = (
        repo_root
        / "packages"
        / "agents"
        / "src"
        / "duckclaw"
        / "forge"
        / "templates"
        / "job_hunter"
    )
    policy = load_security_policy("job_hunter", worker_dir=worker_dir)
    assert policy.network.default == "allow"
    assert policy.max_execution_time_seconds == 300


def test_worker_manifest_browser_sandbox_flag() -> None:
    from duckclaw.workers.manifest import load_manifest

    spec = load_manifest("job_hunter")
    assert spec.browser_sandbox is True
    assert spec.research_config is not None


def test_security_violation_detection_for_ro_and_network_errors() -> None:
    res_ro = ExecutionResult(exit_code=1, stdout="", stderr="OSError: [Errno 30] Read-only file system")
    assert _is_security_violation(res_ro) is True

    res_net = ExecutionResult(exit_code=1, stdout="", stderr="urllib.error.URLError: Temporary failure in name resolution")
    assert _is_security_violation(res_net) is True

    res_other = ExecutionResult(exit_code=1, stdout="", stderr="ValueError: invalid literal")
    assert _is_security_violation(res_other) is False

