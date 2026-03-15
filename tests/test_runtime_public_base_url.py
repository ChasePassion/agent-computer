from __future__ import annotations

import json

from agent_computer import runtime


def test_read_public_endpoints_from_funnel_and_relay(monkeypatch, tmp_path) -> None:
    funnel_path = tmp_path / "observation.funnel.json"
    relay_path = tmp_path / "observation.tunnel.state.json"
    funnel_path.write_text(json.dumps({"public_base_url": "https://funnel.example.ts.net/"}), encoding="utf-8")
    relay_path.write_text(json.dumps({"cleanup_pending": False}), encoding="utf-8")
    monkeypatch.setattr(runtime, "DEFAULT_OBSERVATION_PUBLIC_BASE_URL", "https://relay.example.com/")
    monkeypatch.setattr(runtime, "observation_funnel_state_path", lambda: funnel_path)
    monkeypatch.setattr(runtime, "observation_tunnel_state_path", lambda: relay_path)

    assert runtime._read_public_endpoints() == {
        "funnel": "https://funnel.example.ts.net",
        "relay": "https://relay.example.com",
    }


def test_build_manifest_prefers_funnel_when_available(monkeypatch) -> None:
    monkeypatch.setattr(runtime, "DEFAULT_PUBLIC_PREFERRED", "funnel")
    monkeypatch.setattr(
        runtime,
        "_read_public_endpoints",
        lambda: {
            "funnel": "https://funnel.example.ts.net",
            "relay": "https://relay.example.com",
        },
    )

    payload = runtime.build_observation_urls_manifest(token="TOKEN123", host="127.0.0.1", port=37688)

    assert payload["public_default_name"] == "funnel"
    assert payload["human_default_url"] == "https://funnel.example.ts.net/live?token=TOKEN123"
    assert payload["public_variants"]["relay"]["live_url"] == "https://relay.example.com/live?token=TOKEN123"


def test_build_manifest_prefers_relay_when_configured(monkeypatch) -> None:
    monkeypatch.setattr(runtime, "DEFAULT_PUBLIC_PREFERRED", "relay")
    monkeypatch.setattr(
        runtime,
        "_read_public_endpoints",
        lambda: {
            "funnel": "https://funnel.example.ts.net",
            "relay": "https://relay.example.com",
        },
    )

    payload = runtime.build_observation_urls_manifest(token="TOKEN123", host="127.0.0.1", port=37688)

    assert payload["public_default_name"] == "relay"
    assert payload["human_default_url"] == "https://relay.example.com/live?token=TOKEN123"


def test_build_manifest_falls_back_to_local_when_no_public_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(runtime, "_read_public_endpoints", lambda: {})

    payload = runtime.build_observation_urls_manifest(token="TOKEN123", host="127.0.0.1", port=37688)

    assert payload["human_default_url"] == "http://127.0.0.1:37688/live?token=TOKEN123"
    assert payload["public_variants"] == {}
