"""Server builds and lane stats (RiftPatchNotes data in the fixtures) through data, API and MCP."""

from fastapi.testclient import TestClient

from wildrift import data
from wildrift import mcp_server as mcp
from wildrift.api import app

client = TestClient(app)


def test_common_opponents_sorted_by_pick_rate():
    opponents = data.common_opponents("baron")
    assert opponents and all("baron" in c["positions"] or c["pick"] >= 0 for c in opponents)
    picks = [c["pick"] for c in opponents]
    assert picks == sorted(picks, reverse=True)
    assert {"win", "pick", "ban"} <= set(opponents[0])


def test_common_opponents_limit():
    assert len(data.common_opponents("baron", limit=2)) <= 2


def test_list_champions_has_lane_stats():
    darius = next(c for c in data.list_champions("baron") if c["name"] == "Darius")
    assert darius["stats"]["baron"]["pick"] > 0


def test_build_has_server_options_for_the_lane():
    build = data.get_build("Darius", "baron")
    assert build["server"]["cores"][0]["items"]
    assert build["server"]["rune_pages"][0]["runes"]
    assert build["server_stats"]["win"] > 0


def test_champion_without_server_data_has_empty_server(monkeypatch):
    champ = data._find("Darius")
    monkeypatch.delitem(champ, "server")
    assert data.get_build("Darius", "baron")["server"] == {}
    assert data._server(champ) == {"stats": {}, "builds": {}}


def test_matchup_has_lane_stats_for_both():
    m = data.get_matchup("Darius", "Garen", "baron")
    assert m["your_lane_stats"]["pick"] > 0 and m["enemy_lane_stats"]["pick"] > 0


def test_api_build_server_options_have_icons():
    server = client.get("/api/champions/Darius/build?position=baron").json()["server"]
    assert server["cores"][0]["items"][0]["name"] and "icon" in server["cores"][0]["items"][0]
    assert "icon" in server["rune_pages"][0]["runes"][0]
    assert server["boots"][0]["item"]["name"]
    assert server["spells"][0]["spells"][0]["name"]


def test_api_common_opponents():
    r = client.get("/api/common-opponents?position=baron")
    assert r.status_code == 200 and r.json()[0]["pick"] > 0
    assert client.get("/api/common-opponents").status_code == 422
    assert client.get("/api/common-opponents?position=top").status_code == 422


def test_mcp_common_opponents():
    opponents = mcp.get_common_opponents("baron")
    assert opponents and set(opponents[0]) == {"name", "win", "pick", "ban"}
