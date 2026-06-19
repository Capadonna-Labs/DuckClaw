from __future__ import annotations


def test_resilience_flow_initial_suffix_and_output_fields(monkeypatch) -> None:
    from duckclaw.manager import resilience_flow

    monkeypatch.setattr(resilience_flow, "plan_max_attempts_from_env", lambda: 4)
    assert resilience_flow._initial_replan_state() == {
        "plan_attempt_index": 0,
        "plan_max_attempts": 4,
        "plan_failure_reasons": [],
        "replan_requested": False,
    }

    monkeypatch.setattr(resilience_flow, "replan_enabled", lambda: True)
    retry_task = resilience_flow._planned_task_with_replan_suffix(
        "Consulta las tablas disponibles.",
        plan_attempt_index=1,
        plan_max_attempts=4,
    )
    assert retry_task.startswith("Consulta las tablas disponibles.")
    assert "2" in retry_task
    assert "4" in retry_task

    assert resilience_flow._replan_output_fields(
        replan_after=True,
        exhausted_final=False,
        next_plan_attempt=2,
        max_attempts=4,
        failure_reasons=["inferencia caída"],
    ) == {
        "replan_requested": True,
        "plan_attempt_index": 2,
        "plan_failure_reasons": ["inferencia caída"],
    }
    assert resilience_flow._replan_output_fields(
        replan_after=False,
        exhausted_final=False,
        next_plan_attempt=0,
        max_attempts=4,
        failure_reasons=["ignorado"],
    ) == {
        "replan_requested": False,
        "plan_attempt_index": 0,
        "plan_failure_reasons": [],
    }


def test_manager_resilience_flow_helpers_live_in_manager_module() -> None:
    from duckclaw.manager import resilience_flow

    assert callable(resilience_flow._initial_replan_state)
    assert callable(resilience_flow._planned_task_with_replan_suffix)
    assert callable(resilience_flow._replan_output_fields)


def test_manager_worker_reply_formatting_helpers_live_in_manager_module() -> None:
    from duckclaw.manager import worker_reply_formatting

    assert callable(worker_reply_formatting._strip_leading_subagent_instance_headers)
    assert callable(worker_reply_formatting._worker_base_from_subagent_label)
    assert callable(worker_reply_formatting._reply_already_has_worker_header)
    assert callable(worker_reply_formatting._prepend_subagent_label_once)
