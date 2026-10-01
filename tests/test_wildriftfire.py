"""Fetcher tests on small hand-written pages that mirror WildRiftFire's HTML. No network."""

import json
from datetime import date, timedelta

import pytest

from wildrift import wildriftfire as w

TIER_LIST = """
<span class="patch">Patch 7.3a</span>
<div class="wf-tier-list__tiers__main">
  <div class="tier splus">
    <a href="/guide/darius" class="ico-holder" data-role="Solo" data-id="1">
      <div class="item-holder"> <img src="https://www.mobafire.com/images/champion/square/darius.png" alt="Darius"></div>
      <span>Darius</span></a>
  </div>
  <div class="tier a">
    <a href="/guide/darius" class="ico-holder" data-role="Jungle" data-id="1">
      <div class="item-holder"><img src="https://www.mobafire.com/images/champion/square/darius.png"></div>
      <span>Darius</span></a>
    <a href="/guide/chogath" class="ico-holder" data-role="Support" data-id="2">
      <div class="item-holder"><img src="/images/champion/icon/chogath.png"></div>
      <span>Cho&#039;Gath</span></a>
  </div>
</div>
<div class="wf-tier-list__tiers__sidebar"></div>
"""

GUIDE = """
<div class="wf-champion__guide-selector">
  <span class="active" data-guide-id="40"> <img src="/images/lanes/white-solo.png"> Solo Build </span>
  <span data-guide-id="280"> <img src="/images/lanes/white-jungle.png"> Jungle Build </span>
</div>
<div class="wf-champion__data__items data-block" data-guide-id="40">
  <div class="section starting"><div class="name">Ruby Crystal</div></div>
  <div class="section core">
    <div class="name">Stridebreaker</div><div class="name">Sterak&#039;s Gage</div><div class="name">Black Cleaver</div>
  </div>
  <div class="section boots"><div class="name">Plated Steelcaps</div></div>
  <div class="section final"><div class="name">Plated Steelcaps</div><div class="name">Stridebreaker</div></div>
</div>
<div class="wf-champion__data__spells data-block" data-guide-id="40">
  <img src="/images/summoners/flash.png" alt="Flash"><img src="/images/summoners/ghost.png" alt="Ghost">
  <img class="keystone" src="/images/runes/conqueror.png" alt="Conqueror">
  <img class="Resolve" src="/images/runes/second-wind.png" alt="Second Wind">
</div>
<div class="wf-champion__data__situational  data-block" data-guide-id="40">
  <span class="situation" name="situation">vs AP / CC</span>
  <div class="name">Plated Steelcaps</div><div class="name">Mercury&#039;s Treads</div>
  <span class="situation" name="situation">Only one item</span>
  <div class="name">Thornmail</div>
</div>
<div class="skills-counters-block data-block " data-guide-id="40">
  <div class="data-mod counters-mod counters">
    <div class="ico-holder"><img class="lane" src="/images/lanes/white-solo.png"> <span>Dr. Mundo</span></div>
    <div class="ico-holder"><img class="lane" src="/images/lanes/white-solo.png"> <span>Malphite</span></div>
  </div>
  <div class="data-mod counters-mod synergies">
    <div class="ico-holder"><img class="lane" src="/images/lanes/white-jungle.png"> <span>Lillia</span></div>
    <div class="ico-holder"><img class="lane" src="/images/lanes/white-support.png"> <span>Thresh</span></div>
  </div>
</div>
<div class="wf-champion__data__items data-block inactive" data-guide-id="280">
  <div class="section core"><div class="name">Trinity Force</div><div class="name">Sterak&#039;s Gage</div></div>
  <div class="section boots"><div class="name">Plated Steelcaps</div></div>
</div>
<div class="wf-champion__data__spells data-block inactive" data-guide-id="280">
  <img src="/images/summoners/smite.png" alt="Smite">
  <img class="keystone" src="/images/runes/phase-rush.png" alt="Phase Rush">
</div>
<div class="skills-counters-block data-block  inactive" data-guide-id="280">
  <div class="data-mod counters-mod counters">
    <div class="ico-holder"><img class="lane" src="/images/lanes/white-jungle.png"> <span>Vi</span></div>
  </div>
</div>
"""

ITEM_LIST = """
<div class="wf-tier-list__tiers__main">
  <div class="ico-holder ajax-tooltip { t:'Item',i:75 }" data-sort="Fighter" data-id="75">
    <img src="/images/items/stridebreaker.png"> <span>Stridebreaker</span></div>
  <div class="ico-holder ajax-tooltip { t:'Item',i:76 }" data-sort="Assassin,Fighter" data-id="76">
    <img src="/images/items/steraks-gage.png"> <span>Sterak&#039;s Gage</span></div>
  <div class="ico-holder ajax-tooltip { t:'Item',i:77 }" data-sort="Boots" data-id="77">
    <img src="/images/items/plated-steelcaps.png"> <span>Plated Steelcaps</span></div>
</div>
"""

RUNE_LIST = """
<div class="wf-tier-list__tiers__main">
  <div class="tier s">
    <div class="ico-holder ajax-tooltip { t:'Rune',i:69 }" data-sort=" Keystone" data-id="69"><span>Conqueror</span></div>
    <div class="ico-holder ajax-tooltip { t:'Rune',i:96 }" data-sort="Resolve Minor" data-id="96"><span>Second Wind</span></div>
  </div>
  <div class="tier b">
    <div class="ico-holder ajax-tooltip { t:'Rune',i:3 }" data-sort="Sorcery Minor" data-id="3"><span>Nimbus Cloak</span></div>
  </div>
</div>
<div class="wf-tier-list__tiers__sidebar"></div>
"""


WRMETA_ITEMS = """
<div class="bild-img-short"><p>
  <b class="iname">Stridebreaker</b><br><b class="cdr">Slows enemies nearby after a short dash</b><br><br>
  <b class="istats"><i><img src="hp.png"></i> +400 Max Health</b><br>
  <b class="istats"><i><img src="ad.png"></i> +40 Attack Damage</b><br><br>
  <b class="istats2">Breaking Shockwave (Active):</b> Dash, dealing <i>100% AD</i> damage<br>
  <i><img src="Gold_icon.png"></i> <b class="goldt">3100</b> <br>
  <b class="cdr">Stridebreaker TIPS:</b> Good for fighters. </p></div>
<div class="bild-img-short"><p><b class="iname">Sterak&#039;s Gage</b><br><b class="cdr">Shield when low</b></p></div>
"""


def test_slug():
    assert w.slug("Sterak's Gage") == "steraks-gage"
    assert w.slug("Nunu & Willump") == "nunu-willump"
    assert w.slug("Dr. Mundo") == "dr-mundo"


@pytest.mark.parametrize(
    "page, patch",
    [
        ("Patch 7.3a", "7.3a"),
        ("patch 6.1d ... Patch 7.2 ... Patch 7.10", "7.10"),  # newest wins, compared as numbers
        ("Patch 7.3 and Patch 7.3b", "7.3b"),
        ("no patch here", None),
    ],
)
def test_parse_patch(page, patch):
    assert w.parse_patch(page) == patch


def test_parse_tier_list_positions_and_icons():
    champions = w.parse_tier_list(TIER_LIST)
    assert champions["Darius"]["positions"] == {"baron": "S+", "jungle": "A"}
    assert champions["Cho'Gath"]["positions"] == {"support": "A"}
    assert champions["Cho'Gath"]["icon_url"] == "https://www.wildriftfire.com/images/champion/icon/chogath.png"


def test_parse_guide():
    build = w.parse_guide(GUIDE)
    assert build["starting"] == ["Ruby Crystal"]
    assert build["core"] == ["Stridebreaker", "Sterak's Gage", "Black Cleaver"]
    assert build["boots"] == ["Plated Steelcaps"]
    assert build["final"] == ["Plated Steelcaps", "Stridebreaker"]
    assert build["situational"] == [{"when": "vs AP / CC", "replace": "Plated Steelcaps", "with": "Mercury's Treads"}]
    assert build["spells"] == ["Flash", "Ghost"]
    assert build["runes"] == ["Conqueror", "Second Wind"]


def test_parse_guides_per_lane():
    builds = w.parse_guides(GUIDE)
    assert list(builds) == ["baron", "jungle"]  # recommended lane first
    assert builds["baron"]["countered_by"] == [
        {"name": "Dr. Mundo", "position": "baron"},
        {"name": "Malphite", "position": "baron"},
    ]
    assert builds["baron"]["synergies"] == [
        {"name": "Lillia", "position": "jungle"},
        {"name": "Thresh", "position": "support"},
    ]
    assert builds["jungle"]["core"] == ["Trinity Force", "Sterak's Gage"]
    assert builds["jungle"]["spells"] == ["Smite"] and builds["jungle"]["runes"] == ["Phase Rush"]
    assert builds["jungle"]["countered_by"] == [{"name": "Vi", "position": "jungle"}]
    assert builds["jungle"]["situational"] == []


def test_parse_guide_missing_sections():
    build = w.parse_guide("<html>nothing useful</html>")
    assert build["core"] == [] and build["situational"] == [] and build["runes"] == []


def test_parse_item_list():
    items = w.parse_item_list(ITEM_LIST)
    assert items["Sterak's Gage"]["categories"] == ["Assassin", "Fighter"]
    assert items["Plated Steelcaps"]["icon_url"].endswith("/images/items/plated-steelcaps.png")


def test_parse_rune_list():
    runes = w.parse_rune_list(RUNE_LIST)
    assert runes["Conqueror"] == {
        "name": "Conqueror",
        "kind": "keystone",
        "tree": "Keystone",
        "tier": "S",
        "icon": "/icons/wrf/runes/conqueror.png",
    }
    assert runes["Second Wind"]["kind"] == "minor" and runes["Second Wind"]["tree"] == "Resolve"
    assert runes["Nimbus Cloak"]["tier"] == "B"


@pytest.fixture
def offline_site(tmp_path, monkeypatch):
    """Serve the sample pages instead of the network, and write into a temp folder."""
    pages = {
        "/tier-list": TIER_LIST,
        "/item-list": ITEM_LIST,
        "/rune-list": RUNE_LIST,
        "/guide/darius": GUIDE,
        "/guide/chogath": "<html>broken page</html>",
        w.ITEM_DETAILS_URL: WRMETA_ITEMS,
    }
    requested, icons = [], []

    def fake_get(url):
        requested.append(url)
        return pages[url] if url in pages else pages[url.removeprefix(w.SITE)]

    def fake_icon(url, path):
        icons.append((url, path))

    monkeypatch.setattr(w, "get", fake_get)
    monkeypatch.setattr(w, "_download_icon", fake_icon)
    monkeypatch.setattr(w, "REQUEST_DELAY", 0)
    monkeypatch.setattr(w, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(w, "ICON_DIR", tmp_path / "icons")
    return requested, icons, tmp_path / "data"


def test_refresh_end_to_end(offline_site):
    requested, icons, data_dir = offline_site
    meta = w.refresh(log=lambda _: None)
    assert meta["patch"] == "7.3a"
    champions = json.loads((data_dir / "champions.json").read_text(encoding="utf-8"))
    items = json.loads((data_dir / "items.json").read_text(encoding="utf-8"))
    runes = json.loads((data_dir / "runes.json").read_text(encoding="utf-8"))
    assert champions["Darius"]["build"]["core"][0] == "Stridebreaker"
    assert champions["Darius"]["icon"] == "/icons/wrf/champions/darius.png"
    assert "Ruby Crystal" in items  # build items missing from the item list are added
    assert "Black Cleaver" in items
    assert set(runes) == {"Conqueror", "Second Wind", "Nimbus Cloak"}
    downloaded = {str(path.relative_to(path.parents[1])).replace("\\", "/") for _, path in icons}
    assert {"champions/darius.png", "items/ruby-crystal.png", "runes/conqueror.png", "spells/flash.png"} <= downloaded
    assert {"lanes/baron.png", "lanes/dragon.png"} <= downloaded
    assert all(url.startswith((w.SITE, w.ITEM_DETAILS_URL)) for url in requested)
    assert items["Stridebreaker"]["details"]["gold"] == 3100
    assert items["Sterak's Gage"]["details"]["summary"] == "Shield when low"


def test_parse_item_details():
    details = w.parse_item_details(WRMETA_ITEMS)
    assert details["stridebreaker"] == {
        "summary": "Slows enemies nearby after a short dash",
        "stats": ["+400 Max Health", "+40 Attack Damage"],
        "effects": [{"name": "Breaking Shockwave (Active)", "text": "Dash, dealing 100% AD damage"}],
        "gold": 3100,
        "tip": "Good for fighters.",
    }
    assert "steraksgage" in details  # names are matched without punctuation


def test_item_details_are_optional(offline_site, monkeypatch):
    def fail(url):
        raise OSError("WR-META is down")

    monkeypatch.setattr(w, "get", fail)
    items = {"Stridebreaker": {"name": "Stridebreaker"}}
    logs = []
    w.add_item_details(items, log=logs.append)
    assert "details" not in items["Stridebreaker"] and "unavailable" in logs[0]


def test_refresh_survives_a_broken_guide_page(offline_site):
    _, _, data_dir = offline_site
    logs = []
    w.refresh(log=logs.append)
    champions = json.loads((data_dir / "champions.json").read_text(encoding="utf-8"))
    assert champions["Cho'Gath"]["build"] is None  # marked unavailable, not an empty build
    assert champions["Darius"]["build"]["core"]  # the rest still refreshed
    assert any("Cho'Gath: build failed" in line for line in logs)


def test_needs_refresh_when_no_data(offline_site):
    assert w.needs_refresh() == (True, "no data yet")


def test_needs_refresh_on_new_patch(offline_site):
    _, _, data_dir = offline_site
    data_dir.mkdir(parents=True)
    (data_dir / "meta.json").write_text(json.dumps({"patch": "7.2", "fetched": date.today().isoformat()}))
    stale, reason = w.needs_refresh()
    assert stale and "7.3a" in reason


def test_needs_refresh_when_old(offline_site):
    _, _, data_dir = offline_site
    data_dir.mkdir(parents=True)
    old = (date.today() - timedelta(days=w.MAX_AGE_DAYS)).isoformat()
    (data_dir / "meta.json").write_text(json.dumps({"patch": "7.3a", "fetched": old}))
    assert w.needs_refresh()[0] is True


def test_up_to_date(offline_site):
    _, _, data_dir = offline_site
    data_dir.mkdir(parents=True)
    (data_dir / "meta.json").write_text(json.dumps({"patch": "7.3a", "fetched": date.today().isoformat()}))
    assert w.needs_refresh() == (False, f"up to date (patch 7.3a, fetched {date.today().isoformat()})")


class FakeResponse:
    def __init__(self, body: bytes, content_type="image/png", url="https://www.wildriftfire.com/x.png"):
        self.body, self.content_type, self.url = body, content_type, url
        self.headers = self

    def get_content_type(self):
        return self.content_type

    def geturl(self):
        return self.url

    def read(self, n=-1):
        return self.body if n < 0 else self.body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_open_rejects_oversized_and_redirected(monkeypatch):
    monkeypatch.setattr(w.urllib.request, "urlopen", lambda *a, **k: FakeResponse(b"x" * 2000))
    with pytest.raises(ValueError, match="larger than"):
        w._open("https://www.wildriftfire.com/big.png", 1000)
    monkeypatch.setattr(w.urllib.request, "urlopen", lambda *a, **k: FakeResponse(b"ok", url="https://evil.example/x"))
    with pytest.raises(ValueError, match="redirected"):
        w._open("https://www.wildriftfire.com/x.png", 1000)


def test_download_icon_only_saves_images(tmp_path, monkeypatch):
    monkeypatch.setattr(w.time, "sleep", lambda _: None)
    monkeypatch.setattr(w.urllib.request, "urlopen", lambda *a, **k: FakeResponse(b"<html>", content_type="text/html"))
    with pytest.raises(ValueError, match="not an image"):
        w._download_icon("https://www.wildriftfire.com/x.png", tmp_path / "x.png")
    monkeypatch.setattr(w.urllib.request, "urlopen", lambda *a, **k: FakeResponse(b"\x89PNG"))
    w._download_icon("https://www.wildriftfire.com/x.png", tmp_path / "icons" / "x.png")
    assert (tmp_path / "icons" / "x.png").read_bytes() == b"\x89PNG"
