"""ADF validator accepts Strix security_policy.yaml format."""

from __future__ import annotations

from pathlib import Path


def test_validate_agent_accepts_strix_security_policy(tmp_path: Path) -> None:
    from duckclaw.adf_validator import validate_agent

    agent_dir = tmp_path / "demo-agent"
    agent_dir.mkdir()
    (agent_dir / "manifest.yaml").write_text("id: demo-agent\nname: Demo\n", encoding="utf-8")
    (agent_dir / "system_prompt.md").write_text("# Demo\n", encoding="utf-8")
    (agent_dir / "schema.sql").write_text("-- empty\n", encoding="utf-8")
    (agent_dir / "security_policy.yaml").write_text(
        """
network:
  default: deny
  allow_list: []
filesystem:
  readonly_mounts: []
  ephemeral_volumes:
    - /workspace/output
secrets:
  in_memory_only: true
  allowed_secrets: []
max_execution_time_seconds: 120
""".strip(),
        encoding="utf-8",
    )

    result = validate_agent(agent_dir)
    assert result.valid is True
    assert not any("can_do" in err for err in result.errors)
