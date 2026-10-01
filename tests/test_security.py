import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from wildrift import security
from wildrift.api import app

client = TestClient(app)


def test_security_headers_present():
    headers = client.get("/").headers
    assert "default-src 'self'" in headers["content-security-policy"]
    assert headers["x-content-type-options"] == "nosniff"


def test_page_has_no_inline_script_or_style():
    html = client.get("/").text
    assert "<script>" not in html and "<style>" not in html and "style=" not in html


TOKENS = "alex:alex-token-123456,sam:sam-token-1234567"
ALEX = {"Authorization": "Bearer alex-token-123456"}
SAM = {"Authorization": "Bearer sam-token-1234567"}


def test_token_required_when_set(monkeypatch):
    monkeypatch.setenv("APP_TOKENS", TOKENS)
    assert client.put("/api/profile", json={"baron": ["Darius"]}).status_code == 401
    wrong = {"Authorization": "Bearer nope"}
    assert client.put("/api/profile", json={"baron": ["Darius"]}, headers=wrong).status_code == 401
    assert client.put("/api/profile", json={"baron": ["Darius"]}, headers=ALEX).status_code == 200


def test_local_bypass_off_once_tokens_exist(monkeypatch):
    monkeypatch.setenv("APP_TOKENS", TOKENS)
    assert client.get("/api/usage").status_code == 401  # even from "this computer"


def test_each_user_has_own_profile_and_usage(monkeypatch):
    monkeypatch.setenv("APP_TOKENS", TOKENS)
    client.put("/api/profile", json={"mid": ["Ahri"]}, headers=ALEX)
    assert client.get("/api/profile", headers=ALEX).json()["mid"] == ["Ahri"]
    assert client.get("/api/profile", headers=SAM).json()["mid"] == []
    assert client.get("/api/profile").json()["mid"] == []  # anonymous visitors see the default pool
    for _ in range(5):
        security.ai_usage.consume("alex")
    assert client.get("/api/usage", headers=ALEX).json()["remaining"] == 0
    assert client.get("/api/usage", headers=SAM).json()["remaining"] == 5


def test_short_or_malformed_tokens_ignored(monkeypatch):
    monkeypatch.setenv("APP_TOKENS", "alex:short,Bad Name:long-enough-token-1")
    assert security._tokens() == {}


def test_without_tokens_only_local_requests_allowed():
    remote = TestClient(app, client=("203.0.113.9", 5000))
    assert remote.put("/api/profile", json={"baron": ["Darius"]}).status_code == 403
    assert remote.get("/api/champions").status_code == 200  # reading stays open


def test_reading_is_open_even_with_tokens(monkeypatch):
    monkeypatch.setenv("APP_TOKENS", TOKENS)
    assert client.get("/api/champions/darius/build").status_code == 200


def test_rate_limit_on_protected_endpoints():
    codes = [client.put("/api/profile", json={"baron": ["Darius"]}).status_code for _ in range(12)]
    assert codes[:10] == [200] * 10 and codes[-1] == 429


def test_oversized_body_rejected():
    response = client.put("/api/profile", content=b"x" * 20000, headers={"Content-Type": "application/json"})
    assert response.status_code == 413


def test_input_limits():
    too_many = {"champion": "Darius", "enemies": ["Garen"] * 6}
    assert client.post("/api/builds/tailor", json=too_many).status_code == 422
    long_name = {"champion": "D" * 200, "enemies": ["Garen"]}
    assert client.post("/api/builds/tailor", json=long_name).status_code == 422
    bad_position = {"champion": "Darius", "enemies": ["Garen"], "position": "top<script>"}
    assert client.post("/api/builds/tailor", json=bad_position).status_code == 422


def test_usage_limit_5_per_person(tmp_path):
    usage = security.UsageLimit(limit=5, global_limit=30, window_hours=48, path=tmp_path / "usage.json")
    for _ in range(5):
        usage.consume("alex")
    assert usage.status("alex")["remaining"] == 0
    assert usage.status("sam")["remaining"] == 5
    with pytest.raises(HTTPException) as exc:
        usage.consume("alex")
    assert exc.value.status_code == 429
    usage.consume("sam")  # other people are unaffected


def test_global_limit_protects_credit(tmp_path):
    usage = security.UsageLimit(limit=5, global_limit=3, window_hours=48, path=tmp_path / "usage.json")
    for user in ("a", "b", "c"):
        usage.consume(user)
    assert usage.status("d")["remaining"] == 0
    with pytest.raises(HTTPException):
        usage.consume("d")


def test_usage_limit_survives_restart_and_expires(tmp_path):
    path = tmp_path / "usage.json"
    old = time.time() - 49 * 3600
    path.write_text(f'{{"alex": [{old}, {time.time()}]}}')
    usage = security.UsageLimit(limit=5, global_limit=30, window_hours=48, path=path)  # a "restarted" server
    assert usage.status("alex")["used"] == 1  # the 49h-old call no longer counts


def test_usage_endpoint_local():
    usage = client.get("/api/usage").json()
    assert usage["user"] == "local" and usage["remaining"] == 5


def test_fetcher_refuses_other_hosts():
    from wildrift import wildriftfire

    for url in ("http://www.wildriftfire.com/x", "https://example.com/x.png", "file:///etc/passwd"):
        with pytest.raises(ValueError):
            wildriftfire._open(url, 1000)


def test_app_tokens_prefix_is_tolerated(monkeypatch):
    monkeypatch.setenv("APP_TOKENS", "APP_TOKENS=chocoloco:choco-token-12345,sam:sam-token-1234567")
    assert sorted(security._tokens().values()) == ["chocoloco", "sam"]


def test_bad_token_entries_are_logged_without_the_token(monkeypatch, caplog):
    security._warned.clear()
    monkeypatch.setenv("APP_TOKENS", "ok:long-enough-token-1,Bad Name:secret-value-123456")
    with caplog.at_level("WARNING"):
        assert list(security._tokens().values()) == ["ok"]
    assert "bad name" in caplog.text and "secret-value" not in caplog.text


def test_refund_gives_a_build_back(tmp_path):
    usage = security.UsageLimit(limit=5, global_limit=30, window_hours=48, path=tmp_path / "usage.json")
    usage.consume("alex")
    usage.refund("alex")
    assert usage.status("alex")["remaining"] == 5
    usage.refund("nobody")  # nothing to refund is fine
    assert not list(tmp_path.glob("*.tmp"))  # atomic writes leave no temp files behind
