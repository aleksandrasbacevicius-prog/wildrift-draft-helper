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


def test_strong_against_lists_known_counters_strongest_agreement_first():
    counters = data.strong_against("Darius", "baron")
    names = {c["name"] for c in counters}
    assert {"Dr. Mundo", "Malphite", "Ornn"} <= names  # fixture champions only; others are skipped
    scores = [c["score"] for c in counters]
    assert scores == sorted(scores, reverse=True)
    assert all(c["sources"] for c in counters)


def test_strong_against_unknown_or_buildless_champion_is_empty():
    assert data.strong_against("Yuumi", "support") == []


def test_matchup_clear_counter():
    m = data.get_matchup("Mordekaiser", "Malphite", "baron")  # listed one way only, strongly
    assert m["you_counter_enemy"] is True and m["enemy_counters_you"] is False
    assert data.get_matchup("Malphite", "Mordekaiser", "baron")["enemy_counters_you"] is True


def test_matchup_mutual_counters_with_close_scores_are_even():
    m = data.get_matchup("Darius", "Malphite", "baron")  # each listed against the other, scores close
    assert m["counters_each_other"] is True
    assert m["you_counter_enemy"] is False and m["enemy_counters_you"] is False


def test_matchup_lists_synergies():
    m = data.get_matchup("Darius", "Malphite", "baron")
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
