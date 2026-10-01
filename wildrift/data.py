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
PROFILE_FILE = Path(os.getenv("WILDRIFT_PROFILE", DATA_DIR / "profile.json"))

POSITIONS = ["baron", "jungle", "mid", "dragon", "support"]
TIER_ORDER = {"S+": 0, "S": 1, "A": 2, "B": 3, "C": 4, "D": 5}


class UnknownChampionError(KeyError):
    pass


class UnknownItemError(KeyError):
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


def item_icon(name: str) -> str | None:
    """Icon path for an item, or for a rune (situational swaps can swap runes too)."""
    item = _wrf()["items"].get(name)
    if item:
        return item["icon"]
    rune_slug = slug(name)
    rune = ROOT / "static" / "icons" / "wrf" / "runes" / f"{rune_slug}.png"
    return f"/icons/wrf/runes/{rune_slug}.png" if rune.exists() else None


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


def get_profile() -> dict[str, list[str]]:
    path = PROFILE_FILE if PROFILE_FILE.exists() else DATA_DIR / "profile.default.json"
    profile = _read(path)
    return {p: profile.get(p, []) for p in POSITIONS}


def save_profile(profile: dict[str, list[str]]) -> dict[str, list[str]]:
    clean = {}
    for position in POSITIONS:
        clean[position] = [_find(name)["name"] for name in profile.get(position, [])]
    PROFILE_FILE.write_text(json.dumps(clean, indent=1), encoding="utf-8")
    return clean
