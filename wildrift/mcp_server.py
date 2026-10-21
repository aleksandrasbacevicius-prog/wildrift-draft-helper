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
def get_build(name: str, position: str | None = None, enemy: str | None = None) -> dict:
    """Get the champion's build for a lane (baron, jungle, mid, dragon, support) this patch, adjusted for the
    lane opponent when `enemy` is given: core items, boots, full build, runes, summoner spells, situational
    items, "matchup" (the rule used and each change with its reason) and "options" (ranked alternatives per
    slot with a reason, e.g. a server pick rate or "Against AP burst")."""
    build = _safe(data.get_build, name, position, enemy)
    if "error" in build:
        return build
    keep = ("name", "position", "core", "boots", "final", "runes", "spells", "situational", "situational_items")
    return {
        **{k: build[k] for k in keep},
        "matchup": build["matchup"],
        "options": {
            slot: [[f"{o['name']} ({o['why']})" for o in opts] for opts in lists]
            if slot != "boots"
            else [f"{o['name']} ({o['why']})" for o in lists]
            for slot, lists in build["options"].items()
        },
        "server_stats": build["server_stats"],
    }


@server.tool()
def get_matchup(my_champion: str, enemy: str, position: str | None = None) -> dict:
    """Get lane matchup info: whether either champion counters the other, the enemy's tiers, strengths,
    weaknesses, how to play against them, damage type and whether they heal.
    "card" is WildRiftCore's rating of this exact pairing when available: the enemy's edge over you (-2..+2),
    the interaction that decides it and how to play it."""
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
