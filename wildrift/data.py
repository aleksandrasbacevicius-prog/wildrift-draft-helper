"""Champion, build, item and profile data. No LLM calls.

Builds, tiers and items come from WildRiftFire.com (see wildriftfire.py) and are cached in
data/wildriftfire/. Matchup tips in data/tips.json are hand-written.
"""

import json
import os
import re
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
# Counter scores closer than this count as an even matchup (when each side is listed against the other).
EVEN_MARGIN = 0.15


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
        {"name": c["name"], "icon": c["icon"], "positions": c["positions"], "stats": _server(c)["stats"]}
        for c in _wrf()["champions"].values()
        if position is None or position in c["positions"]
    ]
    if position:
        return sorted(champs, key=lambda c: (TIER_ORDER.get(c["positions"][position], 9), c["name"]))
    return sorted(champs, key=lambda c: c["name"])


def _server(champ: dict) -> dict:
    """RiftPatchNotes' Diamond+ CN server data for a champion: lane stats and server builds (may be empty)."""
    server = champ.get("server") or {}
    return {"stats": server.get("stats") or {}, "builds": server.get("builds") or {}}


def common_opponents(position: str, limit: int = 8) -> list[dict]:
    """The champions you're most likely to face in a lane this patch: highest Diamond+ pick rate first."""
    picked = [
        {"name": c["name"], "icon": c["icon"], "positions": c["positions"], **_server(c)["stats"][position]}
        for c in _wrf()["champions"].values()
        if position in _server(c)["stats"]
    ]
    return sorted(picked, key=lambda c: -c["pick"])[:limit]


def get_champion(name: str) -> dict:
    champ = _find(name)
    return {
        "name": champ["name"],
        "icon": champ["icon"],
        "positions": champ["positions"],
        **_tips().get(champ["name"], {}),
    }


# How many options to suggest per build slot.
MAX_OPTIONS = 4
ANTI_MAGIC = re.compile(r"\bAP\b|magic", re.I)
ANTI_PHYSICAL_BURST = re.compile(r"\bAD burst\b|assassin", re.I)


def _plain(label: str) -> str:
    """Source labels like "Standard — bruiser" without the dash."""
    return re.sub(r"\s*[—–]\s*", ": ", label)


def _lane_data(champ: dict, position: str | None) -> tuple[str | None, dict, dict, dict]:
    """The lane to use and each source's build for it: WildRiftCore, server (RiftPatchNotes), WildRiftFire.
    When the champion has nothing for the lane asked for, their main lane is used instead."""
    wrc = (champ.get("wrc") or {}).get("builds") or {}
    server = _server(champ)["builds"]
    wrf = champ.get("builds") or {}
    if position and (position in wrc or position in server or position in wrf):
        lane = position
    else:
        main = next((pos for pos, b in wrf.items() if b is champ.get("build") or b == champ.get("build")), None)
        lane = main or next(iter(champ.get("positions") or {}), None)
        if lane not in wrc and lane not in server and lane not in wrf:
            lane = next(iter(wrc), None) or next(iter(server), None) or next(iter(wrf), None)
    return lane, wrc.get(lane) or {}, server.get(lane) or {}, wrf.get(lane) or {}


def _lanes_with_data(champ: dict) -> list[str]:
    """Every lane any source has a build for, the champion's listed lanes first."""
    lanes = list(champ.get("positions") or {})
    lanes += (
        list((champ.get("wrc") or {}).get("builds") or {})
        + list(_server(champ)["builds"])
        + list(champ.get("builds") or {})
    )
    return list(dict.fromkeys(lanes))


def _choices(wrc: dict, server: dict, wrf: dict) -> tuple[list[dict], list[dict]]:
    """Whole item cores and rune pages to choose from, most played first."""
    cores, pages = [], []
    for i, core in enumerate(server.get("cores", [])):
        label = "Most played" if i == 0 else f"Server alternative {i}"
        cores.append(
            {"label": label, "items": core["items"], "win": core["win"], "pick": core["pick"], "source": "server"}
        )
    for variant in wrc.get("variants", []):
        if len(variant["items"]) >= 3:
            cores.append(
                {
                    "label": _plain(variant["name"]),
                    "items": variant["items"][:3],
                    "when": variant["when"],
                    "source": "WildRiftCore",
                }
            )
    if wrf.get("core"):
        cores.append({"label": "WildRiftFire guide", "items": wrf["core"], "source": "WildRiftFire"})
    for i, page in enumerate(server.get("rune_pages", [])):
        label = "Most played" if i == 0 else f"Server alternative {i}"
        pages.append(
            {"label": label, "runes": page["runes"], "win": page["win"], "pick": page["pick"], "source": "server"}
        )
    if len(wrc.get("runes", [])) == 5:
        pages.append(
            {
                "label": "WildRiftCore",
                "runes": wrc["runes"],
                "note": wrc.get("rune_reason", ""),
                "source": "WildRiftCore",
            }
        )
    if wrf.get("runes"):
        pages.append({"label": "WildRiftFire guide", "runes": wrf["runes"], "source": "WildRiftFire"})
    if not pages and wrc.get("runes"):  # an incomplete page beats none when it's the only source for the lane
        pages.append(
            {
                "label": "WildRiftCore",
                "runes": wrc["runes"],
                "note": wrc.get("rune_reason", ""),
                "source": "WildRiftCore",
            }
        )
    # Keep one shape per build: the default's length decides.
    if cores:
        cores = [c for c in cores if len(c["items"]) == len(cores[0]["items"])]
    if pages:
        pages = [p for p in pages if len(p["runes"]) == len(pages[0]["runes"])]
    return cores, pages


def _extras(core: list[str], boots: list[str], wrc: dict, wrf: dict, count: int = 2) -> list[str]:
    """Items after the core: from the WildRiftCore variant closest to this core, then the guide's full build."""
    variants = sorted(wrc.get("variants", []), key=lambda v: -len(set(v["items"]) & set(core)))
    pool = [i for v in variants[:1] for i in v["items"]] + list(wrf.get("final", []))
    pool += [i for v in variants[1:] for i in v["items"]]
    taken = set(core) | set(boots)
    return [i for i in dict.fromkeys(pool) if i not in taken and not _is_boots(i)][:count]


def _is_boots(name: str) -> bool:
    item = _wrf()["items"].get(name) or {}
    return "Boots" in item.get("categories", []) or name in {"Mercury's Treads", "Plated Steelcaps"}


def _matchup_rule(foe: dict, wrc: dict, wrf: dict, server: dict) -> dict:
    """What to change against this opponent, most specific first:
    1. WildRiftCore names them as a hard matchup with a counter item (or a situational item names them).
    2. They deal magic damage: anti-magic boots and an anti-magic item from this champion's own options.
    3. They're a physical-damage assassin: the champion's own anti-burst item.
    Otherwise nothing changes and the most played build stays."""
    profile = foe.get("profile") or {}
    changes: list[dict] = []
    for entry in wrc.get("vs", []):
        if slug(entry["foe"]) == slug(foe["name"]):
            changes.append({"item": entry["item"], "why": f"Counter to {foe['name']} ({entry['why'].lower()})"})
    for entry in wrc.get("situational", []):
        if re.search(rf"\b{re.escape(foe['name'])}\b", entry["when"]):
            changes.append({"item": entry["item"], "why": entry["when"]})
    if changes:
        return {"rule": "specific", "changes": changes, "note": f"Matchup-specific build against {foe['name']}"}

    def own_options(pattern):
        items = [s["item"] for s in wrc.get("situational", []) if pattern.search(s["when"])]
        swaps = [s for s in wrf.get("situational", []) if pattern.search(s["when"])]
        return items + [s["with"] for s in swaps if not _is_boots(s["with"])], [
            s["with"] for s in swaps if _is_boots(s["with"])
        ]

    if profile.get("damage") == "magic":
        items, boots = own_options(ANTI_MAGIC)
        boots += [b["item"] for b in server.get("boots", []) if b.get("item") == "Mercury's Treads"]
        changes += [{"item": b, "why": f"{foe['name']} deals magic damage", "boots": True} for b in boots[:1]]
        changes += [{"item": i, "why": f"{foe['name']} deals magic damage"} for i in items[:1]]
        if changes:
            return {"rule": "magic", "changes": changes, "note": f"Anti-magic build: {foe['name']} deals magic damage"}
    if profile.get("damage") == "physical" and "assassin" in profile.get("tags", []):
        items, _ = own_options(ANTI_PHYSICAL_BURST)
        changes += [{"item": i, "why": f"{foe['name']} is a physical-damage assassin"} for i in items[:1]]
        if changes:
            return {"rule": "physical", "changes": changes, "note": f"Anti-burst build against {foe['name']}"}
    return {"rule": "general", "changes": [], "note": f"No change needed against {foe['name']}: most played build"}


def _option(name: str, why: str, matchup: bool = False) -> dict:
    return {"name": name, "why": why, "matchup": matchup}


def _rank(options: list[dict], current: str, taken: set[str]) -> list[dict]:
    """Unique options, matchup ones first, without the current pick or items used elsewhere in the build."""
    seen, ranked = set(), []
    for opt in sorted(options, key=lambda o: not o["matchup"]):
        if opt["name"] != current and opt["name"] not in taken and opt["name"] not in seen:
            seen.add(opt["name"])
            ranked.append(opt)
    return ranked[:MAX_OPTIONS]


def _choice_why(choice: dict) -> str:
    if "pick" in choice:
        return f"{choice['label']}: {choice['pick']:.0f}% pick, {choice['win']:.1f}% win"
    return choice["label"] + (f" ({choice['when']})" if choice.get("when") else "")


def _slot_options(build: dict, wrc: dict, wrf: dict, server: dict, rule: dict) -> dict:
    """Ranked alternatives for every slot: core items, boots, later items and runes."""
    choices, core, final, runes = build["choices"], build["core"], build["final"], build["runes"]
    used = set(final)
    matchup = [_option(c["item"], c["why"], True) for c in rule["changes"]]
    core_opts = []
    for slot in range(len(core)):
        opts = [_option(c["items"][slot], _choice_why(c)) for c in choices["core"] if slot < len(c["items"])]
        core_opts.append(_rank(opts, core[slot], used))
    boots_opts = [m for m in matchup if _is_boots(m["name"])]
    boots_opts += [
        _option(b["item"], f"Server: {b['pick']:.0f}% pick, {b['win']:.1f}% win")
        for b in server.get("boots", [])
        if b.get("item")
    ]
    boots_opts += [_option(s["with"], s["when"]) for s in wrf.get("situational", []) if _is_boots(s["with"])]
    if wrc.get("boots"):
        boots_opts.append(_option(wrc["boots"], "WildRiftCore"))
    later = [m for m in matchup if not _is_boots(m["name"])]
    later += [_option(s["item"], s["when"]) for s in wrc.get("situational", [])]
    later += [_option(s["with"], s["when"]) for s in wrf.get("situational", []) if not _is_boots(s["with"])]
    later += [_option(i, _plain(v["name"])) for v in wrc.get("variants", []) for i in v["items"][3:]]
    extra_opts = [_rank(later, item, used) for item in final[len(build["boots"]) + len(core) :]]
    catalog = _wrf()["runes"]
    rune_opts = []
    for slot in range(len(runes)):
        kind = "keystone" if slot == 0 else "minor"
        opts = [
            _option(p["runes"][slot], _choice_why(p))
            for p in choices["runes"]
            if slot < len(p["runes"]) and (catalog.get(p["runes"][slot]) or {}).get("kind", kind) == kind
        ]
        rune_opts.append(_rank(opts, runes[slot], set(runes)))
    return {
        "core": core_opts,
        "boots": _rank(boots_opts, (build["boots"] or [""])[0], used),
        "extras": extra_opts,
        "runes": rune_opts,
    }


def get_build(name: str, position: str | None = None, enemy: str | None = None) -> dict:
    """The champion's build for a lane, adjusted for the opponent when one is given.

    Without an opponent it's the most played build this patch: the server's most played core, boots, rune page
    and spells (RiftPatchNotes), later items from WildRiftCore's closest variant, with WildRiftFire's guide as
    the fallback. With an opponent, _matchup_rule decides what changes. "options" has ranked alternatives for
    every slot, "choices" whole cores and rune pages. "position" says which lane the build is for."""
    champ = _find(name)
    lane, wrc, server, wrf = _lane_data(champ, position)
    cores, pages = _choices(wrc, server, wrf)
    if cores and not pages:
        # Items for this lane but no rune page: runes depend less on the lane, so borrow another lane's page.
        for other in _lanes_with_data(champ):
            if other != lane:
                _, other_pages = _choices(*_lane_data(champ, other)[1:])
                pages = [{**page, "label": f"{page['label']} ({other})"} for page in other_pages]
                if pages:
                    break
    if not cores or not pages:
        raise UnknownChampionError(f"No build available for {champ['name']}")
    core = list(cores[0]["items"])
    boots = [b["item"] for b in server.get("boots", [])[:1] if b.get("item")]
    boots = boots or ([wrc["boots"]] if wrc.get("boots") else list(wrf.get("boots", []))[:1])
    extras = _extras(core, boots, wrc, wrf)
    spells = (server.get("spells") or [{}])[0].get("spells") or wrf.get("spells", [])

    foe = _find(enemy) if enemy else None
    rule = _matchup_rule(foe, wrc, wrf, server) if foe else {"rule": "general", "changes": [], "note": ""}
    adjustments = []
    for change in rule["changes"]:
        item = change["item"]
        if change.get("boots"):
            if boots and boots[0] != item:
                adjustments.append(
                    {"slot": "boots", "index": 0, "replace": boots[0], "with": item, "why": change["why"]}
                )
                boots = [item]
        elif item not in core and item not in extras and extras:
            slot = len(extras) - 1 - sum(1 for a in adjustments if a["slot"] == "extras")
            if slot >= 0:
                adjustments.append(
                    {"slot": "extras", "index": slot, "replace": extras[slot], "with": item, "why": change["why"]}
                )
                extras[slot] = item
    build = {
        "name": champ["name"],
        "position": lane,
        "core": core,
        "boots": boots,
        "final": boots + core + extras,
        "runes": list(pages[0]["runes"]),
        "spells": spells,
        "starting": wrf.get("starting", []),
        "situational": wrf.get("situational", []),
        "situational_items": wrc.get("situational", []),
        "countered_by": wrf.get("countered_by", []),
        "synergies": wrf.get("synergies", []),
        "counters": (champ.get("counters") or {}).get(lane) or wrf.get("counters") or [],
        "choices": {"core": cores, "runes": pages},
        "matchup": {"enemy": foe["name"], "rule": rule["rule"], "note": rule["note"], "adjustments": adjustments}
        if foe
        else None,
        # Server builds and stats for the lane asked for (or the build's own lane when it fell back).
        "server": server,
        "server_stats": _server(champ)["stats"].get(position or lane) or {},
        "patch": meta()["patch"],
    }
    build["options"] = _slot_options(build, wrc, wrf, server, rule)
    return build


def _names(entries: list[dict]) -> list[str]:
    return [e["name"] for e in entries]


def strong_against(enemy: str, position: str | None = None) -> list[dict]:
    """Champions listed as countering `enemy` in that lane, with their tiers, best tier first.
    Only champions in the current champion list are returned."""
    try:
        counters = _counters_of(get_build(enemy, position))
    except UnknownChampionError:
        return []
    result = []
    for entry in counters:
        name = _known_name(entry["name"])
        if name:
            champ = _find(name)
            result.append(
                {
                    "name": name,
                    "icon": champ["icon"],
                    "positions": champ["positions"],
                    "score": entry.get("score"),
                    "sources": entry.get("sources", []),
                }
            )
    # Strongest agreement first; the lane tier breaks ties.
    lane = position or ""
    return sorted(result, key=lambda c: (-(c["score"] or 0), TIER_ORDER.get(c["positions"].get(lane, ""), 9)))


def _counters_of(build: dict) -> list[dict]:
    """The combined multi-source counter list, or WildRiftFire's own list for older data."""
    return build.get("counters") or build.get("countered_by", [])


def get_matchup(my_champion: str, enemy: str, position: str | None = None) -> dict:
    mine, theirs = get_champion(my_champion), get_champion(enemy)

    def counter_names(name: str) -> list[str]:
        try:
            return _names(_counters_of(get_build(name, position)))
        except UnknownChampionError:
            return []

    def counter_score(counter: str, of: str) -> float:
        """How strongly the sources list `counter` as a counter to `of` (0 when not listed)."""
        try:
            entries = _counters_of(get_build(of, position))
        except UnknownChampionError:
            return 0.0
        return next((e.get("score") or 1.0 for e in entries if e["name"] == counter), 0.0)

    # Sources sometimes list each champion as countering the other; then the scores decide.
    mine_vs, theirs_vs = counter_score(mine["name"], theirs["name"]), counter_score(theirs["name"], mine["name"])
    gap = mine_vs - theirs_vs
    you_counter, they_counter, mutual = gap > EVEN_MARGIN, gap < -EVEN_MARGIN, bool(mine_vs and theirs_vs)
    mutual = mutual and abs(gap) <= EVEN_MARGIN
    # WildRiftCore rates this exact pairing: the opponent's edge over you, -2..+2. When it does, it decides.
    card = matchup_card(mine["name"], theirs["name"], position)
    if card:
        you_counter, they_counter, mutual = card["edge"] < 0, card["edge"] > 0, False
    tips = [t for t in (card["key"], card["how"]) if t] if card else []
    tips += theirs.get("playing_against", [])
    profile = _find(theirs["name"]).get("profile") or {}

    try:
        my_synergies = get_build(my_champion, position)["synergies"]
    except UnknownChampionError:
        my_synergies = []
    return {
        "enemy_countered_by": counter_names(theirs["name"]),
        "you_counter_enemy": you_counter,
        "enemy_counters_you": they_counter,
        "counters_each_other": mutual,
        "even": bool(card) and card["edge"] == 0,
        "card": card,
        "your_counter_score": mine_vs,
        "enemy_counter_score": theirs_vs,
        "your_synergies": my_synergies,
        "your_lane_stats": _server(_find(mine["name"]))["stats"].get(position or "") or {},
        "enemy_lane_stats": _server(_find(theirs["name"]))["stats"].get(position or "") or {},
        "you": mine["name"],
        "enemy": theirs["name"],
        "enemy_tiers": theirs["positions"],
        "your_strengths": mine.get("strengths", []),
        "enemy_strengths": theirs.get("strengths", []),
        "enemy_weaknesses": theirs.get("weaknesses", []),
        "how_to_play_against_enemy": tips,
        "enemy_damage_type": theirs.get("damage") or profile.get("damage"),
        "enemy_classes": profile.get("tags", []),
        "enemy_heals": theirs.get("heals"),
        "has_tips": bool(tips),
    }


def matchup_card(mine: str, enemy: str, position: str | None = None) -> dict | None:
    """WildRiftCore's card for this pairing: the opponent's edge over you (-2..+2), the matchup group,
    tags, the interaction that decides it and how to play it. None when they don't rate the pairing."""
    champ, foe = _find(mine), _find(enemy)

    def card_on(page_of: dict, about: dict) -> dict | None:
        lanes = (page_of.get("wrc") or {}).get("matchups") or {}
        lane_cards = lanes.get(position) if position else next(iter(lanes.values()), None)
        return next((c for n, c in (lane_cards or {}).items() if slug(n) == slug(about["name"])), None)

    card = card_on(champ, foe)
    if card:
        return {"enemy": foe["name"], **card}
    # Not on your champion's page: their page may rate you. Flip the edge; its tips are for the other side.
    reverse = card_on(foe, champ)
    if reverse:
        return {
            "enemy": foe["name"],
            "edge": -reverse["edge"],
            "group": None,
            "tags": reverse["tags"],
            "key": "",
            "how": "",
        }
    return None


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
    """The rune list's icon (some are .webp from WildRiftCore), else a downloaded .png."""
    icon = (_wrf()["runes"].get(name) or {}).get("icon")
    if icon and (ROOT / "static" / icon.lstrip("/")).exists():
        return icon
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


def validate_runes(champion: str, runes: list[str], position: str | None = None) -> list[str]:
    """Check a rune page: same number of runes as the build, keystone first, minors after, no repeats.
    Row rules inside each tree aren't known, so those aren't checked."""
    expected = len(get_build(champion, position)["runes"])
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


def swap_core_item(champion: str, remove: str, add: str, position: str | None = None) -> dict:
    """Return the champion's build with one core item replaced by another."""
    return _swap(get_build(champion, position), remove, add)


def apply_swaps(champion: str, swaps: list[tuple[str, str]], position: str | None = None) -> dict:
    """Apply several (remove, add) swaps in order to the champion's build."""
    build = get_build(champion, position)
    for remove, add in swaps:
        build = _swap(build, remove, add)
    return build


def _swap(build: dict, remove: str, add: str) -> dict:
    old, new = resolve_item(remove), resolve_item(add)
    if "Boots" in _wrf()["items"].get(new, {}).get("categories", []):
        raise ValueError(f"{new} is boots and can't be a core item")
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


def _known_name(name: str) -> str | None:
    try:
        return _find(name)["name"]
    except UnknownChampionError:
        return None


def save_profile(user: str, profile: dict[str, list[str]]) -> dict[str, list[str]]:
    """Save a user's pool. Names not in the current champion list are dropped (e.g. a champion
    that left the tier list after a patch), so one stale name never blocks saving."""
    clean = {}
    for position in POSITIONS:
        names = (_known_name(n) for n in profile.get(position, []))
        clean[position] = list(dict.fromkeys(n for n in names if n))
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    _profile_file(user).write_text(json.dumps(clean, indent=1), encoding="utf-8")
    return clean


def _prefs_file(user: str) -> Path:
    return PREFS_DIR / f"{user}.json"  # user names are validated in security.py


def _all_prefs(user: str) -> dict:
    path = _prefs_file(user)
    return _read(path) if path.exists() else {}


def _prefs_key(champion: str, position: str | None) -> str:
    """Saved builds are per champion per lane, e.g. "Darius@jungle"."""
    build = get_build(champion, position)
    return f"{build['name']}@{build['position']}" if build["position"] else build["name"]


def get_preferences(user: str | None, champion: str, position: str | None = None) -> dict | None:
    """A user's saved core items and runes for a champion in a lane, or None."""
    if not user:
        return None
    try:
        saved = _all_prefs(user).get(_prefs_key(champion, position))
    except UnknownChampionError:
        return None
    if not saved:
        return None
    # A patch can remove items or runes or change the build's shape; then the saved build is dropped.
    try:
        build = get_build(champion, position)
        later = saved.get("extras", []) + ([saved["boots"]] if saved.get("boots") else [])
        items_ok = all(i in _wrf()["items"] for i in saved["core"] + later)
        items_ok = items_ok and len(saved["core"]) == len(build["core"])
        validate_runes(champion, saved["runes"], position)
    except (UnknownChampionError, UnknownRuneError, ValueError, KeyError):
        return None
    return saved if items_ok else None


def save_preferences(
    user: str,
    champion: str,
    core: list[str],
    runes: list[str],
    position: str | None = None,
    boots: str | None = None,
    extras: list[str] | None = None,
) -> dict:
    """Save a user's own core items and runes (and optionally boots and later items) for a champion in a lane."""
    build = get_build(champion, position)
    core_items = [resolve_item(i) for i in core]
    if len(core_items) != len(build["core"]) or len(set(core_items)) != len(core_items):
        raise ValueError(f"Core needs {len(build['core'])} different items")
    boots_in_core = [i for i in core_items if "Boots" in _wrf()["items"][i]["categories"]]
    if boots_in_core:
        raise ValueError(f"Boots can't be core items: {', '.join(boots_in_core)}")
    prefs = _all_prefs(user)
    key = _prefs_key(champion, position)
    prefs[key] = {"core": core_items, "runes": validate_runes(build["name"], runes, position)}
    if boots:
        prefs[key]["boots"] = resolve_item(boots)
    if extras:
        later = [resolve_item(i) for i in extras]
        if len(set(later) | set(core_items)) != len(later) + len(core_items):
            raise ValueError("An item can only be in the build once")
        prefs[key]["extras"] = later
    PREFS_DIR.mkdir(parents=True, exist_ok=True)
    _prefs_file(user).write_text(json.dumps(prefs, indent=1), encoding="utf-8")
    return prefs[key]


def reset_preferences(user: str, champion: str, position: str | None = None) -> None:
    prefs = _all_prefs(user)
    if prefs.pop(_prefs_key(champion, position), None) is not None:
        _prefs_file(user).write_text(json.dumps(prefs, indent=1), encoding="utf-8")
