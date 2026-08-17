from __future__ import annotations

from duckclaw.mcp_android_notifications import (
    analyze_notification_ui_dump,
    append_notification_hints_to_ui_dump,
    classify_swipe_result,
    extract_notification_rows,
    is_button_label,
    is_non_dismissible_notification_title,
)


def test_junk_titles_not_dismissible() -> None:
    from duckclaw.mcp_android_notifications import row_should_skip

    assert row_should_skip("Hace 1 hora", "foo")
    assert row_should_skip("Expandir", "Los dispositivos están conectados.")
    assert row_should_skip("El Tiempo", "headline")
    assert not row_should_skip("Bloomberg", "Markets update")


def test_relaxed_width_skips_junk_when_apps_cleared() -> None:
    raw = (
        '<node text="Hace 1 hora" bounds="[48,400][400,460]"/>'
        '<node text="Expandir" bounds="[48,500][400,560]"/>'
        '<node text="El Tiempo" bounds="[48,600][400,660]"/>'
        '<node text="Datos móviles" bounds="[0,200][540,280]"/>'
        '<node text="Bluetooth" bounds="[540,200][1080,280]"/>'
    ) * 50
    hints = analyze_notification_ui_dump(raw)
    assert hints["dismissible"] == []
    assert hints.get("parser_mode") != "relaxed_width" or not hints["dismiss_actions"]


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
    assert row_should_skip("Laila", "Datos móviles")
    assert not row_should_skip("Reddit", "AI news platform")


def test_large_qs_only_dump_emits_plan() -> None:
    qs_nodes = (
        '<node text="Laila" bounds="[0,200][540,280]"/>'
        '<node text="Datos móviles" bounds="[540,200][1080,280]"/>'
        '<node text="Bluetooth" bounds="[0,300][540,380]"/>'
        '<node text="No interrumpir" bounds="[540,300][1080,380]"/>'
    )
    raw = qs_nodes * 200
    out = append_notification_hints_to_ui_dump(raw)
    assert out.startswith("[DUCKCLAW_NOTIFICATION_PLAN]")
    assert "quick_settings_only" in out
    assert "<node" not in out


def test_collapsed_large_dump_emits_plan_without_rows() -> None:
    raw = "<hierarchy>" + ('<node text="foo" bounds="[0,0][1,1]"/>' * 3000) + "</hierarchy>"
    out = append_notification_hints_to_ui_dump(raw)
    assert out.startswith("[DUCKCLAW_NOTIFICATION_PLAN]")
    assert "collapsed_or_unparsed" in out


def test_plan_prepended_with_digest() -> None:
    raw = (
        '<node text="Telegram" bounds="[0,400][1080,460]"/>'
        '<node text="Alerta de mercado" bounds="[0,460][1080,540]"/>'
    )
    out = append_notification_hints_to_ui_dump(raw)
    assert out.startswith("[DUCKCLAW_NOTIFICATION_PLAN]")
    assert "digest" in out
    assert "<node" not in out


def test_multiline_node_bounds_parsed() -> None:
    from duckclaw.mcp_android_notifications import extract_app_hint_rows

    raw = (
        '<node text="Bloomberg" resource-id="android:id/title"\n'
        ' class="android.widget.TextView" bounds="[190,169][878,236]"/>\n'
        '<node text="Markets update" bounds="[190,240][878,300]"/>'
    )
    rows = extract_app_hint_rows(raw)
    assert rows and rows[0]["title"] == "Bloomberg"
    assert rows[0]["swipe"]["y1"] == (169 + 300) // 2


def test_hint_finds_bloomberg_at_notification_y() -> None:
    from duckclaw.mcp_android_notifications import extract_app_hint_rows

    raw = (
        '<node text="Bloomberg" bounds="[48,120][400,180]"/>'
        '<node text="Fed holds rates steady" bounds="[48,185][900,240]"/>'
    )
    rows = extract_app_hint_rows(raw)
    assert rows and rows[0]["title"] == "Bloomberg"
    assert "Fed" in rows[0]["body"]
    assert rows[0]["swipe"]["y1"] == 180


def test_app_hint_uses_real_bounds_and_body() -> None:
    from duckclaw.mcp_android_notifications import extract_app_hint_rows

    raw = (
        '<node text="Bloomberg" bounds="[48,920][400,980]"/>'
        '<node text="Markets plunge on Fed news" bounds="[48,985][900,1040]"/>'
        '<node text="AfterHour" bounds="[48,1100][400,1160]"/>'
        '<node text="geo21208" bounds="[48,1165][300,1210]"/>'
    )
    rows = extract_app_hint_rows(raw)
    by_title = {r["title"]: r for r in rows}
    assert by_title["Bloomberg"]["body"] == "Markets plunge on Fed news"
    assert by_title["Bloomberg"]["swipe"]["y1"] == 980
    assert by_title["AfterHour"]["swipe"]["y1"] == 1155


def test_content_desc_notification_rows() -> None:
    raw = (
        'content-desc="Notificación de AfterHour: geo21208" '
        'content-desc="Notificación de Bloomberg: Markets update" '
        'content-desc="Bloomberg tiene 1 notificación" '
        'content-desc="Datos móviles" content-desc="Bluetooth"'
    )
    rows = extract_notification_rows(raw)
    assert not rows
    from duckclaw.mcp_android_notifications import extract_a11y_notification_rows

    a11y = extract_a11y_notification_rows(
        '<node content-desc="Notificación de AfterHour: geo21208" bounds="[0,500][1080,580]"/>'
        '<node text="extra headline" bounds="[0,580][1080,640]"/>'
    )
    assert a11y[0]["title"] == "AfterHour"
    assert a11y[0]["body"] == "geo21208"
    assert a11y[0]["swipe"]["y1"] == 570
    assert classify_swipe_result("Swiped from (980, 810) to (80, 810)")["horizontal"]
    assert classify_swipe_result("Swiped from (540, 800) to (540, 1800)")["vertical"]
