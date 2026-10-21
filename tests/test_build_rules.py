"""Matchup-aware builds: the general build, the three matchup rules, per-slot options and matchup cards.

The fixtures hold made-up WildRiftCore-style data for Darius and Garen in baron lane."""

import pytest
from fastapi.testclient import TestClient

from wildrift import data
from wildrift import mcp_server as mcp
from wildrift.api import app

client = TestClient(app)


def test_general_build_is_the_most_played():
    build = data.get_build("Darius", "baron")
    most_played = build["choices"]["core"][0]
    assert most_played["label"] == "Most played" and build["core"] == most_played["items"]
    assert build["runes"] == build["choices"]["runes"][0]["runes"]
    assert build["final"][: 1 + len(build["core"])] == build["boots"] + build["core"]
    assert len(build["final"]) == len(build["boots"]) + len(build["core"]) + 2
    assert build["matchup"] is None


def test_choices_include_every_source_with_dashes_removed():
    labels = [c["label"] for c in data.get_build("Darius", "baron")["choices"]["core"]]
    assert "Standard: bruiser" in labels and "WildRiftFire guide" in labels
    assert not any("—" in label for label in labels)


def test_specific_counter_item_wins():
    build = data.get_build("Darius", "baron", "Malphite")
    m = build["matchup"]
    assert m["rule"] == "specific" and m["enemy"] == "Malphite"
    change = m["adjustments"][0]
    assert change["with"] == "Wit's End" and "Malphite" in change["why"]
    assert "Wit's End" in build["final"] and change["replace"] not in build["final"]


def test_situational_item_naming_the_opponent_is_specific():
    m = data.get_build("Darius", "baron", "Aatrox")["matchup"]
    assert m["rule"] == "specific" and m["adjustments"][0]["with"] == "Chempunk Chainsword"


def test_mage_gets_anti_magic_boots_and_item():
    build = data.get_build("Darius", "baron", "Syndra")
    m = build["matchup"]
    assert m["rule"] == "magic"
    assert build["boots"] == ["Mercury's Treads"]
    assert {a["with"] for a in m["adjustments"]} == {"Mercury's Treads", "Wit's End"}
    assert all("magic damage" in a["why"] for a in m["adjustments"])


def test_physical_assassin_gets_anti_burst():
    m = data.get_build("Darius", "baron", "Lee Sin")["matchup"]
    assert m["rule"] == "physical" and m["adjustments"][0]["with"] == "Guardian Angel"


def test_plain_matchup_keeps_the_general_build():
    general = data.get_build("Darius", "baron")
    build = data.get_build("Darius", "baron", "Garen")
    assert build["matchup"]["rule"] == "general" and build["matchup"]["adjustments"] == []
    assert build["final"] == general["final"]


def test_options_cover_every_slot_matchup_first():
    build = data.get_build("Darius", "baron", "Syndra")
    options = build["options"]
    assert len(options["core"]) == len(build["core"]) and len(options["runes"]) == len(build["runes"])
    assert len(options["extras"]) == 2
    for slot, item in enumerate(build["core"]):
        names = [o["name"] for o in options["core"][slot]]
        assert item not in names and len(names) == len(set(names)) <= data.MAX_OPTIONS
    # Already in the build, so not offered again; the remaining anti-magic option comes first.
    assert all(o["name"] not in build["final"] for slot in options["extras"] for o in slot)
    assert all(o["why"] for slot in options["core"] for o in slot)


def test_rune_options_keep_keystones_in_the_first_slot():
    build = data.get_build("Darius", "baron")
    runes = data.get_runes()
    assert all(runes[o["name"]]["kind"] == "keystone" for o in build["options"]["runes"][0] if o["name"] in runes)
    assert all(
        runes[o["name"]]["kind"] == "minor" for s in build["options"]["runes"][1:] for o in s if o["name"] in runes
    )


def test_matchup_card_decides_the_verdict_and_tips():
    m = data.get_matchup("Darius", "Garen", "baron")
    assert m["enemy_counters_you"] and not m["you_counter_enemy"] and not m["even"]
    assert m["card"]["edge"] == 1 and m["how_to_play_against_enemy"][0] == "Sample key tip vs Garen."
    assert m["has_tips"]
    even = data.get_matchup("Darius", "Mordekaiser", "baron")
    assert even["even"] and not even["enemy_counters_you"] and not even["you_counter_enemy"]
    assert data.get_matchup("Garen", "Darius", "baron")["you_counter_enemy"]


def test_enemy_damage_type_comes_from_class_data():
    assert data.get_matchup("Darius", "Syndra", "baron")["enemy_damage_type"] == "magic"
    assert data.get_matchup("Darius", "Dr. Mundo", "baron")["enemy_damage_type"] == "mixed"


def test_counters_include_wildriftcore():
    garen = next(c for c in data.strong_against("Darius", "baron") if c["name"] == "Garen")
    assert garen["sources"] == ["WildRiftCore"]


def test_api_build_vs_opponent():
    r = client.get("/api/champions/Darius/build?position=baron&vs=Syndra")
    assert r.status_code == 200
    body = r.json()
    change = body["matchup"]["adjustments"][0]
    assert {"name", "icon"} <= set(change["with"]) and change["why"]
    assert {"name", "icon", "why", "matchup"} <= set(body["options"]["core"][0][0])
    assert body["choices"]["core"][0]["items"][0]["icon"] is not None
    assert client.get("/api/champions/Darius/build?position=baron&vs=Nobody").status_code == 404


def test_preferences_with_boots_and_later_items():
    build = data.get_build("Darius", "baron")
    data.save_preferences(
        "pat",
        "Darius",
        build["core"],
        build["runes"],
        "baron",
        boots="Mercury's Treads",
        extras=["Guardian Angel", "Thornmail"],
    )
    saved = data.get_preferences("pat", "Darius", "baron")
    assert saved["boots"] == "Mercury's Treads" and saved["extras"] == ["Guardian Angel", "Thornmail"]
    with pytest.raises(ValueError):
        data.save_preferences("pat", "Darius", build["core"], build["runes"], "baron", extras=[build["core"][0]])


def test_mcp_build_is_compact():
    build = mcp.get_build("Darius", "baron", "Syndra")
    assert build["matchup"]["rule"] == "magic"
    assert "choices" not in build and "server" not in build
    assert isinstance(build["options"]["core"][0][0], str) and "(" in build["options"]["core"][0][0]


def test_incomplete_rune_page_is_used_when_it_is_the_only_one():
    wrc = {
        "variants": [{"name": "Standard", "items": ["A", "B", "C"], "when": ""}],
        "runes": ["Electrocute", "Sudden Impact"],
    }
    cores, pages = data._choices(wrc, {}, {})
    assert cores[0]["items"] == ["A", "B", "C"] and pages[0]["runes"] == ["Electrocute", "Sudden Impact"]


def test_rating_from_the_opponents_page_is_flipped_without_tips():
    # Only Darius's page rates Darius vs Mordekaiser; from Mordekaiser's side the edge flips and tips are left out.
    garen_side = data.matchup_card("Garen", "Darius", "baron")
    assert garen_side["edge"] == -1 and garen_side["key"]  # Garen's own page rates Darius
    card = data.matchup_card("Mordekaiser", "Darius", "baron")
    assert card["edge"] == 0 and card["key"] == "" and card["how"] == ""
    assert data.matchup_card("Ahri", "Syndra", "mid") is None
