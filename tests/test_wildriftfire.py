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
<div class="wf-champion__data__items data-block">
  <div class="section starting"><div class="name">Ruby Crystal</div></div>
  <div class="section core">
    <div class="name">Stridebreaker</div><div class="name">Sterak&#039;s Gage</div><div class="name">Black Cleaver</div>
  </div>
  <div class="section boots"><div class="name">Plated Steelcaps</div></div>
  <div class="section final"><div class="name">Plated Steelcaps</div><div class="name">Stridebreaker</div></div>
</div>
<div class="wf-champion__data__spells data-block">
  <img src="/images/summoners/flash.png" alt="Flash"><img src="/images/summoners/ghost.png" alt="Ghost">
  <img class="keystone" src="/images/runes/conqueror.png" alt="Conqueror">
  <img class="Resolve" src="/images/runes/second-wind.png" alt="Second Wind">
</div>
<div class="wf-champion__data__situational data-block">
  <span class="situation" name="situation">vs AP / CC</span>
  <div class="name">Plated Steelcaps</div><div class="name">Mercury&#039;s Treads</div>
  <span class="situation" name="situation">Only one item</span>
  <div class="name">Thornmail</div>
</div>
<div class="skills-counters-block"></div>
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
    }
    requested, icons = [], []

    def fake_get(url):
        requested.append(url)
        return pages[url.removeprefix(w.SITE)]

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
    assert all(url.startswith(w.SITE) for url in requested)


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
