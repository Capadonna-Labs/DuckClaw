"""Regression: `_android_ui_dump` must retry past uiautomator's transient
"UI not idle" failures instead of surfacing a contentless error on the first miss."""

from __future__ import annotations

from unittest.mock import patch

from duckclaw.mcp_android_adb import _android_ui_dump


def test_succeeds_on_first_attempt_no_sleep() -> None:
    calls: list[list[str]] = []

    def fake_run_adb(args, *, timeout=15.0):
        calls.append(args)
        if "uiautomator" in args:
            return 0, "", ""
        return 0, "<hierarchy/>", ""

    with patch("duckclaw.mcp_android_adb._run_adb", side_effect=fake_run_adb), patch(
        "duckclaw.mcp_android_adb.time.sleep"
    ) as sleep_mock:
        code, out, err = _android_ui_dump("serial1")

    assert (code, out, err) == (0, "<hierarchy/>", "")
    sleep_mock.assert_not_called()


def test_retries_past_transient_failure_then_succeeds() -> None:
    dump_attempts = 0

    def fake_run_adb(args, *, timeout=15.0):
        nonlocal dump_attempts
        if "uiautomator" in args:
            dump_attempts += 1
            if dump_attempts == 1:
                return 1, "", ""  # transient miss, empty stderr (the reported bug)
            return 0, "", ""
        return 0, "<hierarchy/>", ""

    with patch("duckclaw.mcp_android_adb._run_adb", side_effect=fake_run_adb), patch(
        "duckclaw.mcp_android_adb.time.sleep"
    ) as sleep_mock:
        code, out, err = _android_ui_dump("serial1")

    assert (code, out, err) == (0, "<hierarchy/>", "")
    assert dump_attempts == 2
    sleep_mock.assert_called_once()


def test_falls_back_to_stdout_when_stderr_empty() -> None:
    """Some devices print the uiautomator diagnostic to stdout, not stderr —
    the old code discarded the dump command's stdout entirely."""

    def fake_run_adb(args, *, timeout=15.0):
        if "uiautomator" in args:
            return 1, "ERROR: could not get idle state.", ""
        return 0, "<hierarchy/>", ""

    with patch("duckclaw.mcp_android_adb._run_adb", side_effect=fake_run_adb), patch(
        "duckclaw.mcp_android_adb.time.sleep"
    ):
        code, out, err = _android_ui_dump("serial1", retries=0)

    assert code == 1
    assert out == ""
    assert err == "ERROR: could not get idle state."


def test_exhausts_retries_and_returns_last_error() -> None:
    def fake_run_adb(args, *, timeout=15.0):
        if "uiautomator" in args:
            return 1, "", "permission denied"
        return 0, "<hierarchy/>", ""

    with patch("duckclaw.mcp_android_adb._run_adb", side_effect=fake_run_adb), patch(
        "duckclaw.mcp_android_adb.time.sleep"
    ) as sleep_mock:
        code, out, err = _android_ui_dump("serial1", retries=2, retry_delay=0.01)

    assert code == 1
    assert err == "permission denied"
    assert sleep_mock.call_count == 2
