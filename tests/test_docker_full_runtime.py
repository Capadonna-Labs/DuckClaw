from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILES = [
    ROOT / "deploy/docker/docker-compose.yml",
    ROOT / "deploy/docker/docker-compose.release.yml",
    ROOT / "packages/desktop-docker/src-tauri/resources/stack/docker-compose.yml",
]


def test_docker_full_compose_includes_persistent_heartbeat() -> None:
    for path in COMPOSE_FILES:
        text = path.read_text(encoding="utf-8")
        assert "  heartbeat:\n" in text
        assert 'command: ["python", "services/heartbeat/main.py"]' in text
        assert "DUCKCLAW_PROCESS_ROLE: heartbeat" in text
        assert "restart: unless-stopped" in text


def test_gateway_image_bundles_heartbeat_service() -> None:
    dockerfile = (ROOT / "docker/gateway/Dockerfile").read_text(encoding="utf-8")
    assert "COPY services/heartbeat/ services/heartbeat/" in dockerfile


def test_docker_full_publishes_gateway_and_admin_on_localhost_by_default() -> None:
    for path in COMPOSE_FILES:
        text = path.read_text(encoding="utf-8")
        for port in ("8000", "3001"):
            assert f'"${{DUCKCLAW_BIND_ADDR:-127.0.0.1}}:{port}:{port}"' in text, path
            assert f'"{port}:{port}"' not in text, path   # a bare mapping publishes on every interface
