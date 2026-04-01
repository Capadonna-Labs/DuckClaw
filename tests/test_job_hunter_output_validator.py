"""Validador de egress Job-Hunter (URLs plantilla / placeholders)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.parametrize(
    "text,expect_block",
    [
        ("Oferta: https://jobs.example.com/foo", True),
        ("Ver https://example.org/path", True),
        ("Postula: https://acme.com/jobs/1?pid=123456", True),
        ("https://localhost/jobs", True),
        ("http://127.0.0.1:8080/x", True),
        ("Lever real: https://jobs.lever.co/acme/uuid", False),
        ("LinkedIn https://www.linkedin.com/jobs/view/12345", False),
    ],
)
def test_job_hunter_reply_should_block(text: str, expect_block: bool) -> None:
    from duckclaw.forge.atoms.job_hunter_output_validator import job_hunter_reply_should_block

    blocked, reason = job_hunter_reply_should_block(text)
    assert blocked is expect_block
    if expect_block:
        assert reason


def test_spec_is_job_hunter() -> None:
    from duckclaw.forge.atoms.job_hunter_output_validator import spec_is_job_hunter

    assert spec_is_job_hunter(SimpleNamespace(worker_id="Job-Hunter", logical_worker_id="job_hunter"))
    assert not spec_is_job_hunter(SimpleNamespace(worker_id="finanz", logical_worker_id="finanz"))
