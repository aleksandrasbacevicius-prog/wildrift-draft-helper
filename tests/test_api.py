import pytest
from fastapi.testclient import TestClient

import wildrift.agent as agent_module
import wildrift.api as api_module
from wildrift import data, security, wildriftfire
from wildrift.api import app

client = TestClient(app)  # no `with`, so the daily patch check doesn't start


def test_meta_has_patch():
    meta = client.get("/api/meta").json()
    assert meta["patch"] and meta["positions"] == data.POSITIONS


def test_champions_by_position():
    champions = client.get("/api/champions", params={"position": "baron"}).json()
    assert champions and all("baron" in c["positions"] for c in champions)


def test_bad_position_is_400():
    assert client.get("/api/champions", params={"position": "top"}).status_code == 400


def test_build_includes_item_icons():
    build = client.get("/api/champions/darius/build").json()
    assert set(build["core"][0]) == {"name", "icon"}
    assert "replace" in build["situational"][0]


def test_unknown_champion_is_404():
    assert client.get("/api/champions/Nobody/build").status_code == 404


def test_profile_round_trip():
    assert "Darius" in client.get("/api/profile").json()["baron"]
    saved = client.put("/api/profile", json={"baron": ["garen"]}).json()
    assert saved["baron"] == ["Garen"]


def test_homepage_served():
    response = client.get("/")
    assert response.status_code == 200 and "Draft Helper" in response.text


# The tailor error cases below fail during local validation, before any Anthropic API call.
def test_tailor_rejects_unknown_item():
    response = client.post(
        "/api/builds/tailor",
        json={"champion": "Darius", "enemies": ["Garen"], "swaps": [{"remove": "Stridebreaker", "add": "Not An Item"}]},
    )
    assert response.status_code == 404


def test_tailor_rejects_unknown_enemy():
    response = client.post("/api/builds/tailor", json={"champion": "Darius", "enemies": ["Nobody"]})
    assert response.status_code == 404


def test_tailor_rejects_invalid_swap():
    response = client.post(
        "/api/builds/tailor",
        json={"champion": "Darius", "enemies": ["Garen"], "swaps": [{"remove": "triforce", "add": "Stridebreaker"}]},
    )
    assert response.status_code == 400


def test_tailor_requires_an_enemy():
    response = client.post("/api/builds/tailor", json={"champion": "Darius", "enemies": []})
    assert response.status_code == 422


# --- Patch checks, refresh and the "still downloading" state ---


def test_check_for_update_refreshes_on_new_patch(monkeypatch):
    calls = []
    monkeypatch.setattr(wildriftfire, "needs_refresh", lambda **_: (True, "new patch 7.4 (have 7.3a)"))
    monkeypatch.setattr(wildriftfire, "refresh", lambda log: calls.append("refresh"))
    monkeypatch.setattr(data, "reload", lambda: calls.append("reload"))
    api_module.check_for_update()
    assert calls == ["refresh", "reload"]
    assert api_module.update_status["state"] == "idle" and "Updated" in api_module.update_status["message"]


def test_check_for_update_when_current(monkeypatch):
    monkeypatch.setattr(wildriftfire, "needs_refresh", lambda **_: (False, "up to date (patch 7.3a)"))
    monkeypatch.setattr(wildriftfire, "refresh", lambda log: pytest.fail("should not refresh"))
    api_module.check_for_update()
    assert api_module.update_status["message"] == "Up to date (patch 7.3a)"


def test_check_for_update_reports_errors(monkeypatch):
    def boom(**_):
        raise OSError("network down")

    monkeypatch.setattr(wildriftfire, "needs_refresh", boom)
    api_module.check_for_update()
    assert api_module.update_status["state"] == "error" and "network down" in api_module.update_status["message"]


def test_first_refresh_allowed_right_after_boot(monkeypatch):
    # On Linux, time.monotonic() is seconds since boot, so it can be small on a new server or CI machine.
    monkeypatch.setattr(api_module, "check_for_update", lambda: None)
    monkeypatch.setattr(api_module.time, "monotonic", lambda: 60.0)
    monkeypatch.setattr(api_module, "_last_manual_refresh", float("-inf"))
    assert client.post("/api/refresh").status_code == 202


def test_refresh_endpoint_has_cooldown(monkeypatch):
    monkeypatch.setattr(api_module, "check_for_update", lambda: None)
    monkeypatch.setattr(api_module, "_last_manual_refresh", float("-inf"))
    assert client.post("/api/refresh").status_code == 202
    assert client.post("/api/refresh").status_code == 429


def test_no_data_yet_returns_503(monkeypatch):
    def no_data():
        raise data.NoDataError("downloading")

    monkeypatch.setattr(data, "_wrf", no_data)
    assert client.get("/api/champions").status_code == 503
    assert client.get("/api/champions/Darius/build").status_code == 503
    assert client.get("/api/runes").status_code == 503
    assert client.get("/api/meta").json()["update"]  # meta still answers


# --- A successful AI build, with the agent faked ---


def test_tailor_success_counts_usage(monkeypatch):
    def fake_tailor(champion, enemies, swaps, position, runes=None, on_api_call=None):
        on_api_call()
        return f"Advice for {champion} vs {enemies[0]}"

    monkeypatch.setattr(agent_module, "tailor_build", fake_tailor)
    response = client.post("/api/builds/tailor", json={"champion": "Darius", "enemies": ["Garen"], "position": "baron"})
    assert response.status_code == 200
    body = response.json()
    assert body["result"] == "Advice for Darius vs Garen"
    assert body["ai_usage"]["used"] == 1 and body["ai_usage"]["remaining"] == 4


def test_tailor_limit_reached_is_429(monkeypatch):
    monkeypatch.setattr(agent_module, "tailor_build", lambda *a, on_api_call=None, **k: (on_api_call(), "advice")[1])
    for _ in range(5):
        security.ai_usage.consume("local")
    response = client.post("/api/builds/tailor", json={"champion": "Darius", "enemies": ["Garen"]})
    assert response.status_code == 429 and "5 custom builds" in response.json()["detail"]


def test_tailor_missing_api_key_is_503(monkeypatch):
    def no_key(*a, **k):
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")

    monkeypatch.setattr(agent_module, "tailor_build", no_key)
    response = client.post("/api/builds/tailor", json={"champion": "Darius", "enemies": ["Garen"]})
    assert response.status_code == 503


def test_ai_service_failure_is_502_and_not_counted(monkeypatch):
    def flaky(*a, on_api_call=None, **k):
        on_api_call()
        raise ConnectionError("Anthropic overloaded")

    monkeypatch.setattr(agent_module, "tailor_build", flaky)
    response = client.post("/api/builds/tailor", json={"champion": "Darius", "enemies": ["Garen"]})
    assert response.status_code == 502 and "wasn't counted" in response.json()["detail"]
    assert security.ai_usage.status("local")["remaining"] == 5


def test_champion_without_build_is_404():
    assert client.get("/api/champions/Yuumi/build").status_code == 404


def test_first_check_after_boot_is_delayed_and_patch_only(monkeypatch):
    calls = []

    def stop(seconds):
        calls.append(("sleep", seconds))
        if len(calls) > 2:
            raise SystemExit

    monkeypatch.setattr(api_module.time, "sleep", stop)
    monkeypatch.setattr(api_module, "check_for_update", lambda **kw: calls.append(("check", kw)))
    with pytest.raises(SystemExit):
        api_module._daily_checks()
    assert calls[:3] == [
        ("sleep", api_module.STARTUP_CHECK_DELAY_SECONDS),
        ("check", {"check_age": False}),
        ("sleep", api_module.CHECK_EVERY_SECONDS),
    ]


def test_large_responses_are_compressed():
    r = client.get("/api/items", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"
