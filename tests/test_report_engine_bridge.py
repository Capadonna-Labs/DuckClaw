"""Report Engine bridge — escrituras sincronizadas y políticas de tools."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from duckclaw.forge.skills.report_engine_bridge import register_report_template


def test_open_hub_db_reuses_worker_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw import DuckClaw
    from duckclaw.forge.skills.report_engine_bridge import _open_hub_db
    from duckclaw.forge.skills.report_engine_hub_context import set_report_engine_hub_db

    hub = "/tmp/hub-axis.duckdb"
    worker_db = DuckClaw(hub, read_only=False, engine="python")
    monkeypatch.setattr("duckclaw.forge.skills.report_engine_bridge._hub_db_path", lambda: hub)
    set_report_engine_hub_db(worker_db)
    opened = _open_hub_db()
    assert opened is worker_db


def test_register_report_template_surfaces_db_writer_failure(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from docx import Document

    docx_path = tmp_path / "informe.docx"
    doc = Document()
    doc.add_paragraph("Informe mensual")
    doc.save(str(docx_path))

    monkeypatch.setattr(
        "duckclaw.forge.rag.knowledge_paths.resolve_readable_document_path",
        lambda **_: docx_path,
    )
    monkeypatch.setattr(
        "duckclaw.forge.skills.report_engine_bridge._hub_db_path",
        lambda: str(tmp_path / "hub.duckdb"),
    )
    monkeypatch.setattr(
        "duckclaw.forge.skills.report_engine_bridge._session_scope",
        lambda: ("default", "user@example.com", "proj-1"),
    )

    with patch(
        "duckclaw.db_write_queue.enqueue_or_apply_duckdb_write_sync",
        return_value="task-abc",
    ):
        with patch("duckclaw.spawn_profile.spawn_inline_writes_enabled", return_value=False):
            with patch(
                "duckclaw.db_write_fire_and_forget.write_poll_timeout_sec",
                return_value=10.0,
            ):
                with patch(
                    "duckclaw.db_write_fire_and_forget.wait_write_task",
                    return_value=MagicMock(status="failed", detail="ACL denegado"),
                ):
                    raw = register_report_template(
                        "INFORME MENSUAL.docx",
                        "Informe mensual",
                    )
    payload = json.loads(raw)
    assert "error" in payload
    assert "ACL denegado" in payload["error"]


def test_dispatch_write_polls_even_when_env_poll_is_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """Con DUCKCLAW_WRITE_POLL_SEC=0 el gateway es fire-and-forget; Report Engine no."""
    from duckclaw.forge.skills.report_engine_bridge import _dispatch_write

    waited: list[float] = []

    monkeypatch.setattr(
        "duckclaw.forge.skills.report_engine_bridge._session_scope",
        lambda: ("default", "user@example.com", ""),
    )
    monkeypatch.setattr(
        "duckclaw.forge.skills.report_engine_bridge._hub_db_path",
        lambda: "/tmp/hub.duckdb",
    )
    monkeypatch.setattr(
        "duckclaw.db_write_queue.enqueue_or_apply_duckdb_write_sync",
        lambda **_: "task-xyz",
    )
    monkeypatch.setattr(
        "duckclaw.spawn_profile.spawn_inline_writes_enabled",
        lambda: False,
    )
    monkeypatch.setattr(
        "duckclaw.db_write_fire_and_forget.write_poll_timeout_sec",
        lambda: 0.0,
    )

    def _wait(task_id: str, timeout_sec: float = 0):
        waited.append(timeout_sec)
        return MagicMock(status="success", detail="")

    monkeypatch.setattr("duckclaw.db_write_fire_and_forget.wait_write_task", _wait)
    _dispatch_write({"command_type": "create_report_instance", "instance_id": "rpt_x"})
    assert waited and waited[0] >= 30.0


def test_framework_pack_includes_report_engine_guidance() -> None:
    from duckclaw.framework_policy_pack import get_framework_policy_content

    content = get_framework_policy_content("directive", "report_engine")
    assert content
    assert "REPORT ENGINE" in content
    assert "render_report_instance" in content
    assert "patch_report_section" in content
    assert "extract_document_text" in content
    assert "Disambiguación de intención" in content
    assert "informe mensual" in content.lower()
    assert "append_images_to_report" in content
    assert "convert_document" not in content

    default = get_framework_policy_content("system_prompt", "default")
    assert default
    assert "write_output_document" in default


def test_generate_report_docx_discovers_markdown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.forge.skills.report_engine_bridge import _discover_markdown_relative_path

    out_root = tmp_path / "vault"
    informes = out_root / "Informes"
    informes.mkdir(parents=True)
    target = informes / "INFORME MENSUAL N°4 - JUNIO 2026.md"
    target.write_text("# Informe", encoding="utf-8")
    other = informes / "borrador.md"
    other.write_text("x", encoding="utf-8")

    monkeypatch.setattr(
        "duckclaw.forge.rag.knowledge_paths.knowledge_output_roots",
        lambda: [out_root],
    )

    rel = _discover_markdown_relative_path(report_title="INFORME MENSUAL N°4 - JUNIO 2026")
    assert rel == "Informes/INFORME MENSUAL N°4 - JUNIO 2026.md"


def test_generate_report_docx_from_markdown_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.forge.skills.report_engine_bridge import generate_report_docx_from_markdown

    calls: list[str] = []

    monkeypatch.setattr(
        "duckclaw.forge.skills.report_engine_bridge._resolve_registered_template_id",
        lambda **_: ("rtpl_existing", [{"id": "resumen_ejecutivo", "label": "Resumen"}]),
    )
    monkeypatch.setattr(
        "duckclaw.forge.skills.report_engine_bridge._read_markdown_for_report",
        lambda **_: ("# Informe\n\nContenido mensual", "Informes/informe.md"),
    )
    monkeypatch.setattr(
        "duckclaw.forge.skills.report_engine_bridge.create_report_instance",
        lambda **_: json.dumps({"instance_id": "rpt_abc", "template_id": "rtpl_existing", "status": "draft"}),
    )

    def _patch(**kwargs: object) -> str:
        calls.append(str(kwargs.get("section_id")))
        return json.dumps({"status": "updated", "section_id": kwargs.get("section_id")})

    monkeypatch.setattr("duckclaw.forge.skills.report_engine_bridge.patch_report_section", _patch)
    monkeypatch.setattr(
        "duckclaw.forge.skills.report_engine_bridge.render_report_instance",
        lambda iid: json.dumps(
            {"path": "/out/Informe_N_4_rpt_abc.docx", "relative_path": "Informe_N_4_rpt_abc.docx", "format": "docx"}
        ),
    )

    raw = generate_report_docx_from_markdown(
        template_docx_path="INFORME MENSUAL.docx",
        report_title="Informe N°4",
        markdown_relative_path="Informes/informe.md",
        period_key="2026-06",
    )
    payload = json.loads(raw)
    assert payload["instance_id"] == "rpt_abc"
    assert payload["relative_path"] == "Informe_N_4_rpt_abc.docx"
    assert calls == ["resumen_ejecutivo"]


def test_create_blank_document_blocks_when_conversation_draft_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.forge.skills import report_engine_bridge as bridge

    monkeypatch.setattr(
        bridge,
        "list_report_instances",
        lambda limit=20: json.dumps(
            {
                "instances": [
                    {
                        "instance_id": "rpt_existing",
                        "title": "Evidencias 1.1-1.3",
                        "same_conversation": True,
                    }
                ],
                "resume_suggestion": "rpt_existing",
                "count": 1,
            }
        ),
    )

    raw = bridge.create_blank_document(title="Evidencia 1.4 sola")
    payload = json.loads(raw)
    assert "error" in payload
    assert payload.get("resume_instance_id") == "rpt_existing"
    assert "append_images_to_report" in (payload.get("hint") or "")


def test_append_images_to_report_fills_next_free_slot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from duckclaw.forge.skills import report_engine_bridge as bridge
    from duckclaw.report_engine.blank_template import BLANK_SECTION_SCHEMA
    from duckclaw.report_engine.state import init_state_from_schema

    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

    state = init_state_from_schema(BLANK_SECTION_SCHEMA)
    state["sections"]["imagen_1"]["content"] = "/old/a.png"
    state["sections"]["imagen_1"]["status"] = "complete"
    state["sections"]["imagen_2"]["content"] = "/old/b.png"
    state["sections"]["imagen_2"]["status"] = "complete"
    state["sections"]["imagen_3"]["content"] = "/old/c.png"
    state["sections"]["imagen_3"]["status"] = "complete"

    monkeypatch.setattr(bridge, "_session_scope", lambda: ("default", "samuel@x.com", ""))
    monkeypatch.setattr(bridge, "_ensure_blank_template_up_to_date", lambda *_a, **_k: "rtpl_blank")
    monkeypatch.setattr(bridge, "_open_hub_db", lambda: object())
    monkeypatch.setattr(bridge, "_close_hub_db_if_owned", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "duckclaw.report_engine.admin_report_read.get_report_instance",
        lambda *_a, **_k: {
            "instance_id": "rpt_ev",
            "state": state,
            "template_id": "rtpl_blank",
        },
    )
    monkeypatch.setattr(
        "duckclaw.report_engine.admin_report_read.actor_can_access_instance",
        lambda *_a, **_k: True,
    )

    patched: list[str] = []

    def _patch_img(**kwargs: object) -> str:
        patched.append(str(kwargs.get("section_id")))
        return json.dumps({"ok": True, "section_id": kwargs.get("section_id")})

    monkeypatch.setattr(bridge, "patch_report_image", _patch_img)
    monkeypatch.setattr(
        bridge,
        "patch_report_section",
        lambda **kwargs: json.dumps({"ok": True, "section_id": kwargs.get("section_id")}),
    )

    raw = bridge.append_images_to_report(
        instance_id="rpt_ev",
        image_paths=str(img),
        captions="Evidencia ejecución 1.4",
    )
    payload = json.loads(raw)
    assert payload.get("instance_id") == "rpt_ev"
    assert payload["images_appended"][0]["section_id"] == "imagen_4"
    assert patched == ["imagen_4"]


def test_decode_admin_images_allows_up_to_15() -> None:
    import sys

    gw = Path(__file__).resolve().parent.parent / "services" / "api-gateway"
    if str(gw) not in sys.path:
        sys.path.insert(0, str(gw))
    from core import vlm_ingest as vlm

    tiny = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    images = [{"mime_type": "image/png", "data_base64": tiny} for _ in range(15)]
    decoded = vlm.decode_admin_images_payload(images)
    assert len(decoded) == 15
    with pytest.raises(ValueError, match="máximo 15"):
        vlm.decode_admin_images_payload(images + [images[0]])


def test_resume_score_prefers_multi_evidence_over_complement() -> None:
    from duckclaw.forge.skills.report_engine_bridge import _pick_resume, _resume_score

    complement = {
        "instance_id": "rpt_0f5f3213b0",
        "title": "EVIDENCIA – EJECUCIÓN 1.4 – JULIO 2025",
        "output_filename": "EVIDENCIA_EJECUCION_1.4_JULIO_2025_rpt_0f5f3213b0.docx",
        "same_conversation": True,
        "status": "ready",
        "images_filled": 2,
        "progress": 40,
    }
    main = {
        "instance_id": "rpt_58e9d22888",
        "title": "EVIDENCIAS – EJECUCIONES 1.1 A 1.4 – JULIO 2025",
        "output_filename": "EVIDENCIAS_EJECUCIONES_1.1_A_1.4_JULIO_2025_rpt_58e9d22888.docx",
        "same_conversation": True,
        "status": "ready",
        "images_filled": 3,
        "progress": 70,
    }
    assert _resume_score(main) > _resume_score(complement)
    assert _pick_resume([complement, main]) == "rpt_58e9d22888"
    assert (
        _pick_resume(
            [complement, main],
            query="EVIDENCIAS_EJECUCIONES_1.1_A_1.4_JULIO_2025_rpt_58e9d22888.docx",
        )
        == "rpt_58e9d22888"
    )


def test_resolve_report_instance_by_filename(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.forge.skills import report_engine_bridge as bridge

    monkeypatch.setattr(
        bridge,
        "list_report_instances",
        lambda limit=50, query="": json.dumps(
            {
                "instances": [
                    {
                        "instance_id": "rpt_0f5f3213b0",
                        "title": "EVIDENCIA 1.4",
                        "output_filename": "EVIDENCIA_EJECUCION_1.4_JULIO_2025_rpt_0f5f3213b0.docx",
                        "same_conversation": True,
                        "status": "ready",
                        "images_filled": 1,
                        "progress": 30,
                        "next_free_slot": "imagen_2",
                    },
                    {
                        "instance_id": "rpt_58e9d22888",
                        "title": "EVIDENCIAS 1.1 A 1.4",
                        "output_filename": "EVIDENCIAS_EJECUCIONES_1.1_A_1.4_JULIO_2025_rpt_58e9d22888.docx",
                        "same_conversation": True,
                        "status": "ready",
                        "images_filled": 3,
                        "progress": 70,
                        "next_free_slot": "imagen_4",
                    },
                ],
                "resume_suggestion": "rpt_58e9d22888",
                "count": 2,
            }
        ),
    )
    raw = bridge.resolve_report_instance(
        "EVIDENCIAS_EJECUCIONES_1.1_A_1.4_JULIO_2025_rpt_58e9d22888.docx"
    )
    payload = json.loads(raw)
    assert payload["instance_id"] == "rpt_58e9d22888"
