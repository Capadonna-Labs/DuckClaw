"""Tests para detección de puertos locales en estado JSON de Tailscale Funnel."""

from duckops.sovereign.tailscale_funnel import funnel_status_proxied_local_ports


def test_funnel_status_proxied_local_ports_empty() -> None:
    assert funnel_status_proxied_local_ports({}) == set()
    assert funnel_status_proxied_local_ports({"Web": "x"}) == set()


def test_funnel_status_proxied_local_ports_from_handlers() -> None:
    data = {
        "Web": {
            "machine:443": {
                "Handlers": {
                    "/": {"Proxy": "http://127.0.0.1:8000"},
                }
            }
        }
    }
    assert funnel_status_proxied_local_ports(data) == {8000}


def test_funnel_status_proxied_local_ports_multiple() -> None:
    data = {
        "Web": {
            "x": {
                "Handlers": {
                    "a": {"Proxy": "http://127.0.0.1:8000/foo"},
                    "b": {"Proxy": "http://localhost:8888"},
                }
            }
        }
    }
    assert funnel_status_proxied_local_ports(data) == {8000, 8888}
