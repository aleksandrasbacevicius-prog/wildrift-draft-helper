"""Champion and item data access. Pure functions, no network, no LLM."""

import json
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "champions.json"

# Champions whose kits heal a lot, so anti-heal (grievous wounds) is worth considering.
HEALING_CHAMPIONS = {"Darius", "Renekton", "Fiora", "Swain", "Mordekaiser", "Aatrox"}


class UnknownChampionError(KeyError):
    pass


class UnknownItemError(KeyError):
    pass


@lru_cache(maxsize=1)
def load_data(path: Path = DATA_FILE) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _find(name: str) -> tuple[str, dict]:
    champions = load_data()["champions"]
    for key, value in champions.items():
        if key.lower() == name.strip().lower():
            return key, value
    raise UnknownChampionError(
        f"'{name}' is not in the dataset. Known champions: {', '.join(champions)}"
    )


def icon_slug(name: str) -> str:
    """File-name-safe slug for an icon, e.g. "Sterak's Gage" -> "steraks-gage"."""
    return "-".join(name.lower().replace("'", "").split())


def list_champions() -> list[str]:
    return list(load_data()["champions"])


def get_champion(name: str) -> dict:
    key, champ = _find(name)
    return {"name": key, **{k: v for k, v in champ.items() if k != "build"}}


def get_build(name: str) -> dict:
    key, champ = _find(name)
    return {"name": key, **champ["build"], "patch": load_data()["_meta"]["patch"]}


def get_matchup(my_champion: str, enemy: str) -> dict:
    my_key, mine = _find(my_champion)
    enemy_key, theirs = _find(enemy)
    return {
        "you": my_key,
        "enemy": enemy_key,
        "your_strengths": mine["strengths"],
        "enemy_strengths": theirs["strengths"],
        "enemy_weaknesses": theirs["weaknesses"],
        "how_to_play_against_enemy": theirs["playing_against"],
        "enemy_damage_type": theirs["damage"],
        "enemy_heals": enemy_key in HEALING_CHAMPIONS,
    }


def resolve_item(name: str) -> str:
    """Match an item by exact name (any case) or a common nickname like 'triforce'."""
    wanted = name.strip().lower().replace("'", "")
    items = load_data()["items"]
    for item in items:
        if item.lower().replace("'", "") == wanted:
            return item
    alias = load_data()["item_aliases"].get(wanted)
    if alias:
        return alias
    raise UnknownItemError(f"'{name}' is not a known item. Known items: {', '.join(items)}")


def swap_core_item(champion: str, remove: str, add: str) -> dict:
    """Return the champion's build with one core item replaced by another."""
    return _swap(get_build(champion), remove, add)


def apply_swaps(champion: str, swaps: list[tuple[str, str]]) -> dict:
    """Apply several (remove, add) swaps in order to the champion's build."""
    build = get_build(champion)
    for remove, add in swaps:
        build = _swap(build, remove, add)
    return build


def _swap(build: dict, remove: str, add: str) -> dict:
    build = {**build, "core": list(build["core"]), "situational": list(build["situational"])}
    old, new = resolve_item(remove), resolve_item(add)
    if old not in build["core"]:
        raise ValueError(f"{old} is not a core item for {build['name']}. Core: {', '.join(build['core'])}")
    if new in build["core"]:
        raise ValueError(f"{new} is already a core item for {build['name']}")
    build["core"] = [new if item == old else item for item in build["core"]]
    # The removed core item becomes a situational option; the added one leaves that list.
    build["situational"] = [old] + [item for item in build["situational"] if item != new]
    return build


def get_items(tag: str | None = None) -> dict[str, list[str]]:
    items = load_data()["items"]
    if tag is None:
        return items
    return {name: tags for name, tags in items.items() if tag in tags}
