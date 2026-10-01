"""Champion, build, item and profile data. No LLM calls.

Builds, tiers and items come from WildRiftFire.com (see wildriftfire.py) and are cached in
data/wildriftfire/. Matchup tips in data/tips.json are hand-written.
"""

import json
import os
from functools import lru_cache
from pathlib import Path

from wildrift.wildriftfire import slug

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
WRF_DIR = Path(os.getenv("WILDRIFT_DATA_DIR", DATA_DIR / "wildriftfire"))
PROFILE_DIR = Path(os.getenv("WILDRIFT_PROFILE_DIR", DATA_DIR / "profiles"))
PREFS_DIR = Path(os.getenv("WILDRIFT_PREFS_DIR", DATA_DIR / "builds"))

POSITIONS = ["baron", "jungle", "mid", "dragon", "support"]
TIER_ORDER = {"S+": 0, "S": 1, "A": 2, "B": 3, "C": 4, "D": 5}


class UnknownChampionError(KeyError):
    pass


class UnknownItemError(KeyError):
    pass


class UnknownRuneError(KeyError):
    pass


class NoDataError(RuntimeError):
    pass


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _wrf() -> dict:
    if not (WRF_DIR / "champions.json").exists():
        raise NoDataError("No champion data yet. Run: python -m wildrift.wildriftfire")
    return {
        "champions": _read(WRF_DIR / "champions.json"),
        "items": _read(WRF_DIR / "items.json"),
        "runes": _read(WRF_DIR / "runes.json") if (WRF_DIR / "runes.json").exists() else {},
        "meta": _read(WRF_DIR / "meta.json"),
    }


@lru_cache(maxsize=1)
def _tips() -> dict:
    return {k: v for k, v in _read(DATA_DIR / "tips.json").items() if not k.startswith("_")}


@lru_cache(maxsize=1)
def _aliases() -> dict:
    return _read(DATA_DIR / "item_aliases.json")


def reload() -> None:
    """Drop cached data, e.g. after a refresh from WildRiftFire."""
    _wrf.cache_clear()


def meta() -> dict:
    return _wrf()["meta"]


def _find(name: str) -> dict:
    wanted = name.strip().lower()
    for champ in _wrf()["champions"].values():
        if champ["name"].lower() == wanted:
            return champ
    raise UnknownChampionError(f"'{name}' is not in the champion list")


def _best_tier(champ: dict) -> int:
    return min((TIER_ORDER.get(t, 9) for t in champ["positions"].values()), default=9)


def list_champions(position: str | None = None) -> list[dict]:
    """Champions with their tier per position. Sorted by tier for a position, else by name."""
    champs = [
        {"name": c["name"], "icon": c["icon"], "positions": c["positions"]}
        for c in _wrf()["champions"].values()
        if position is None or position in c["positions"]
    ]
    if position:
        return sorted(champs, key=lambda c: (TIER_ORDER.get(c["positions"][position], 9), c["name"]))
    return sorted(champs, key=lambda c: c["name"])


def get_champion(name: str) -> dict:
    champ = _find(name)
    return {"name": champ["name"], "icon": champ["icon"], "positions": champ["positions"], **_tips().get(champ["name"], {})}


def get_build(name: str) -> dict:
    champ = _find(name)
    if not champ.get("build"):
        raise UnknownChampionError(f"No build available for {champ['name']}")
    return {"name": champ["name"], **champ["build"], "patch": meta()["patch"]}


def get_matchup(my_champion: str, enemy: str) -> dict:
    mine, theirs = get_champion(my_champion), get_champion(enemy)
    return {
        "you": mine["name"],
        "enemy": theirs["name"],
        "enemy_tiers": theirs["positions"],
        "your_strengths": mine.get("strengths", []),
        "enemy_strengths": theirs.get("strengths", []),
        "enemy_weaknesses": theirs.get("weaknesses", []),
        "how_to_play_against_enemy": theirs.get("playing_against", []),
        "enemy_damage_type": theirs.get("damage"),
        "enemy_heals": theirs.get("heals"),
        "has_tips": "playing_against" in theirs,
    }


def get_items(category: str | None = None) -> dict[str, dict]:
    items = _wrf()["items"]
    if category is None:
        return items
    wanted = category.lower()
    return {n: i for n, i in items.items() if wanted in (c.lower() for c in i["categories"])}


def _local_icon(kind: str, name: str) -> str | None:
    path = ROOT / "static" / "icons" / "wrf" / kind / f"{slug(name)}.png"
    return f"/icons/wrf/{kind}/{slug(name)}.png" if path.exists() else None


def item_icon(name: str) -> str | None:
    """Icon path for an item, or for a rune (situational swaps can swap runes too)."""
    item = _wrf()["items"].get(name)
    if item:
        return item["icon"]
    return _local_icon("runes", name)


def rune_icon(name: str) -> str | None:
    return _local_icon("runes", name)


def spell_icon(name: str) -> str | None:
    return _local_icon("spells", name)


def resolve_item(name: str) -> str:
    """Match an item by exact name (any case) or a common nickname like 'triforce'."""
    wanted = name.strip().lower().replace("'", "")
    items = _wrf()["items"]
    for item in items:
        if item.lower().replace("'", "") == wanted:
            return item
    alias = _aliases().get(wanted)
    if alias and alias in items:
        return alias
    raise UnknownItemError(f"'{name}' is not a known item")


def get_runes() -> dict[str, dict]:
    """Every rune: kind (keystone/minor), tree and tier."""
    return _wrf()["runes"]


def resolve_rune(name: str) -> str:
    wanted = name.strip().lower()
    for rune in _wrf()["runes"]:
        if rune.lower() == wanted:
            return rune
    raise UnknownRuneError(f"'{name}' is not a known rune")


def validate_runes(champion: str, runes: list[str]) -> list[str]:
    """Check a rune page: same number of runes as the build, keystone first, minors after, no repeats.
    Row rules inside each tree aren't known, so those aren't checked."""
    expected = len(get_build(champion)["runes"])
    names = [resolve_rune(r) for r in runes]
    if len(names) != expected:
        raise ValueError(f"Expected {expected} runes, got {len(names)}")
    if len(set(names)) != len(names):
        raise ValueError("A rune can only be picked once")
    catalog = _wrf()["runes"]
    if catalog[names[0]]["kind"] != "keystone":
        raise ValueError(f"{names[0]} is not a keystone")
    for name in names[1:]:
        if catalog[name]["kind"] != "minor":
            raise ValueError(f"{name} is a keystone; only the first slot can hold one")
    return names


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
    old, new = resolve_item(remove), resolve_item(add)
    if old not in build["core"]:
        raise ValueError(f"{old} is not a core item for {build['name']}. Core: {', '.join(build['core'])}")
    if new in build["core"]:
        raise ValueError(f"{new} is already a core item for {build['name']}")
    return {
        **build,
        "core": [new if item == old else item for item in build["core"]],
        "final": [new if item == old else item for item in build["final"]],
        "swaps": build.get("swaps", []) + [{"remove": old, "add": new}],
    }


def _profile_file(user: str) -> Path:
    # User names are validated in security.py (lowercase letters, digits, - and _), so this stays in PROFILE_DIR.
    return PROFILE_DIR / f"{user}.json"


def get_profile(user: str | None = None) -> dict[str, list[str]]:
    """A user's champion pool per position, or the default pool for anonymous visitors and new users."""
    path = _profile_file(user) if user else None
    profile = _read(path if path and path.exists() else DATA_DIR / "profile.default.json")
    return {p: profile.get(p, []) for p in POSITIONS}


def save_profile(user: str, profile: dict[str, list[str]]) -> dict[str, list[str]]:
    clean = {}
    for position in POSITIONS:
        clean[position] = list(dict.fromkeys(_find(name)["name"] for name in profile.get(position, [])))
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    _profile_file(user).write_text(json.dumps(clean, indent=1), encoding="utf-8")
    return clean


def _prefs_file(user: str) -> Path:
    return PREFS_DIR / f"{user}.json"  # user names are validated in security.py


def _all_prefs(user: str) -> dict:
    path = _prefs_file(user)
    return _read(path) if path.exists() else {}


def get_preferences(user: str | None, champion: str) -> dict | None:
    """A user's saved core items and runes for a champion, or None."""
    if not user:
        return None
    return _all_prefs(user).get(_find(champion)["name"])


def save_preferences(user: str, champion: str, core: list[str], runes: list[str]) -> dict:
    """Save a user's own core items and runes for a champion (validated like swaps)."""
    build = get_build(champion)
    core_items = [resolve_item(i) for i in core]
    if len(core_items) != len(build["core"]) or len(set(core_items)) != len(core_items):
        raise ValueError(f"Core needs {len(build['core'])} different items")
    boots = [i for i in core_items if "Boots" in _wrf()["items"][i]["categories"]]
    if boots:
        raise ValueError(f"Boots can't be core items: {', '.join(boots)}")
    prefs = _all_prefs(user)
    prefs[build["name"]] = {"core": core_items, "runes": validate_runes(build["name"], runes)}
    PREFS_DIR.mkdir(parents=True, exist_ok=True)
    _prefs_file(user).write_text(json.dumps(prefs, indent=1), encoding="utf-8")
    return prefs[build["name"]]


def reset_preferences(user: str, champion: str) -> None:
    prefs = _all_prefs(user)
    if prefs.pop(_find(champion)["name"], None) is not None:
        _prefs_file(user).write_text(json.dumps(prefs, indent=1), encoding="utf-8")
