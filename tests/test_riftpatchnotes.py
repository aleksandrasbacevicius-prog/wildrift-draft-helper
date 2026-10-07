"""RiftPatchNotes parser tests on small hand-written pages that mirror its HTML. No network."""

import json

from wildrift import riftpatchnotes as rpn
from wildrift import wildriftfire as w

CHAMPION_PAGE = """
<div data-form="Top"><section><h2>Darius Build Guide (<!-- -->Top<!-- -->)</h2>
<h4>Most popular core<!-- --> <span class="x">53.71% WR · 18.34% pick</span></h4>
<img src="/items/stridebreaker.png" alt="Stridebreaker"/><img src="/items/steraks-gage.png" alt="Sterak&#x27;s Gage"/>
<img src="/items/amaranths-twinguard.png" alt="Amaranth&#x27;s Twinguard"/>
<h4>Alternative core 1<!-- --> <span class="x">52.57% WR · 6.77% pick</span></h4>
<img alt="Stridebreaker"/><img alt="Experimental Hexplate"/><img alt="Sterak&#x27;s Gage"/>
<h4>Most popular boots<!-- --> <span class="x">48.75% WR · 84.05% pick</span></h4><img alt="Plated Steelcaps"/>
<p>Most popular page<!-- --> <span class="x">50.00% WR · 19.08% pick</span></p>
<img alt="Conqueror"/><img alt="Unshakeable"/><img alt="Second Wind"/><img alt="Perseverance"/><img alt="Nimbus Cloak"/>
<p class="t">Resolve<!-- --> primary · <!-- -->Sorcery<!-- --> secondary</p>
<p>Most popular summoners<!-- --> <span class="x">48.67% WR · 83.70% pick</span></p><img alt="Ghost"/><img alt="Flash"/>
<p>Win and pick rates from Diamond+ ranked games on the Wild Rift CN server, updated <!-- -->2026-10-04<!-- -->.</p>
</section></div>
<div data-form="Jungle" hidden=""><section>
<h4>Most popular core<!-- --> <span class="x">53.55% WR · 8.80% pick</span></h4>
<img alt="Trinity Force"/><img alt="The Collector"/><img alt="Galeforce"/>
</section></div>
"""


def winrates_page(entries):
    payload = json.dumps({"entries": entries}, separators=(",", ":")).replace('"', '\\"')
    return f'<p>Last updated: <!-- -->2026-10-05</p><script>self.__next_f.push([1,"{payload}"])</script>'


ENTRIES = [
    {"slug": "darius", "rank": 1, "position": 2, "winRate": 48.71, "pickRate": 15.46, "banRate": 12.78, "winTrend": -1},
    {"slug": "darius", "rank": 3, "position": 2, "winRate": 49.06, "pickRate": 10.6, "banRate": 5.71},
    {"slug": "darius", "rank": 1, "position": 5, "winRate": 50.18, "pickRate": 5.71, "banRate": 12.78},
    {"slug": "nunu-willump", "rank": 1, "position": 5, "winRate": 55.52, "pickRate": 5.39, "banRate": 6.58},
]


def test_parse_champion_builds_per_lane():
    builds = rpn.parse_champion_builds(CHAMPION_PAGE)
    assert list(builds) == ["baron", "jungle"]
    baron = builds["baron"]
    assert baron["cores"][0] == {
        "label": "Most popular core",
        "win": 53.71,
        "pick": 18.34,
        "items": ["Stridebreaker", "Sterak's Gage", "Amaranth's Twinguard"],
    }
    assert baron["cores"][1]["items"][1] == "Experimental Hexplate"
    assert baron["boots"] == [{"label": "Most popular boots", "win": 48.75, "pick": 84.05, "item": "Plated Steelcaps"}]
    page = baron["rune_pages"][0]
    assert page["runes"] == ["Conqueror", "Unshakeable", "Second Wind", "Perseverance", "Nimbus Cloak"]
    assert (page["primary"], page["secondary"], page["pick"]) == ("Resolve", "Sorcery", 19.08)
    assert baron["spells"][0]["spells"] == ["Ghost", "Flash"]
    assert baron["updated"] == "2026-10-04"
    assert builds["jungle"]["cores"][0]["items"] == ["Trinity Force", "The Collector", "Galeforce"]


def test_parse_champion_builds_single_lane_page():
    # One-lane champions have no lane tabs; the lane comes from the heading.
    page = """<h2>Ahri<!-- --> Build Guide <span class="t">(<!-- -->Mid<!-- -->)</span></h2>
    <h4>Most popular core<!-- --> <span class="x">53.00% WR · 31.38% pick</span></h4>
    <img alt="Luden&#x27;s Echo"/><img alt="Rabadon&#x27;s Deathcap"/><img alt="Void Staff"/>"""
    builds = rpn.parse_champion_builds(page)
    assert list(builds) == ["mid"]
    assert builds["mid"]["cores"][0]["items"][0] == "Luden's Echo"


def test_parse_champion_builds_empty_page():
    assert rpn.parse_champion_builds("<html>nothing</html>") == {}


def test_parse_lane_stats_keeps_diamond_plus_only():
    stats, updated = rpn.parse_lane_stats(winrates_page(ENTRIES))
    assert updated == "2026-10-05"
    assert stats["darius"]["baron"] == {"win": 48.71, "pick": 15.46, "ban": 12.78, "win_trend": -1, "pick_trend": 0}
    assert stats["darius"]["jungle"]["pick"] == 5.71  # position 5 = jungle
    assert stats["nunu-willump"]["jungle"]["win"] == 55.52


def test_add_server_data_offline(monkeypatch, tmp_path):
    sitemap = (
        "<loc>https://www.riftpatchnotes.com/champion/darius</loc>"
        "<loc>https://www.riftpatchnotes.com/champion/nunu-willump</loc>"
    )
    pages = {
        f"{rpn.SITE}/winrates": winrates_page(ENTRIES),
        f"{rpn.SITE}/sitemap-wr-entities.xml": sitemap,
        f"{rpn.SITE}/champion/darius": CHAMPION_PAGE,
        f"{rpn.SITE}/champion/nunu-willump": "<html>no builds yet</html>",
    }
    icons = []
    monkeypatch.setattr(w, "get", lambda url: pages[url])
    monkeypatch.setattr(w, "_download_icon", lambda url, path: icons.append(url))
    monkeypatch.setattr(w, "REQUEST_DELAY", 0)
    monkeypatch.setattr(w, "ICON_DIR", tmp_path)
    champions = {"Darius": {"name": "Darius"}, "Nunu & Willump": {"name": "Nunu & Willump"}, "Garen": {"name": "Garen"}}
    items = {"Stridebreaker": {}, "Sterak's Gage": {}, "Amaranth's Twinguard": {}, "Plated Steelcaps": {}}
    runes = {"Conqueror": {}, "Unshakeable": {}, "Second Wind": {}, "Nimbus Cloak": {}}
    meta = {}
    w.add_server_data(champions, items, runes, meta, log=lambda _: None)

    assert champions["Darius"]["server"]["builds"]["baron"]["cores"][0]["win"] == 53.71
    assert champions["Darius"]["server"]["stats"]["baron"]["pick"] == 15.46
    assert champions["Nunu & Willump"]["server"]["stats"]["jungle"]["win"] == 55.52  # names matched across sites
    assert champions["Garen"]["server"] == {"stats": {}, "builds": {}}  # no data: empty, not an error
    # Items and runes only the server lists are added, with icons, so they can be shown and saved.
    assert "Experimental Hexplate" in items and "Galeforce" in items
    assert runes["Perseverance"]["kind"] == "minor" and runes["Perseverance"]["tree"] == "Resolve"
    assert any(u.endswith("/items/experimental-hexplate.png") for u in icons)
    assert meta["server"] == {
        "source": rpn.SITE,
        "bracket": "Diamond+",
        "stats_updated": "2026-10-05",
        "builds_updated": "2026-10-04",
    }


def test_add_server_data_survives_site_down(monkeypatch):
    def down(url):
        raise OSError("down")

    monkeypatch.setattr(w, "get", down)
    champions = {"Darius": {"name": "Darius"}}
    meta = {}
    w.add_server_data(champions, {}, {}, meta, log=lambda _: None)
    assert "server" not in champions["Darius"] and "server" not in meta
