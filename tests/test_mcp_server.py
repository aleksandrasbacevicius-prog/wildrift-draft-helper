"""The MCP tools are plain functions underneath, so they can be tested directly."""

from wildrift import mcp_server as mcp


def test_list_champions_by_position():
    champions = mcp.list_champions("baron")
    assert champions and all("baron" in c["tiers"] for c in champions)
    assert set(champions[0]) == {"name", "tiers"}


def test_get_build_and_champion():
    assert mcp.get_build("Darius")["core"]
    assert mcp.get_champion("darius")["name"] == "Darius"


def test_errors_come_back_as_data_not_exceptions():
    assert "error" in mcp.get_build("Nobody")
    assert "error" in mcp.get_matchup("Darius", "Nobody")
    assert "error" in mcp.swap_core_item("Darius", "Not In Core", "triforce")


def test_swap_core_item():
    core = mcp.get_build("Darius")["core"]
    assert mcp.swap_core_item("Darius", core[0], "triforce")["core"][0] == "Trinity Force"


def test_get_items_and_runes():
    assert "Plated Steelcaps" in mcp.get_items("Boots")
    keystones = mcp.get_runes("keystone")
    assert keystones and all(r["kind"] == "keystone" for r in keystones)
    assert len(mcp.get_runes()) > len(keystones)


def test_matchup_has_tips_flag():
    assert mcp.get_matchup("Darius", "Garen")["has_tips"] is True
