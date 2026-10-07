"""MCP server exposing Wild Rift draft data as tools. Runs over stdio.

Any MCP client can use it: the Strands agent in this repo, Claude Desktop, etc.
"""

from mcp.server import MCPServer

from wildrift import data

server = MCPServer(
    name="wildrift-draft",
    instructions="Wild Rift tier list, builds and items for the current patch (from WildRiftFire.com), plus matchup tips.",
)


def _safe(fn, *args):
    try:
        return fn(*args)
    except (data.UnknownChampionError, data.UnknownItemError, ValueError) as e:
        return {"error": e.args[0]}


@server.tool()
def list_champions(position: str | None = None) -> list[dict]:
    """List champions with their tier (S+ best, then S, A, B, C) per position.
    Position is one of baron, jungle, mid, dragon, support. Omit it to list everyone."""
    return [{"name": c["name"], "tiers": c["positions"]} for c in data.list_champions(position)]


@server.tool()
def get_champion(name: str) -> dict:
    """Get a champion's tier per position and, where available, strengths, weaknesses and tips for playing against them."""
    return _safe(data.get_champion, name)


@server.tool()
def get_build(name: str, position: str | None = None) -> dict:
    """Get the champion's current build for a lane (baron, jungle, mid, dragon, support): starting item,
    core items, boots, final build, situational swaps (e.g. 'vs Healing: replace X with Y'), summoner
    spells, runes, and who counters them / synergises with them in that lane."""
    return _safe(data.get_build, name, position)


@server.tool()
def get_matchup(my_champion: str, enemy: str, position: str | None = None) -> dict:
    """Get lane matchup info: whether either champion counters the other, the enemy's tiers, strengths,
    weaknesses, how to play against them, damage type and whether they heal.
    Hand-written tips exist only for some champions (see has_tips)."""
    return _safe(data.get_matchup, my_champion, enemy, position)


@server.tool()
def get_common_opponents(position: str) -> list[dict]:
    """The most common opponents in a lane this patch: champions with the highest Diamond+ pick rate on the CN
    server, with their win, pick and ban rates (percent). Position: baron, jungle, mid, dragon or support."""
    return [
        {"name": c["name"], "win": c["win"], "pick": c["pick"], "ban": c["ban"]}
        for c in data.common_opponents(position)
    ]


@server.tool()
def get_counters(champion: str, position: str | None = None) -> list[dict] | dict:
    """List champions that are strong against (counter) this champion in a lane, best tier first."""
    try:
        data.get_champion(champion)
    except data.UnknownChampionError as e:
        return {"error": e.args[0]}
    return [{"name": c["name"], "tiers": c["positions"]} for c in data.strong_against(champion, position)]


@server.tool()
def swap_core_item(champion: str, remove: str, add: str) -> dict:
    """Return the champion's build with one core item replaced by another, e.g.
    remove='Stridebreaker', add='Trinity Force'. Accepts nicknames like 'triforce'."""
    return _safe(data.swap_core_item, champion, remove, add)


@server.tool()
def get_runes(tree: str | None = None) -> list[dict]:
    """List runes with kind (keystone or minor), tree and tier (S best). Filter by tree:
    Keystone, Domination, Precision, Resolve or Sorcery."""
    runes = data.get_runes().values()
    return [r for r in runes if tree is None or r["tree"].lower() == tree.lower()]


@server.tool()
def get_items(category: str | None = None) -> list[str]:
    """List item names. Filter by category: Fighter, Assassin, Marksman, Magic, Defense,
    Support, Boots or Physical. Omit the category to list all items."""
    return list(data.get_items(category))


if __name__ == "__main__":
    server.run()
