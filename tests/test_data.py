import pytest

from wildrift import data


def test_position_list_sorted_by_tier():
    tiers = [c["positions"]["baron"] for c in data.list_champions("baron")]
    assert tiers == sorted(tiers, key=data.TIER_ORDER.get)


def test_lookup_is_case_insensitive():
    assert data.get_champion("  darius ")["name"] == "Darius"


def test_unknown_champion_raises():
    with pytest.raises(data.UnknownChampionError):
        data.get_build("Not A Champion")


def test_build_has_core_and_situational():
    build = data.get_build("Darius")
    assert len(build["core"]) == 3
    assert build["patch"]
    assert all({"when", "replace", "with"} <= set(s) for s in build["situational"])


def test_champion_with_tips_includes_them():
    assert data.get_champion("Garen")["playing_against"]


def test_matchup_without_tips_still_works():
    matchup = data.get_matchup("Darius", "Ahri")
    assert matchup["has_tips"] is False
    assert matchup["enemy_tiers"]


def test_resolve_item_accepts_nicknames_and_any_case():
    assert data.resolve_item("triforce") == "Trinity Force"
    assert data.resolve_item("steraks") == "Sterak's Gage"
    assert data.resolve_item("STRIDEBREAKER") == "Stridebreaker"


def test_swap_replaces_in_core_and_final():
    build = data.get_build("Darius")
    old = build["core"][0]
    swapped = data.swap_core_item("Darius", old, "triforce")
    assert swapped["core"][0] == "Trinity Force"
    assert old not in swapped["final"]
    assert swapped["swaps"] == [{"remove": old, "add": "Trinity Force"}]


def test_swap_does_not_change_stored_build():
    before = data.get_build("Darius")["core"]
    data.swap_core_item("Darius", before[0], "triforce")
    assert data.get_build("Darius")["core"] == before


@pytest.mark.parametrize(
    "remove, add, error",
    [
        ("Trinity Force", "Stridebreaker", ValueError),  # not in core
        ("Stridebreaker", "Sterak's Gage", ValueError),  # already core
        ("Stridebreaker", "Not An Item", data.UnknownItemError),
    ],
)
def test_swap_rejects_bad_input(remove, add, error):
    with pytest.raises(error):
        data.swap_core_item("Darius", remove, add)


def test_items_filter_by_category():
    boots = data.get_items("boots")
    assert boots and all("Boots" in i["categories"] for i in boots.values())


def test_default_profile_has_baron_pool():
    assert "Darius" in data.get_profile()["baron"]


def test_save_profile_normalises_names():
    saved = data.save_profile("alex", {"baron": ["darius", "Darius"], "mid": ["ahri"]})
    assert saved["baron"] == ["Darius"] and saved["mid"] == ["Ahri"]
    assert data.get_profile("alex")["mid"] == ["Ahri"]


def test_profiles_are_per_user():
    data.save_profile("alex", {"mid": ["Ahri"]})
    assert data.get_profile("sam")["mid"] == []  # new user gets the default pool
    assert "Darius" in data.get_profile("sam")["baron"]


def test_save_profile_rejects_unknown_champion():
    with pytest.raises(data.UnknownChampionError):
        data.save_profile("alex", {"baron": ["Nobody"]})
