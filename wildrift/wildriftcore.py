"""Builds, matchups and tier lists from WildRiftCore.com (patch-current, CN server based).

- Per champion and lane: three build variants (standard, anti-tank, sustain...) with when to pick them,
  boots, a rune page, situational items with their condition, and "adaptations by opponent":
  the hardest matchups with the item that answers each one.
- Per champion and lane: every opponent rated by their edge over the champion (-2..+2), with the
  interaction that decides the matchup and how to play it.
- Per lane: the tier list.

Its robots.txt allows crawlers (ClaudeBot included). Used for a private, non-commercial tool for a few
friends; requests are spaced out like the other fetchers'.
"""

import html
import re

SITE = "https://wildriftcore.com"
ROLES = {"TOP": "baron", "JUNGLE": "jungle", "MID": "mid", "ADC": "dragon", "SUPPORT": "support"}
TIER_PAGES = {
    "baron": "baron-lane",
    "jungle": "jungle",
    "mid": "mid-lane",
    "dragon": "dragon-lane",
    "support": "support",
}
LANE_TITLES = {"baron lane": "baron", "top": "baron", "jungle": "jungle", "mid lane": "mid", "mid": "mid"}
LANE_TITLES |= {"dragon lane": "dragon", "adc": "dragon", "support": "support"}


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _alts(fragment: str) -> list[str]:
    return [html.unescape(a).strip() for a in re.findall(r'<img[^>]*\balt="([^"]+)"', fragment)]


def champion_url(slug: str, page: str = "builds") -> str:
    return f"{SITE}/en/champions/{slug}/{page}/"


def tier_url(position: str) -> str:
    return f"{SITE}/en/tierlist/{TIER_PAGES[position]}/"


def parse_patch(page: str) -> str | None:
    found = re.search(r"Patch (\d+\.\d+[a-z]?)", page)
    return found.group(1) if found else None


def parse_tier_list(page: str) -> dict[str, dict]:
    """Champion name -> {"slug", "tier", "win", "pick", "ban"} for one lane."""
    tiers = {}
    for m in re.finditer(
        r'<a href="/en/champions/([a-z0-9-]+)/" class="tl-champ-tile" title="([^"]+)".*?'
        r'class="tl-champ-badge">([^<]+)<.*?tl-champ-wr">([\d.]+)% WR.*?tl-champ-pr">([\d.]+)% PR'
        r'.*?tl-champ-br">([\d.]+)% BR',
        page,
        re.S,
    ):
        slug_, name, tier, win, pick, ban = m.groups()
        tiers[html.unescape(name).strip()] = {
            "slug": slug_,
            "tier": tier.strip(),
            "win": float(win),
            "pick": float(pick),
            "ban": float(ban),
        }
    return tiers


def _lane_sections(page: str, default_lane: str | None = None) -> list[tuple[str, str]]:
    """Split a builds page into (lane, section) pairs using the "<Champion> <Lane> — recommended build" titles.
    Champions with one lane have no titles: then the whole build section is for `default_lane`."""
    parts = re.split(r'<h3 class="eb-role-title">(.*?)</h3>', page, flags=re.S)
    if len(parts) == 1:
        start = page.find('data-section="engine-builds"')
        return [(default_lane, page[start:])] if default_lane and start >= 0 else []
    sections = []
    for title, body in zip(parts[1::2], parts[2::2], strict=True):
        title = _text(title).lower()
        lane = next((pos for name, pos in LANE_TITLES.items() if f" {name} " in f" {title} "), None)
        if lane:
            sections.append((lane, body))
    return sections


def parse_builds(page: str, default_lane: str | None = None) -> dict[str, dict]:
    """Per lane: build variants, boots, runes, situational items and adaptations by opponent.
    `default_lane` is used for single-lane champions, whose page doesn't name the lane."""
    lanes = {}
    for lane, body in _lane_sections(page, default_lane):
        variants = []
        for m in re.finditer(
            r'<article class="engine-builds__variant"[^>]*data-variant-key="([^"]+)"[^>]*>(.*?)</article>', body, re.S
        ):
            key, block = m.groups()
            name = re.search(r"<h[34][^>]*>(.*?)</h[34]>", block, re.S)
            desc = re.search(r'<p class="eb-variant-desc">(.*?)</p>', block, re.S)
            items_block = re.search(r'<div class="eb-items".*?</div>\s*(?:<div|<span class="nx-count")', block, re.S)
            when = re.search(r'<span class="eb-chip[^"]*">(.*?)</span>', block, re.S)
            variants.append(
                {
                    "key": key,
                    "name": _text(name.group(1)) if name else key,
                    "description": _text(desc.group(1)) if desc else "",
                    "items": [
                        html.unescape(n).strip()
                        for n in re.findall(
                            r'<a class="eb-item"[^>]*>.*?<span>([^<]+)</span>',
                            items_block.group(0) if items_block else block,
                            re.S,
                        )
                    ],
                    "when": _text(when.group(1)) if when else "",
                }
            )
        shared = re.search(r'data-nx-section="eb_runes">(.*?)<h3', body, re.S)
        shared = shared.group(1) if shared else ""
        boots = re.search(r"<strong>Recommended boots</strong><em>(.*?)</em>", shared, re.S)
        rune_block = re.search(r'<div class="eb-sit eb-sit--runes">(.*?)</div>\s*</div>', shared, re.S)
        reason = re.search(r'<em class="eb-rune-reason">(.*?)</em>', shared, re.S)
        situational = [
            {"item": html.unescape(item).strip(), "when": _text(when)}
            for item, when in re.findall(
                r'<div class="eb-sit" data-item="[^"]+"[^>]*>.*?<strong>(.*?)</strong><em>(.*?)</em>',
                _between(body, 'data-nx-section="eb_situational"', "<h3"),
                re.S,
            )
        ]
        vs = [
            {"foe": html.unescape(foe).strip(), "why": _text(why), "item": html.unescape(item).strip()}
            for foe, why, item in re.findall(
                r'<a class="eb-vs__foe".*?<b>(.*?)</b>.*?<em class="eb-vs__why">(.*?)</em>.*?'
                r'<a class="eb-item"[^>]*>.*?<span>([^<]+)</span>',
                _between(body, 'data-nx-section="eb_vs"', '<h3 class="eb-role-title"'),
                re.S,
            )
        ]
        if variants:
            lanes.setdefault(
                lane,
                {
                    "variants": variants,
                    "boots": _text(boots.group(1)) if boots else None,
                    "runes": _alts(rune_block.group(1)) if rune_block else [],
                    "rune_reason": _text(reason.group(1)) if reason else "",
                    "situational": situational,
                    "vs": vs,
                },
            )
    return lanes


def _between(page: str, start: str, end: str) -> str:
    i = page.find(start)
    if i < 0:
        return ""
    j = page.find(end, i + len(start))
    return page[i : j if j > 0 else len(page)]


GROUP_NAMES = {"hard": "hard", "unfavorable": "unfavorable", "skillMatchups": "skill", "favorable": "favorable"}


def parse_matchups(page: str) -> dict[str, dict]:
    """Per lane, every opponent rated against this champion: lane -> opponent name -> card.

    "edge" is the opponent's edge over this champion (-2..+2): positive means they counter it.
    "key" and "how" are advice for playing this champion into them."""
    lanes: dict[str, dict] = {}
    for m in re.finditer(
        r'<details class="nx-counter-fold" id="mu-([A-Z]+)-[a-z0-9-]+"[^>]*>(.*?)</details>', page, re.S
    ):
        role, card = m.groups()
        lane = ROLES.get(role)
        name = re.search(r'class="nx-counter-name">([^<]+)</a>', card)
        edge = re.search(r'class="nx-counter-edge"[^>]*>([−\-+±]?\d+)</span>', card)
        if not lane or not name or not edge:
            continue
        group = re.search(r'data-idx="(\w+?)-\d+"', m.group(0))
        block = {k: _text(v) for k, v in re.findall(r'data-k="(\w+)"><h3>.*?</h3><p>(.*?)</p>', card, re.S)}
        lanes.setdefault(lane, {})[html.unescape(name.group(1)).strip()] = {
            "edge": int(edge.group(1).replace("−", "-").replace("±", "")),
            "group": GROUP_NAMES.get(group.group(1), group.group(1)) if group else None,
            "tags": [_text(t) for t in re.findall(r'<span class="nx-counter-tag">(.*?)</span>', card, re.S)],
            "key": block.get("key", ""),
            "how": block.get("adapt", ""),
        }
    return lanes
