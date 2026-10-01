"""Counterpicks, synergies and lane-specific builds."""

from fastapi.testclient import TestClient

from wildrift import data
from wildrift.api import app

client = TestClient(app)


def test_build_follows_the_lane():
    assert data.get_build("Darius", "jungle")["position"] == "jungle"
    assert data.get_build("Darius", "baron")["position"] == "baron"
    assert data.get_build("Darius", "jungle")["core"] != data.get_build("Darius", "baron")["core"]


def test_lane_without_its_own_build_falls_back_to_recommended():
    build = data.get_build("Darius", "support")
    assert build["position"] == "baron"  # Darius has no support build


def test_strong_against_lists_known_counters_best_tier_first():
    counters = data.strong_against("Darius", "baron")
    names = [c["name"] for c in counters]
    assert set(names) <= {"Dr. Mundo", "Malphite", "Ornn"} and names
    tiers = [data.TIER_ORDER.get(c["positions"].get("baron", ""), 9) for c in counters]
    assert tiers == sorted(tiers)


def test_strong_against_unknown_or_buildless_champion_is_empty():
    assert data.strong_against("Yuumi", "support") == []


def test_matchup_counter_flags():
    m = data.get_matchup("Malphite", "Darius", "baron")
    assert m["you_counter_enemy"] is True and "Malphite" in m["enemy_countered_by"]
    m = data.get_matchup("Darius", "Malphite", "baron")
    assert m["enemy_counters_you"] is True
    assert {"name", "position"} <= set(m["your_synergies"][0])


def test_saved_builds_are_per_lane():
    baron, jungle = data.get_build("Darius", "baron"), data.get_build("Darius", "jungle")
    data.save_preferences("alex", "Darius", ["Trinity Force", *baron["core"][1:]], baron["runes"], "baron")
    assert data.get_preferences("alex", "Darius", "baron")["core"][0] == "Trinity Force"
    assert data.get_preferences("alex", "Darius", "jungle") is None
    data.save_preferences("alex", "Darius", jungle["core"], jungle["runes"], "jungle")
    data.reset_preferences("alex", "Darius", "baron")
    assert data.get_preferences("alex", "Darius", "baron") is None
    assert data.get_preferences("alex", "Darius", "jungle") is not None


def test_counters_endpoint():
    assert client.get("/api/counters/Darius", params={"position": "baron"}).json()
    assert client.get("/api/counters/Nobody").status_code == 404
    assert client.get("/api/counters/Darius", params={"position": "top"}).status_code == 422


def test_build_endpoint_by_lane():
    build = client.get("/api/champions/Darius/build", params={"position": "jungle"}).json()
    assert build["position"] == "jungle"
    assert {"name", "position"} <= set(build["countered_by"][0])


def test_item_details_reach_the_page():
    stridebreaker = next(i for i in client.get("/api/items").json() if i["name"] == "Stridebreaker")
    assert stridebreaker["details"]["gold"] and stridebreaker["details"]["stats"]
