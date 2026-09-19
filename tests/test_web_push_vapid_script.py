import base64
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/generate_web_push_vapid.py"


def _decode_nopad(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * ((4 - len(value) % 4) % 4))


def test_generate_vapid_keys_shape() -> None:
    namespace: dict[str, object] = {}
    exec(SCRIPT.read_text(encoding="utf-8"), namespace)
    keys = namespace["generate_vapid_keys"]("mailto:test@example.com")
    public_key = getattr(keys, "public_key")
    private_key = getattr(keys, "private_key")
    assert len(_decode_nopad(public_key)) == 65
    assert _decode_nopad(public_key)[0] == 4
    assert len(_decode_nopad(private_key)) == 32
    assert getattr(keys, "subject") == "mailto:test@example.com"


def test_generate_vapid_cli_outputs_env_lines() -> None:
    out = subprocess.check_output(
        [sys.executable, str(SCRIPT), "--subject", "mailto:test@example.com"],
        text=True,
    )
    assert "WEB_PUSH_VAPID_PUBLIC_KEY=" in out
    assert "WEB_PUSH_VAPID_PRIVATE_KEY=" in out
    assert "WEB_PUSH_SUBJECT=mailto:test@example.com" in out