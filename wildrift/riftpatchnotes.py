"""Server statistics from RiftPatchNotes.com: real build and lane stats from Diamond+ ranked games
on the Wild Rift CN server (the only region with official ranked statistics).

- Per champion and lane: the most popular item cores (and two alternatives), boots, rune pages and
  summoner spells, each with its win rate and pick rate.
- Per lane: every champion's win, pick and ban rate, used to rank the most common opponents this patch.

Its robots.txt allows all crawlers, AI ones included. Requests are spaced out like the WildRiftFire fetcher's.
"""

import html
import json
import re

SITE = "https://www.riftpatchnotes.com"
# The rank bracket used for everything: 1 = Diamond+ (2 = Master+, 3 = Challenger+). Diamond+ has the most games.
RANK = 1
BRACKET = "Diamond+"
# Position numbers on the win-rate page, and lane names on champion pages, mapped to in-game lanes.
POSITION_NUMBERS = {1: "mid", 2: "baron", 3: "dragon", 4: "support", 5: "jungle"}
LANE_NAMES = {
    "top": "baron",
    "baron": "baron",
    "jungle": "jungle",
    "mid": "mid",
    "adc": "dragon",
    "bot": "dragon",
    "dragon": "dragon",
    "duo": "dragon",
    "support": "support",
}

OPTION = re.compile(
    r"(Most popular core|Alternative core \d|Most popular boots|Alternative boots|Most popular page|Alternative page"
    r"|Most popular summoners|Alternative summoners)(?:<!-- -->)?\s*<span[^>]*>\s*([\d.]+)% WR\s*\S\s*([\d.]+)% pick"
)


def _names(fragment: str) -> list[str]:
    return [html.unescape(n).strip() for n in re.findall(r'<img[^>]*\balt="([^"]+)"', fragment)]


def parse_champion_builds(page: str) -> dict[str, dict]:
    """Per lane: cores, boots, rune pages and spell pairs, each with win and pick rate (percent)."""
    lanes = {}
    blocks = re.split(r'<div data-form="([A-Za-z]+)"', page)
    if len(blocks) == 1:
        # Champions with one lane have no lane tabs: the lane is only named in the "Build Guide (Mid)" heading.
        single = re.search(r"Build Guide\s*(?:<span[^>]*>)?\((?:<!-- -->)?([A-Za-z]+)", page)
        blocks = ["", single.group(1), page[single.end() :]] if single else [page]
    for lane_name, body in zip(blocks[1::2], blocks[2::2], strict=True):
        lane = LANE_NAMES.get(lane_name.lower())
        if not lane:
            continue
        build = {"cores": [], "boots": [], "rune_pages": [], "spells": []}
        options = list(OPTION.finditer(body))
        for i, m in enumerate(options):
            label, win, pick = m.group(1), float(m.group(2)), float(m.group(3))
            content = body[m.end() : options[i + 1].start() if i + 1 < len(options) else len(body)]
            names = _names(content)
            entry = {"label": label, "win": win, "pick": pick}
            if "core" in label:
                build["cores"].append({**entry, "items": names})
            elif "boots" in label:
                build["boots"].append({**entry, "item": names[0] if names else None})
            elif "page" in label:
                trees = re.search(r">\s*([A-Za-z]+)(?:<!-- -->)?\s*primary\s*\S\s*(?:<!-- -->)?([A-Za-z]+)", content)
                build["rune_pages"].append(
                    {
                        **entry,
                        "runes": names,
                        "primary": trees.group(1) if trees else None,
                        "secondary": trees.group(2) if trees else None,
                    }
                )
            else:
                build["spells"].append({**entry, "spells": names[:2]})
        updated = re.search(r"updated (?:<!-- -->)?(\d{4}-\d{2}-\d{2})", body)
        build["updated"] = updated.group(1) if updated else None
        if build["cores"] or build["rune_pages"]:
            lanes.setdefault(lane, build)
    return lanes


def parse_lane_stats(page: str) -> tuple[dict[str, dict], str | None]:
    """Every champion's Diamond+ win, pick and ban rate per lane, keyed by the site's champion slug.

    The table is embedded in the page's script payload as JSON entries."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', page, re.S)
    payload = "".join(chunks).encode().decode("unicode_escape", errors="ignore")
    stats: dict[str, dict] = {}
    for raw in re.findall(r'\{"slug":"[a-z0-9-]+","rank":\d+,"position":\d+,[^{}]*\}', payload):
        e = json.loads(raw)
        lane = POSITION_NUMBERS.get(e["position"])
        if e["rank"] != RANK or not lane:
            continue
        stats.setdefault(e["slug"], {})[lane] = {
            "win": e["winRate"],
            "pick": e["pickRate"],
            "ban": e["banRate"],
            "win_trend": e.get("winTrend", 0),
            "pick_trend": e.get("pickTrend", 0),
        }
    updated = re.search(r"Last updated:\s*(?:<!-- -->)?\s*(\d{4}-\d{2}-\d{2})", page)
    return stats, updated.group(1) if updated else None


def champion_url(slug: str) -> str:
    return f"{SITE}/champion/{slug}"
