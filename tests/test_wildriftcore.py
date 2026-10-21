"""WildRiftCore parser and fetch tests on small hand-written pages that mirror its HTML. No network."""

import json

from wildrift import wildriftcore as wrc
from wildrift import wildriftfire as w

BUILDS_PAGE = """
<h3 class="eb-role-title">Darius Baron Lane — recommended build</h3>
<div class="engine-builds__grid">
<article class="engine-builds__variant" data-variant="0" data-variant-key="standard">
 <h4>Standard — bruiser</h4><p class="eb-variant-desc">Sample description.</p>
 <div class="eb-items" data-nx-glide="-14">
  <a class="eb-item" data-item="a"><img alt="Stridebreaker"><span>Stridebreaker</span></a><span class="eb-arrow">›</span>
  <a class="eb-item" data-item="b"><img alt="Sterak&#x27;s Gage"><span>Sterak&#x27;s Gage</span></a>
 </div>
 <div class="eb-cost"><span class="nx-count">6,000</span></div>
 <span class="eb-eyebrow">When to pick it</span><span class="eb-chip eb-chip--neutral">No strong signal</span>
</article>
<article class="engine-builds__variant" data-variant="1" data-variant-key="anti-tank">
 <h4>Anti-tank — shred</h4><p class="eb-variant-desc">Sample.</p>
 <div class="eb-items"><a class="eb-item"><span>Black Cleaver</span></a></div>
 <span class="nx-count">3,000</span><span class="eb-chip">2+ enemy tanks</span>
</article>
</div>
<div class="engine-builds__shared-block" data-nx-section="eb_runes">
 <div class="eb-sit"><img alt="Plated Steelcaps"><div><strong>Recommended boots</strong><em>Plated Steelcaps</em></div></div>
 <div class="eb-sit eb-sit--runes"><img alt="Conqueror"><div><strong>Recommended runes: Conqueror</strong>
  <em class="eb-rune-reason">Sample reason.</em><span class="eb-sit__minors"><img alt="Demolish"><img alt="Second Wind"></span></div></div>
</div>
<h3 class="engine-builds__sit-title">Situational adaptations</h3>
<div class="engine-builds__sits" data-nx-section="eb_situational">
 <div class="eb-sit" data-item="wits-end" role="button"><img alt="Wit's End"><div><strong>Wit&#x27;s End</strong><em>Against AP burst (Syndra…)</em></div></div>
</div>
<h3 class="engine-builds__sit-title">Adaptations by opponent</h3>
<div class="eb-vs" data-nx-section="eb_vs">
 <div class="eb-vs__row"><a class="eb-vs__foe" href="/en/champions/kennen/counters/"><img alt="">
  <span class="eb-vs__name"><span class="eb-vs__title"><b>Kennen</b></span><em class="eb-vs__why">Magic damage</em></span></a>
  <a class="eb-item" data-item="wits-end"><img alt="Wit's End"><span>Wit&#x27;s End</span></a></div>
</div>
<h3 class="eb-role-title">Darius Jungle — recommended build</h3>
<article class="engine-builds__variant" data-variant-key="standard"><h4>Standard</h4>
 <div class="eb-items"><a class="eb-item"><span>Trinity Force</span></a></div><span class="nx-count">1</span></article>
"""

COUNTERS_PAGE = """
<details class="nx-counter-fold" id="mu-TOP-vayne" data-idx="hard-0"><summary>
 <h3><a href="/en/champions/vayne/" class="nx-counter-name">Vayne</a><span class="nx-counter-edge" data-sign="pos">+2</span></h3>
 <span class="nx-counter-tags"><span class="nx-counter-tag">Range</span></span></summary>
 <section class="nx-counter-detail-block" data-k="key"><h3>The interaction that decides it</h3><p>Sample key.</p></section>
 <section class="nx-counter-detail-block" data-k="adapt"><h3>How to play</h3><p>Sample how.</p></section>
</details>
<details class="nx-counter-fold" id="mu-TOP-garen" data-idx="skillMatchups-0"><summary>
 <h3><a href="/en/champions/garen/" class="nx-counter-name">Garen</a><span class="nx-counter-edge" data-sign="even">±0</span></h3></summary>
</details>
<details class="nx-counter-fold" id="mu-JUNGLE-kayle" data-idx="favorable-0"><summary>
 <h3><a class="nx-counter-name">Kayle</a><span class="nx-counter-edge" data-sign="neg">−2</span></h3></summary>
</details>
"""

TIER_PAGE = """<p>Patch 7.3b — Best Top Lane Champions</p>
<a href="/en/champions/darius/" class="tl-champ-tile" title="Darius" data-reason="x"><div><img alt="Darius">
 <span class="tl-champ-badge">A</span></div><span class="tl-champ-name">Darius</span>
 <span class="tl-champ-stats"><span class="tl-champ-wr">49.8% WR</span><span class="tl-champ-pr">14.4% PR</span>
 <span class="tl-champ-br">13.0% BR</span></span></a>
"""


def test_parse_builds_per_lane():
    builds = wrc.parse_builds(BUILDS_PAGE)
    assert list(builds) == ["baron", "jungle"]
    baron = builds["baron"]
    assert [v["key"] for v in baron["variants"]] == ["standard", "anti-tank"]
    assert baron["variants"][0]["items"] == ["Stridebreaker", "Sterak's Gage"]
    assert baron["variants"][0]["when"] == "No strong signal"
    assert baron["variants"][1]["when"] == "2+ enemy tanks"
    assert baron["boots"] == "Plated Steelcaps"
    assert baron["runes"] == ["Conqueror", "Demolish", "Second Wind"]
    assert baron["situational"] == [{"item": "Wit's End", "when": "Against AP burst (Syndra…)"}]
    assert baron["vs"] == [{"foe": "Kennen", "why": "Magic damage", "item": "Wit's End"}]
    assert builds["jungle"]["variants"][0]["items"] == ["Trinity Force"]


def test_parse_matchups_with_signed_and_even_edges():
    cards = wrc.parse_matchups(COUNTERS_PAGE)
    assert cards["baron"]["Vayne"] == {
        "edge": 2,
        "group": "hard",
        "tags": ["Range"],
        "key": "Sample key.",
        "how": "Sample how.",
    }
    assert cards["baron"]["Garen"]["edge"] == 0 and cards["baron"]["Garen"]["group"] == "skill"
    assert cards["jungle"]["Kayle"]["edge"] == -2


def test_parse_tier_list_and_patch():
    assert wrc.parse_tier_list(TIER_PAGE)["Darius"] == {
        "slug": "darius",
        "tier": "A",
        "win": 49.8,
        "pick": 14.4,
        "ban": 13.0,
    }
    assert wrc.parse_patch(TIER_PAGE) == "7.3b"


def test_empty_pages_give_nothing():
    assert wrc.parse_builds("<html></html>") == {}
    assert wrc.parse_matchups("<html></html>") == {}


def test_add_wildriftcore_data_offline(monkeypatch, tmp_path):
    pages = {wrc.tier_url(pos): TIER_PAGE if pos == "baron" else "<p></p>" for pos in wrc.TIER_PAGES}
    pages[wrc.champion_url("darius", "builds")] = BUILDS_PAGE
    pages[wrc.champion_url("darius", "counters")] = COUNTERS_PAGE
    monkeypatch.setattr(w, "get", lambda url: pages[url])
    monkeypatch.setattr(w, "_download_icon", lambda url, path: None)
    monkeypatch.setattr(w, "REQUEST_DELAY", 0)
    monkeypatch.setattr(w, "ICON_DIR", tmp_path)
    champions = {
        "Darius": {"name": "Darius", "positions": {"jungle": "B"}},
        "Garen": {"name": "Garen", "positions": {}},
    }
    items = {"Stridebreaker": {}, "Sterak's Gage": {}, "Plated Steelcaps": {}, "Black Cleaver": {}, "Trinity Force": {}}
    meta = {}
    w.add_wildriftcore_data(champions, items, meta, log=lambda _: None)
    darius = champions["Darius"]
    assert darius["positions"] == {"baron": "A"}  # WildRiftCore's tier list replaces the old lanes
    assert darius["wrc"]["builds"]["baron"]["vs"][0]["item"] == "Wit's End"
    assert darius["wrc"]["matchups"]["baron"]["Vayne"]["edge"] == 2
    assert "wrc" not in champions["Garen"]  # not in their tier lists
    assert "Wit's End" in items  # new item added
    assert meta["wildriftcore"]["patch"] == "7.3b" and meta["wildriftcore"]["champions"] == 1


def test_add_wildriftcore_data_survives_site_down(monkeypatch):
    def down(url):
        raise OSError("down")

    monkeypatch.setattr(w, "get", down)
    monkeypatch.setattr(w, "REQUEST_DELAY", 0)
    champions = {"Darius": {"name": "Darius", "positions": {"baron": "A"}}}
    meta = {}
    w.add_wildriftcore_data(champions, {}, meta, log=lambda _: None)
    assert champions["Darius"]["positions"] == {"baron": "A"} and "wildriftcore" not in meta


def test_add_profiles_offline(monkeypatch):
    roster = {
        "data": {
            "Ahri": {"name": "Ahri", "tags": ["Mage", "Assassin"], "info": {"attack": 3, "magic": 8}},
            "DrMundo": {"name": "Dr. Mundo", "tags": ["Tank", "Fighter"], "info": {"attack": 5, "magic": 6}},
            "Darius": {"name": "Darius", "tags": ["Fighter", "Tank"], "info": {"attack": 9, "magic": 1}},
        }
    }
    pages = {
        f"{w.DDRAGON}/api/versions.json": json.dumps(["1.0"]),
        f"{w.DDRAGON}/cdn/1.0/data/en_US/champion.json": json.dumps(roster),
    }
    monkeypatch.setattr(w, "get", lambda url: pages[url])
    champions = {n: {"name": n} for n in ("Ahri", "Dr. Mundo", "Darius", "Nobody")}
    w.add_profiles(champions, log=lambda _: None)
    assert champions["Ahri"]["profile"] == {"damage": "magic", "tags": ["mage", "assassin"]}
    assert champions["Dr. Mundo"]["profile"]["damage"] == "mixed"  # a little magic doesn't make a mage
    assert champions["Darius"]["profile"]["damage"] == "physical"
    assert "profile" not in champions["Nobody"]


def test_combine_all_counters_uses_positive_edges():
    champions = {
        "Darius": {
            "name": "Darius",
            "builds": {"baron": {"countered_by": [{"name": "Garen"}]}},
            "wrc": {"matchups": {"baron": {"Vayne": {"edge": 2}, "Garen": {"edge": 1}, "Kayle": {"edge": -2}}}},
            "wrmeta_counters": {"baron": ["vayne"]},
        },
        "Garen": {"name": "Garen"},
        "Vayne": {"name": "Vayne"},
        "Kayle": {"name": "Kayle"},
    }
    w.combine_all_counters(champions)
    counters = {c["name"]: c for c in champions["Darius"]["counters"]["baron"]}
    assert set(counters) == {"Vayne", "Garen"}  # Kayle has no edge over Darius
    assert counters["Vayne"]["sources"] == ["WildRiftCore", "WR-META"]


SINGLE_LANE_PAGE = """
<section class="engine-builds" data-section="engine-builds">
<article class="engine-builds__variant" data-variant-key="standard"><h3>Standard — AP burst</h3>
 <div class="eb-items"><a class="eb-item"><span>Luden&#x27;s Echo</span></a></div><span class="nx-count">1</span></article>
<div data-nx-section="eb_runes"><div class="eb-sit eb-sit--runes"><img alt="Electrocute"><div><strong>Recommended runes</strong>
 <span class="eb-sit__minors"><img alt="Giant Slayer"></span></div></div></div><h3 class="engine-builds__sit-title">x</h3>
</section>
"""


def test_single_lane_page_uses_the_default_lane():
    builds = wrc.parse_builds(SINGLE_LANE_PAGE, "mid")
    assert list(builds) == ["mid"]
    assert builds["mid"]["variants"][0]["name"] == "Standard — AP burst"
    assert builds["mid"]["variants"][0]["items"] == ["Luden's Echo"]
    assert wrc.parse_builds(SINGLE_LANE_PAGE) == {}  # no lane known: nothing to file it under


def test_new_runes_are_added_to_the_rune_list(monkeypatch, tmp_path):
    pages = {
        wrc.tier_url(pos): TIER_PAGE.replace("Darius", "Ahri").replace("darius", "ahri") if pos == "mid" else "<p></p>"
        for pos in wrc.TIER_PAGES
    }
    pages[wrc.champion_url("ahri", "builds")] = SINGLE_LANE_PAGE.replace(
        '<img alt="Giant Slayer">', '<img src="/assets/images/runes-local/giant.webp" alt="Giant Slayer">'
    )
    pages[wrc.champion_url("ahri", "counters")] = ""
    monkeypatch.setattr(w, "get", lambda url: pages[url])
    monkeypatch.setattr(w, "_download_icon", lambda url, path: None)
    monkeypatch.setattr(w, "REQUEST_DELAY", 0)
    monkeypatch.setattr(w, "ICON_DIR", tmp_path)
    champions = {"Ahri": {"name": "Ahri", "positions": {}}}
    runes = {"Electrocute": {"kind": "keystone"}}
    w.add_wildriftcore_data(champions, {"Luden's Echo": {}}, {}, log=lambda _: None, runes=runes)
    assert champions["Ahri"]["wrc"]["builds"]["mid"]["runes"] == ["Electrocute", "Giant Slayer"]
    assert runes["Giant Slayer"]["kind"] == "minor" and runes["Giant Slayer"]["icon"].endswith("giant-slayer.webp")


def test_item_spellings_are_unified():
    items = {"Lord Dominik's Regard": {}, "Sterak's Gage": {}}
    assert w._item_alias("Lord Dominik's Regards", items) == "Lord Dominik's Regard"
    assert w._item_alias("steraks gage", items) == "Sterak's Gage"
    assert w._item_alias("Unknown Item", items) is None
