from __future__ import annotations

from duckclaw.mcp_android_notifications import (
    analyze_notification_ui_dump,
    append_notification_hints_to_ui_dump,
    classify_swipe_result,
    extract_notification_rows,
    is_button_label,
    is_non_dismissible_notification_title,
)


def test_non_dismissible_titles() -> None:
    assert is_non_dismissible_notification_title("Sistema Android")
    assert is_non_dismissible_notification_title("Tarjeta SIM ausente")
    assert not is_non_dismissible_notification_title("WhatsApp")


def test_button_labels_filtered() -> None:
    assert is_button_label("Sí")
    assert is_button_label("Desactivado")
    assert not is_button_label("WhatsApp")


def test_cluster_full_width_rows() -> None:
    raw = (
        '<node text="WhatsApp" bounds="[0,360][1080,420]"/>'
        '<node text="Nuevo mensaje de Juan" bounds="[0,420][1080,510]"/>'
        '<node text="Sí" bounds="[45,179][529,346]"/>'
        '<node text="Sistema Android" bounds="[0,200][1080,350]"/>'
    )
    rows = extract_notification_rows(raw)
    titles = [r["title"] for r in rows]
    assert "Sí" not in titles
    assert "Desactivado" not in titles
    assert "WhatsApp" in titles
    assert "Sistema Android" in titles
    sys_row = next(r for r in rows if r["title"] == "Sistema Android")
    assert sys_row["action"] == "SKIP"
    wa = next(r for r in rows if r["title"] == "WhatsApp")
    assert "Juan" in (wa.get("body") or "")
    assert wa["action"] == "DISMISS"


def test_row_skip_by_body() -> None:
    from duckclaw.mcp_android_notifications import row_should_skip

    assert row_should_skip("Laila", "Sistema Android")
    assert row_should_skip("X", "Se conectó la depuración inalámbrica")
    assert not row_should_skip("Reddit", "AI news platform")


def test_plan_prepended_with_digest() -> None:
    raw = (
        '<node text="Telegram" bounds="[0,400][1080,460]"/>'
        '<node text="Alerta de mercado" bounds="[0,460][1080,540]"/>'
    )
    out = append_notification_hints_to_ui_dump(raw)
    assert out.startswith("[DUCKCLAW_NOTIFICATION_PLAN]")
    assert "digest" in out
    assert "<node" not in out


def test_classify_swipe() -> None:
    assert classify_swipe_result("Swiped from (980, 810) to (80, 810)")["horizontal"]
    assert classify_swipe_result("Swiped from (540, 800) to (540, 1800)")["vertical"]
