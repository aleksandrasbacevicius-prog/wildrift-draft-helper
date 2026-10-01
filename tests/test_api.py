import pytest
from fastapi.testclient import TestClient

from wildrift import data
from wildrift.api import app

client = TestClient(app)  # no `with`, so the daily patch check doesn't start


@pytest.fixture(autouse=True)
def no_saved_profile():
    data.PROFILE_FILE.unlink(missing_ok=True)
    yield
    data.PROFILE_FILE.unlink(missing_ok=True)


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
