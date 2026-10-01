from fastapi.testclient import TestClient

from wildrift.api import app

client = TestClient(app)


def test_champions_have_icons():
    champions = client.get("/api/champions").json()
    assert len(champions) == 8
    assert all(c["icon"] for c in champions)


def test_build_includes_item_icons():
    build = client.get("/api/champions/darius/build").json()
    assert build["core"][0] == {"name": "Black Cleaver", "icon": "/icons/items/black-cleaver.png"}


def test_unknown_champion_is_404():
    assert client.get("/api/champions/Teemo/build").status_code == 404


def test_matchup():
    matchup = client.get("/api/matchup", params={"me": "Garen", "vs": "Aatrox"}).json()
    assert matchup["enemy_heals"] is True


def test_homepage_served():
    response = client.get("/")
    assert response.status_code == 200
    assert "Draft Helper" in response.text


# The tailor error cases below fail during local validation, before any Anthropic API call.
def test_tailor_rejects_unknown_item():
    response = client.post(
        "/api/builds/tailor",
        json={"champion": "Darius", "enemies": ["Garen"], "swaps": [{"remove": "bc", "add": "Infinity Edge"}]},
    )
    assert response.status_code == 404


def test_tailor_rejects_invalid_swap():
    response = client.post(
        "/api/builds/tailor",
        json={"champion": "Darius", "enemies": ["Garen"], "swaps": [{"remove": "triforce", "add": "bc"}]},
    )
    assert response.status_code == 400


def test_tailor_requires_an_enemy():
    response = client.post("/api/builds/tailor", json={"champion": "Darius", "enemies": []})
    assert response.status_code == 422
