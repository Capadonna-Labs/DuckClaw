from __future__ import annotations

from pathlib import Path

from duckops.post_up import resolve_launch_mode, run_post_up_loop


def test_resolve_launch_mode_ui_tui() -> None:
    assert resolve_launch_mode(ui="tui", no_prompt=False, skip_admin=False) == "tui"


def test_resolve_launch_mode_ui_web() -> None:
    assert resolve_launch_mode(ui="web", no_prompt=False, skip_admin=False) == "web"


def test_resolve_launch_mode_no_prompt_exits() -> None:
    assert resolve_launch_mode(ui=None, no_prompt=True, skip_admin=False) == "exit"


def test_resolve_launch_mode_web_becomes_exit_when_skip_admin() -> None:
    assert resolve_launch_mode(ui="web", no_prompt=False, skip_admin=True) == "exit"


def test_post_up_loop_returns_to_menu_after_tui(tmp_path: Path, monkeypatch) -> None:
    prompts = iter(["tui", "exit"])

    monkeypatch.setattr(
        "duckops.post_up.prompt_launch_mode",
        lambda **_k: next(prompts),
    )
    monkeypatch.setattr(
        "duckops.post_up._prepare_admin_for_tui",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "duckops.sovereign.runner.run_sovereign_chat",
        lambda *_a, **_k: 0,
    )

    code = run_post_up_loop(
        tmp_path,
        skip_admin=False,
        no_browser=True,
        ui=None,
        no_prompt=False,
        print_fn=lambda _m: None,
    )
    assert code == 0

