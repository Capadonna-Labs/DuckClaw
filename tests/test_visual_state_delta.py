"""DTO VisualStateDelta round-trip."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_WRITER = _REPO / "services" / "db-writer"
# append (no insert(0)): db-writer/main.py colisiona con api-gateway/main.py en tests admin.
if str(_WRITER) not in sys.path:
    sys.path.append(str(_WRITER))

from models.visual_state_delta import VisualAssetMutation, VisualStateDelta  # noqa: E402


def test_visual_state_delta_roundtrip() -> None:
    delta = VisualStateDelta(
        tenant_id="default",
        user_id="u1",
        target_db_path="/tmp/test.duckdb",
        mutation=VisualAssetMutation(
            id="550e8400-e29b-41d4-a716-446655440000",
            prompt="a red cube",
            negative_prompt="blur",
            file_path="/repo/db/private/default/artifacts/x.png",
            aspect_ratio="16:9",
            prompt_id_comfy="abc-123",
            operation="img2img_edit",
            source_image_path="/repo/db/private/default/inbound/x.jpg",
        ),
    )
    raw = delta.model_dump_json()
    back = VisualStateDelta.model_validate(json.loads(raw))
    assert back.delta_type == "VISUAL_ASSET_UPSERT"
    assert back.mutation.prompt == "a red cube"
    assert back.mutation.aspect_ratio == "16:9"
    assert back.mutation.operation == "img2img_edit"
    assert "inbound" in back.mutation.source_image_path
