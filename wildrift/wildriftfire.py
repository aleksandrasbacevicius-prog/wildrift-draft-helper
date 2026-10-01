"""Fetch tier list, champion builds, items, icons and patch from WildRiftFire.com.

Only public pages allowed by robots.txt are read (/tier-list, /item-list, /guide/<champion>).
Requests are spaced out so a full refresh takes a few minutes.

    python -m wildrift.wildriftfire          # refresh only if the patch changed or data is old
    python -m wildrift.wildriftfire --force  # always refresh
"""

import argparse
import html
import json
import os
import re
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("WILDRIFT_DATA_DIR", ROOT / "data" / "wildriftfire"))
ICON_DIR = ROOT / "static" / "icons" / "wrf"
SITE = "https://www.wildriftfire.com"
HEADERS = {"User-Agent": "wildrift-draft-helper (personal, non-commercial)"}
REQUEST_DELAY = 1.0  # seconds between page requests
# Scraped pages can point anywhere, so only these hosts are ever contacted.
ALLOWED_HOSTS = {"www.wildriftfire.com", "wildriftfire.com", "www.mobafire.com", "mobafire.com", "wr-meta.com"}
# Item stats and descriptions come from WR-META's public item list (its robots.txt allows /items/).
ITEM_DETAILS_URL = "https://wr-meta.com/items/"
# WR-META champion pages add a second, independent counter list per lane (only the free "Extreme" band).
WRMETA_HOME = "https://wr-meta.com/"
WRMETA_LANES = {
    "solo": "baron",
    "baron": "baron",
    "jungle": "jungle",
    "mid": "mid",
    "adc": "dragon",
    "dragon": "dragon",
    "duo": "dragon",
    "bot": "dragon",
    "support": "support",
}
COUNTER_SOURCES = ("WildRiftFire", "WR-META")
MAX_PAGE_BYTES = 3 * 1024 * 1024
MAX_IMAGE_BYTES = 512 * 1024
MAX_AGE_DAYS = 7  # tier lists move within a patch, so refresh weekly anyway

# Site lane names -> in-game positions
POSITIONS = {"Solo": "baron", "Jungle": "jungle", "Mid": "mid", "Duo": "dragon", "Support": "support"}
TIERS = {"splus": "S+", "s": "S", "a": "A", "b": "B", "c": "C", "d": "D"}


def _open(url: str, max_bytes: int) -> tuple[bytes, str]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"refusing to fetch {url}")
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        if urlparse(response.geturl()).hostname not in ALLOWED_HOSTS:  # redirected elsewhere
            raise ValueError(f"{url} redirected off the allowed hosts")
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError(f"{url} is larger than {max_bytes} bytes")
        return body, response.headers.get_content_type()


def get(url: str) -> str:
    return _open(url, MAX_PAGE_BYTES)[0].decode("utf-8", errors="ignore")


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower().replace("'", "")).strip("-")


def parse_patch(page: str) -> str | None:
    found = re.findall(r"[Pp]atch\s*v?((\d+)\.(\d+)([a-z]?))", page)
    if not found:
        return None
    return max(found, key=lambda p: (int(p[1]), int(p[2]), p[3]))[0]


def parse_tier_list(page: str) -> dict:
    main = page[page.find("wf-tier-list__tiers__main") : page.find("wf-tier-list__tiers__sidebar")]
    parts = re.split(r'<div class="tier ([a-z]+)">', main)
    champions: dict[str, dict] = {}
    for tier_class, body in zip(parts[1::2], parts[2::2], strict=True):
        for m in re.finditer(
            r'href="/guide/([^"]+)"[^>]*data-role="([^"]+)".*?<div class="item-holder">\s*<img src="([^"]+)".*?<span>([^<]+)</span>',
            body,
            re.S,
        ):
            guide, lane, icon, name = m.groups()
            name = html.unescape(name).strip()
            icon = icon if icon.startswith("http") else SITE + icon
            champ = champions.setdefault(name, {"name": name, "guide": guide, "icon_url": icon, "positions": {}})
            champ["positions"][POSITIONS.get(lane, lane.lower())] = TIERS.get(tier_class, tier_class.upper())
    return champions


def _items_in(section: str) -> list[str]:
    return [html.unescape(n).strip() for n in re.findall(r'<div class="name">([^<]+)', section)]


# Lane names in image file names on guide pages -> in-game positions
LANE_IMAGES = {
    "solo": "baron",
    "baron": "baron",
    "jungle": "jungle",
    "mid": "mid",
    "duo": "dragon",
    "adc": "dragon",
    "dragon": "dragon",
    "support": "support",
}


def _champions_in(section: str) -> list[dict]:
    """Champion entries in a counters/synergies list: name plus the lane they're listed for."""
    found = []
    for lane, name in re.findall(r"/images/lanes/white-([a-z]+)\.png.*?<span>([^<]+)</span>", section, re.S):
        found.append({"name": html.unescape(name).strip(), "position": LANE_IMAGES.get(lane, lane)})
    return found


def _parse_build(blocks: dict[str, str]) -> dict:
    """One lane's build from that lane's page blocks (items, spells, situational, counters)."""
    build: dict = {}
    items = blocks.get("items", "")
    for name in ("starting", "core", "boots", "final"):
        m = re.search(rf'<div class="section {name}">(.*?)(?=<div class="section |$)', items, re.S)
        build[name] = _items_in(m.group(1)) if m else []

    situational = []
    for label, body in re.findall(
        r'<span class="situation"[^>]*>([^<]+)</span>(.*?)(?=<span class="situation"|$)',
        blocks.get("situational", ""),
        re.S,
    ):
        found = _items_in(body)
        if len(found) >= 2:
            situational.append({"when": html.unescape(label).strip(), "replace": found[0], "with": found[1]})
    build["situational"] = situational

    spells = blocks.get("spells", "")
    build["spells"] = [html.unescape(n) for n in re.findall(r"/images/summoners/[^\"]+\" alt=\"([^\"]+)\"", spells)]
    build["runes"] = [html.unescape(n) for n in re.findall(r"/images/runes/[^\"]+\" alt=\"([^\"]+)\"", spells)]

    counters = blocks.get("counters", "")
    countered = re.search(r"counters-mod counters\"(.*?)(?=counters-mod synergies|$)", counters, re.S)
    synergies = re.search(r"counters-mod synergies\"(.*)", counters, re.S)
    build["countered_by"] = _champions_in(countered.group(1)) if countered else []
    build["synergies"] = _champions_in(synergies.group(1)) if synergies else []
    return build


BLOCK_KINDS = {
    "wf-champion__data__items": "items",
    "wf-champion__data__spells": "spells",
    "wf-champion__data__situational": "situational",
    "skills-counters-block": "counters",
}


def parse_guides(page: str, default_position: str | None = None) -> dict[str, dict]:
    """Every lane's build on a champion page, keyed by position. The page's recommended lane comes first.

    Pages with a single build have no lane selector; that build belongs to the page's "Recommended Role",
    or failing that to `default_position` (the champion's lane in the tier list)."""
    # Which guide id belongs to which lane, from the lane selector ("Solo Build", "Jungle Build", ...)
    lanes = {}
    for guide_id, lane in re.findall(
        r'<span[^>]*data-guide-id="(\d+)"[^>]*>\s*<img src="/images/lanes/white-([a-z]+)\.png">', page
    ):
        lanes.setdefault(guide_id, LANE_IMAGES.get(lane, lane))

    # Each block is tagged with its guide id; it runs until the next block starts.
    markers = list(re.finditer(r'<div class="([^"]*?)\s*data-block[^"]*"\s*data-guide-id="(\d+)"', page))
    blocks: dict[str, dict[str, str]] = {}
    for i, m in enumerate(markers):
        kind = next((k for cls, k in BLOCK_KINDS.items() if cls in m.group(1)), None)
        if kind:
            end = markers[i + 1].start() if i + 1 < len(markers) else len(page)
            blocks.setdefault(m.group(2), {})[kind] = page[m.start() : end]

    recommended = re.search(
        r'Recommended Role</span>\s*<span class="data">\s*<img src="/images/lanes/white-([a-z]+)\.png">', page
    )
    fallback = LANE_IMAGES.get(recommended.group(1)) if recommended else default_position

    builds = {}
    for guide_id, parts in blocks.items():
        position = lanes.get(guide_id) or fallback or f"guide-{guide_id}"
        builds.setdefault(position, _parse_build(parts))
    return builds


def parse_guide(page: str) -> dict:
    """The recommended (first) build on a champion page."""
    builds = parse_guides(page)
    return next(iter(builds.values())) if builds else _parse_build({})


def parse_item_list(page: str) -> dict:
    items = {}
    for categories, img, name in re.findall(
        r'class="ico-holder[^"]*"\s+data-sort="([^"]*)".*?<img src="(/images/items/[^"]+)">.*?<span>([^<]+)</span>',
        page,
        re.S,
    ):
        name = html.unescape(name).strip()
        items[name] = {"name": name, "categories": [c for c in categories.split(",") if c], "icon_url": SITE + img}
    return items


def _text(fragment: str) -> str:
    """HTML fragment to plain text."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", fragment))).strip()


def _item_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def parse_item_details(page: str) -> dict[str, dict]:
    """Stats, effects, gold cost and a buying tip per item, from WR-META's item list."""
    details = {}
    for block in page.split('<div class="bild-img-short">')[1:]:
        name = re.search(r'<b class="iname">(.*?)</b>', block, re.S)
        if not name:
            continue
        name = _text(name.group(1))
        summary = re.search(r'<b class="iname">.*?</b>\s*<br>\s*<b class="cdr">(.*?)</b>', block, re.S)
        stats = [_text(s) for s in re.findall(r'<b class="istats">(.*?)</b>', block, re.S)]
        effects = []
        for label, body in re.findall(r'<b class="istats2">(.*?)</b>(.*?)(?=<br>|<b class="istats2">|$)', block, re.S):
            effects.append({"name": _text(label).rstrip(":"), "text": _text(body)})
        gold = re.search(r'<b class="goldt">\s*(\d+)\s*</b>', block)
        tip = re.search(r"TIPS:</b>(.*?)</p>", block, re.S)
        details[_item_key(name)] = {
            "summary": _text(summary.group(1)) if summary else "",
            "stats": [s for s in stats if s],
            "effects": [e for e in effects if e["text"]],
            "gold": int(gold.group(1)) if gold else None,
            "tip": _text(tip.group(1)) if tip else "",
        }
    return details


def name_key(name: str) -> str:
    """Match champion names across sites: "Kha'Zix", "kha-zix" and "Nunu &amp; Willump" all line up."""
    return re.sub(r"[^a-z0-9]", "", html.unescape(name).lower().replace("-amp-", "").replace("&", ""))


def parse_wrmeta_champion_links(page: str) -> dict[str, str]:
    """Champion page URLs on WR-META, keyed by name_key."""
    links = {}
    for url, slug_ in re.findall(r"(https://wr-meta\.com/\d+-([a-z0-9-]+)\.html)", page):
        links.setdefault(name_key(slug_), url)
    return links


def parse_wrmeta_counters(page: str) -> dict[str, list[str]]:
    """Per lane, the champions in WR-META's free "Extreme threats" band (as name keys, strongest first)."""
    counters = {}
    for m in re.finditer(r'<h2><i class="demo-icon ([a-z]+)-[a-z]+icon-"></i>[^<]*?Counters</h2>', page):
        lane = WRMETA_LANES.get(m.group(1))
        section = page[m.end() :]
        first_tab = section.find('<div class="tabs-b2">')
        if not lane or first_tab < 0:
            continue
        tab = section[first_tab + 1 :]
        tab = tab[: tab.find('<div class="tabs-b2">')]
        if "lock-block" in tab:  # premium-only content: not used
            continue
        names = [
            name_key(n)
            for n in re.findall(
                r'class="counter-champion">\s*<a href="https://wr-meta\.com/\d+-([a-z0-9-]+)\.html"', tab
            )
        ]
        if names:
            counters.setdefault(lane, names)
    return counters


def combine_counters(lists: dict[str, list[str]], names: dict[str, str]) -> list[dict]:
    """Average each champion's rank-based score across the sources that rate this lane.

    Rank 1 in a list scores 1.0, rank 2 0.9, and so on. A source that has a list but doesn't mention a
    champion gives them 0, so a champion several sources agree on ranks above one only a single source lists.
    `names` maps name keys back to display names; unknown champions are skipped.
    """
    rated = {source: ranked for source, ranked in lists.items() if ranked}
    scores: dict[str, dict] = {}
    for source, ranked in rated.items():
        for rank, key in enumerate(ranked):
            if key not in names:
                continue
            entry = scores.setdefault(key, {"name": names[key], "score": 0.0, "sources": []})
            entry["score"] += max(0.1, 1 - rank * 0.1)
            entry["sources"].append(source)
    for entry in scores.values():
        entry["score"] = round(entry["score"] / len(rated), 3)
    return sorted(scores.values(), key=lambda e: (-e["score"], e["name"]))


def add_wrmeta_counters(champions: dict, log=print) -> None:
    """Fetch WR-META's counter lists and merge them with WildRiftFire's into build["counters"] per lane."""
    names = {name_key(n): n for n in champions}
    try:
        links = parse_wrmeta_champion_links(get(WRMETA_HOME))
    except Exception as e:
        links = {}
        log(f"WR-META counters unavailable ({e}); using WildRiftFire only")
    fetched = 0
    for name, champ in champions.items():
        wrmeta = {}
        url = links.get(name_key(name))
        if url:
            time.sleep(REQUEST_DELAY)
            try:
                wrmeta = parse_wrmeta_counters(get(url))
                fetched += 1
            except Exception as e:
                log(f"  {name}: WR-META counters failed ({e})")
        for position, build in (champ.get("builds") or {}).items():
            wrf = [name_key(c["name"]) for c in build.get("countered_by", [])]
            build["counters"] = combine_counters({"WildRiftFire": wrf, "WR-META": wrmeta.get(position, [])}, names)
    log(f"Counters combined from WildRiftFire and WR-META ({fetched} WR-META pages)")


def add_item_details(items: dict, log=print) -> None:
    """Attach WR-META's stats and descriptions to our items, matched by name. Optional: failures are logged."""
    try:
        details = parse_item_details(get(ITEM_DETAILS_URL))
    except Exception as e:
        log(f"Item details unavailable ({e})")
        return
    matched = 0
    for name, item in items.items():
        found = details.get(_item_key(name))
        if found:
            item["details"] = found
            matched += 1
    log(f"Item details for {matched}/{len(items)} items")


def parse_rune_list(page: str) -> dict:
    """Every rune with its type (keystone or minor), tree and tier."""
    main = page[page.find("wf-tier-list__tiers__main") : page.find("wf-tier-list__tiers__sidebar")]
    parts = re.split(r'<div class="tier ([a-z]+)">', main)
    runes = {}
    for tier_class, body in zip(parts[1::2], parts[2::2], strict=True):
        for sort, name in re.findall(
            r'class="ico-holder[^"]*"\s+data-sort="([^"]*)".*?<span>([^<]+)</span>', body, re.S
        ):
            name = html.unescape(name).strip()
            words = sort.split()
            kind = "keystone" if "Keystone" in words else "minor"
            tree = next((w for w in words if w not in ("Keystone", "Minor")), "Keystone" if kind == "keystone" else "")
            runes[name] = {
                "name": name,
                "kind": kind,
                "tree": tree,
                "tier": TIERS.get(tier_class, tier_class.upper()),
                "icon": f"/icons/wrf/runes/{slug(name)}.png",
            }
    return runes


def _download_icon(url: str, path: Path) -> None:
    if path.exists():
        return
    body, content_type = _open(url, MAX_IMAGE_BYTES)
    if content_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise ValueError(f"{url} is not an image ({content_type})")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    time.sleep(0.2)


def download_lane_icons() -> None:
    lane_files = {"baron": "baron", "jungle": "jungle", "mid": "mid", "dragon": "adc", "support": "support"}
    for position, name in lane_files.items():
        _download_icon(f"{SITE}/images/lanes/white-{name}.png", ICON_DIR / "lanes" / f"{position}.png")


def load_meta() -> dict:
    path = DATA_DIR / "meta.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def needs_refresh() -> tuple[bool, str]:
    """One request: compare the live patch with the stored one, and check data age."""
    meta = load_meta()
    if not meta:
        return True, "no data yet"
    live_patch = parse_patch(get(f"{SITE}/tier-list"))
    if live_patch and live_patch != meta.get("patch"):
        return True, f"new patch {live_patch} (have {meta.get('patch')})"
    age = (date.today() - date.fromisoformat(meta["fetched"][:10])).days
    if age >= MAX_AGE_DAYS:
        return True, f"data is {age} days old"
    return False, f"up to date (patch {meta.get('patch')}, fetched {meta['fetched'][:10]})"


def refresh(log=print) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tier_page = get(f"{SITE}/tier-list")
    patch = parse_patch(tier_page)
    champions = parse_tier_list(tier_page)
    log(f"Patch {patch}: {len(champions)} champions in the tier list")

    time.sleep(REQUEST_DELAY)
    items = parse_item_list(get(f"{SITE}/item-list"))
    log(f"{len(items)} items")

    time.sleep(REQUEST_DELAY)
    runes = parse_rune_list(get(f"{SITE}/rune-list"))
    log(f"{len(runes)} runes")

    for i, champ in enumerate(champions.values(), 1):
        time.sleep(REQUEST_DELAY)
        try:
            builds = {
                pos: b
                for pos, b in parse_guides(
                    get(f"{SITE}/guide/{champ['guide']}"), next(iter(champ["positions"]), None)
                ).items()
                if b["core"]
            }
            if not builds:
                raise ValueError("no core items found on the page")
            champ["builds"] = builds
            champ["build"] = next(iter(builds.values()))  # the page's recommended lane
        except Exception as e:  # one broken page shouldn't stop the refresh
            log(f"  {champ['name']}: build failed ({e})")
            champ["build"], champ["builds"] = None, {}
        if i % 20 == 0:
            log(f"  builds {i}/{len(champions)}")

    # Builds can use items missing from the item list (e.g. starting items like Ruby Crystal).
    all_builds = [b for c in champions.values() for b in (c.get("builds") or {}).values()]
    for build in all_builds:
        for section in ("starting", "core", "boots", "final"):
            for name in build.get(section, []):
                if name not in items:
                    items[name] = {"name": name, "categories": [], "icon_url": f"{SITE}/images/items/{slug(name)}.png"}

    for champ in champions.values():
        champ["icon"] = f"/icons/wrf/champions/{slug(champ['name'])}.png"
        _download_icon(champ.pop("icon_url"), ICON_DIR / "champions" / f"{slug(champ['name'])}.png")
    for item in items.values():
        item["icon"] = f"/icons/wrf/items/{slug(item['name'])}.png"
        try:
            _download_icon(item.pop("icon_url"), ICON_DIR / "items" / f"{slug(item['name'])}.png")
        except Exception as e:
            log(f"  icon for {item['name']} failed ({e})")
            item["icon"] = None
    download_lane_icons()

    # Runes appear in builds and in situational swaps (e.g. "vs Burst: Conqueror -> Aftershock").
    rune_names = set(runes) | {r for b in all_builds for r in b.get("runes", [])}
    rune_names |= {
        name
        for b in all_builds
        for s in b.get("situational", [])
        for name in (s["replace"], s["with"])
        if name not in items
    }
    for rune in rune_names:
        try:
            _download_icon(f"{SITE}/images/runes/{slug(rune)}.png", ICON_DIR / "runes" / f"{slug(rune)}.png")
        except Exception as e:
            log(f"  icon for rune {rune} failed ({e})")
    for spell in {s for b in all_builds for s in b.get("spells", [])}:
        try:
            _download_icon(f"{SITE}/images/summoners/{slug(spell)}.png", ICON_DIR / "spells" / f"{slug(spell)}.png")
        except Exception as e:
            log(f"  icon for spell {spell} failed ({e})")

    meta = {"patch": patch, "fetched": datetime.now().isoformat(timespec="seconds"), "source": SITE}
    add_item_details(items, log)
    add_wrmeta_counters(champions, log)
    unplaced = sorted(
        n for n, c in champions.items() for pos in (c.get("builds") or {}) if pos not in LANE_IMAGES.values()
    )
    if unplaced:
        log(f"Warning: builds without a known lane for {', '.join(unplaced)}")

    # Write each file to a temp name first, then swap it in, so the app never reads a half-written file.
    # meta.json goes last: it marks the refresh as complete.
    for name, content in (("champions", champions), ("items", items), ("runes", runes), ("meta", meta)):
        tmp = DATA_DIR / f"{name}.json.tmp"
        tmp.write_text(json.dumps(content, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(DATA_DIR / f"{name}.json")
    log(f"Saved patch {patch} data to {DATA_DIR}")
    return meta


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="refresh even if the patch hasn't changed")
    args = parser.parse_args()
    stale, reason = needs_refresh()
    print(reason)
    if args.force or stale:
        refresh()


if __name__ == "__main__":
    main()
