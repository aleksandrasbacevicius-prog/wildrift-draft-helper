import pytest

from wildrift import data


def test_lists_all_champions():
    assert set(data.list_champions()) == {
        "Darius", "Garen", "Renekton", "Irelia", "Fiora", "Swain", "Mordekaiser", "Aatrox",
    }


def test_lookup_is_case_insensitive():
    assert data.get_champion("  darius ")["name"] == "Darius"


def test_unknown_champion_raises():
    with pytest.raises(data.UnknownChampionError):
        data.get_build("Teemo")


def test_build_items_exist_in_item_list():
    items = data.get_items()
    for name in data.list_champions():
        build = data.get_build(name)
        for item in build["core"] + build["situational"] + [build["boots"]]:
            assert item in items, f"{name} build uses unknown item {item}"


def test_matchup_flags_healing_enemy():
    matchup = data.get_matchup("Garen", "Aatrox")
    assert matchup["enemy_heals"] is True
    assert matchup["enemy_damage_type"] == "AD"


def test_items_filter_by_tag():
    anti_heal = data.get_items("grievous_wounds")
    assert set(anti_heal) == {"Thornmail", "Mortal Reminder"}


def test_resolve_item_accepts_nicknames_and_any_case():
    assert data.resolve_item("triforce") == "Trinity Force"
    assert data.resolve_item("steraks") == "Sterak's Gage"
    assert data.resolve_item("black cleaver") == "Black Cleaver"


def test_swap_core_item_replaces_in_place():
    build = data.swap_core_item("Darius", "Black Cleaver", "triforce")
    assert build["core"] == ["Trinity Force", "Sterak's Gage", "Death's Dance"]
    assert build["situational"][0] == "Black Cleaver"


def test_swap_does_not_change_stored_build():
    data.swap_core_item("Darius", "Black Cleaver", "triforce")
    assert data.get_build("Darius")["core"][0] == "Black Cleaver"


def test_swap_moves_situational_item_into_core():
    build = data.swap_core_item("Darius", "Death's Dance", "Guardian Angel")
    assert "Guardian Angel" in build["core"]
    assert "Guardian Angel" not in build["situational"]


def test_apply_swaps_chains():
    build = data.apply_swaps("Darius", [("bc", "triforce"), ("dd", "ga")])
    assert build["core"] == ["Trinity Force", "Sterak's Gage", "Guardian Angel"]


@pytest.mark.parametrize(
    "remove, add, error",
    [
        ("Trinity Force", "Black Cleaver", ValueError),  # not in core
        ("Black Cleaver", "Sterak's Gage", ValueError),  # already core
        ("Black Cleaver", "Infinity Edge", data.UnknownItemError),
    ],
)
def test_swap_rejects_bad_input(remove, add, error):
    with pytest.raises(error):
        data.swap_core_item("Darius", remove, add)
