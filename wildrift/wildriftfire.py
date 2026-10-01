"""Fetch tier list, champion builds, items, icons and patch from WildRiftFire.com.

Only public pages allowed by robots.txt are read (/tier-list, /item-list, /guide/<champion>).
Requests are spaced out so a full refresh takes a few minutes.

    python -m wildrift.wildriftfire          # refresh only if the patch changed or data is old
    python -m wildrift.wildriftfire --force  # always refresh
"""

import argparse
import html
import json
import re
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "wildriftfire"
ICON_DIR = ROOT / "static" / "icons" / "wrf"
SITE = "https://www.wildriftfire.com"
HEADERS = {"User-Agent": "wildrift-draft-helper (personal, non-commercial)"}
REQUEST_DELAY = 1.0  # seconds between page requests
MAX_AGE_DAYS = 7  # tier lists move within a patch, so refresh weekly anyway

# Site lane names -> in-game positions
POSITIONS = {"Solo": "baron", "Jungle": "jungle", "Mid": "mid", "Duo": "dragon", "Support": "support"}
TIERS = {"splus": "S+", "s": "S", "a": "A", "b": "B", "c": "C", "d": "D"}


def get(url: str) -> str:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="ignore")


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
    for tier_class, body in zip(parts[1::2], parts[2::2]):
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


def parse_guide(page: str) -> dict:
    build: dict = {}
    block = page[page.find("wf-champion__data__items") : page.find("wf-champion__data__spells")]
    for name in ("starting", "core", "boots", "final"):
        m = re.search(rf'<div class="section {name}">(.*?)(?=<div class="section |$)', block, re.S)
        build[name] = _items_in(m.group(1)) if m else []

    situational = []
    sit = page[page.find("wf-champion__data__situational") : page.find("skills-counters-block")]
    for label, body in re.findall(r'<span class="situation"[^>]*>([^<]+)</span>(.*?)(?=<span class="situation"|$)', sit, re.S):
        items = _items_in(body)
        if len(items) >= 2:
            situational.append({"when": html.unescape(label).strip(), "replace": items[0], "with": items[1]})
    build["situational"] = situational

    spells = page[page.find("wf-champion__data__spells") : page.find("wf-champion__data__situational")]
    build["spells"] = [html.unescape(n) for n in re.findall(r"/images/summoners/[^\"]+\" alt=\"([^\"]+)\"", spells)]
    build["runes"] = [html.unescape(n) for n in re.findall(r"/images/runes/[^\"]+\" alt=\"([^\"]+)\"", spells)]
    return build


def parse_item_list(page: str) -> dict:
    items = {}
    for categories, img, name in re.findall(
        r'class="ico-holder[^"]*"\s+data-sort="([^"]*)".*?<img src="(/images/items/[^"]+)">.*?<span>([^<]+)</span>', page, re.S
    ):
        name = html.unescape(name).strip()
        items[name] = {"name": name, "categories": [c for c in categories.split(",") if c], "icon_url": SITE + img}
    return items


def _download_icon(url: str, path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        path.write_bytes(response.read())
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

    for i, champ in enumerate(champions.values(), 1):
        time.sleep(REQUEST_DELAY)
        try:
            champ["build"] = parse_guide(get(f"{SITE}/guide/{champ['guide']}"))
        except Exception as e:  # one broken page shouldn't stop the refresh
            log(f"  {champ['name']}: build failed ({e})")
            champ["build"] = None
        if i % 20 == 0:
            log(f"  builds {i}/{len(champions)}")

    # Builds can use items missing from the item list (e.g. starting items like Ruby Crystal).
    for champ in champions.values():
        for section in ("starting", "core", "boots", "final"):
            for name in (champ["build"] or {}).get(section, []):
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
    runes = {r for c in champions.values() for r in (c["build"] or {}).get("runes", [])}
    runes |= {
        name
        for c in champions.values()
        for s in (c["build"] or {}).get("situational", [])
        for name in (s["replace"], s["with"])
        if name not in items
    }
    for rune in runes:
        try:
            _download_icon(f"{SITE}/images/runes/{slug(rune)}.png", ICON_DIR / "runes" / f"{slug(rune)}.png")
        except Exception as e:
            log(f"  icon for rune {rune} failed ({e})")

    meta = {"patch": patch, "fetched": datetime.now().isoformat(timespec="seconds"), "source": SITE}
    (DATA_DIR / "champions.json").write_text(json.dumps(champions, indent=1, ensure_ascii=False), encoding="utf-8")
    (DATA_DIR / "items.json").write_text(json.dumps(items, indent=1, ensure_ascii=False), encoding="utf-8")
    (DATA_DIR / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
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
