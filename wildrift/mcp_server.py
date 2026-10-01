"""MCP server exposing Wild Rift draft data as tools. Runs over stdio.

Any MCP client can use it: the Strands agent in this repo, Claude Desktop, etc.
"""

from mcp.server import MCPServer

from wildrift import data

server = MCPServer(
    name="wildrift-draft",
    instructions="Wild Rift champion, build and matchup data. Builds are placeholders unless marked verified.",
)


def _safe(fn, *args):
    try:
        return fn(*args)
    except (data.UnknownChampionError, data.UnknownItemError, ValueError) as e:
        return {"error": e.args[0]}


@server.tool()
def list_champions() -> list[str]:
    """List the champions this dataset covers."""
    return data.list_champions()


@server.tool()
def get_champion(name: str) -> dict:
    """Get a champion's role, damage type, class, strengths, weaknesses and tips for playing against them."""
    return _safe(data.get_champion, name)


@server.tool()
def get_build(name: str) -> dict:
    """Get the standard (server) build for a champion: core items, boots and situational items.
    Check the 'verified' field. False means it is a placeholder."""
    return _safe(data.get_build, name)


@server.tool()
def get_matchup(my_champion: str, enemy: str) -> dict:
    """Get lane matchup info: your strengths, the enemy's strengths and weaknesses,
    how to play against them, their damage type and whether they heal."""
    return _safe(data.get_matchup, my_champion, enemy)


@server.tool()
def swap_core_item(champion: str, remove: str, add: str) -> dict:
    """Return the champion's build with one core item replaced by another, e.g.
    remove='Black Cleaver', add='Trinity Force'. Accepts nicknames like 'triforce'.
    The removed item moves to the situational list."""
    return _safe(data.swap_core_item, champion, remove, add)


@server.tool()
def get_items(tag: str | None = None) -> dict[str, list[str]]:
    """List items and their tags. Filter by a tag such as 'armor', 'magic_resist',
    'grievous_wounds', 'tenacity' or 'anti_tank'. Omit the tag to get all items."""
    return data.get_items(tag)


if __name__ == "__main__":
    server.run()
