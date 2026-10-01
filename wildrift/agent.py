"""Strands agent that tailors a build to the enemy team, using the MCP server's tools.

Usage:
    python -m wildrift.agent Darius --enemies Garen Swain Irelia Fiora Mordekaiser
    python -m wildrift.agent Darius --enemies Garen Swain --swap "Stridebreaker=triforce"
"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from strands import Agent
from strands.models.anthropic import AnthropicModel
from strands.tools.mcp import MCPClient

from wildrift import data

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODEL_ID = "claude-haiku-4-5"  # cheapest current model; this task doesn't need more

SYSTEM_PROMPT = """You help a Wild Rift player adjust their build during champion select.

Use the tools to fetch the player's current build for this patch and the enemy champions' info.
The build includes situational swaps (e.g. "vs Healing: replace X with Y"). Decide which of them
apply to this enemy team, and whether anything else should change. Consider damage types
(mostly AD vs AP), healing (anti-heal), crowd control (tenacity) and tankiness.

Rules:
- Keep the core items unless there's a strong reason. The core is the priority.
- Only recommend items that appear in get_items. Don't invent items.
- Matchup tips only exist for some champions. Without them, reason from general knowledge and say so.
- Keep it short: final build in order, then at most 4 one-line reasons for any changes,
  then 2-3 lane tips against the enemy laner (the first enemy listed)."""

_cache: dict[tuple, str] = {}


def _mcp_client() -> MCPClient:
    [client] = MCPClient.load_servers(
        {
            "wildrift": {
                "command": sys.executable,
                "args": ["-m", "wildrift.mcp_server"],
                "cwd": str(PROJECT_ROOT),
            }
        }
    )
    return client


def tailor_build(
    my_champion: str, enemies: list[str], swaps: list[tuple[str, str]] | None = None, position: str | None = None
) -> str:
    """Return a tailored build. Repeat requests for the same draft are served from cache.

    swaps: (remove, add) core-item swaps the player has locked in, e.g. [("Black Cleaver", "triforce")].
    They are validated locally first, so a bad item name fails before any API call.
    """
    swaps = swaps or []
    for name in [my_champion, *enemies]:
        data.get_champion(name)  # fail fast on unknown names, before any API call
    locked_build = data.apply_swaps(my_champion, swaps) if swaps else None

    key = (
        data.meta()["patch"],
        position or "",
        my_champion.lower(),
        enemies[0].lower() if enemies else "",
        tuple(sorted(e.lower() for e in enemies)),
        tuple(locked_build["core"]) if locked_build else (),
    )
    if key in _cache:
        return _cache[key]

    load_dotenv(PROJECT_ROOT / ".env")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Add it to .env in the project root.")

    model = AnthropicModel(model_id=MODEL_ID, max_tokens=1024)
    role = f" in the {position} position" if position else ""
    prompt = (
        f"I'm playing {my_champion}{role}. Enemy team: {', '.join(enemies)}. "
        f"My lane opponent is {enemies[0]}." if enemies else f"I'm playing {my_champion}{role}."
    )
    if locked_build:
        changes = "; ".join(
            f"I replaced {data.resolve_item(old)} with {data.resolve_item(new)}" for old, new in swaps
        )
        prompt += (
            f"\n{changes}. My build is now: {json.dumps(locked_build)}. "
            "Keep my chosen core items. Don't call get_build. Tailor the boots and remaining "
            "slots around this, and say briefly if my swap is a poor fit for this enemy team."
        )
    with _mcp_client() as mcp:
        agent = Agent(
            model=model,
            tools=mcp.list_tools_sync(),
            system_prompt=SYSTEM_PROMPT,
            callback_handler=None,
        )
        result = str(agent(prompt))

    _cache[key] = result
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Tailor a Wild Rift build to the enemy team.")
    parser.add_argument("champion")
    parser.add_argument("--enemies", nargs="+", required=True, help="Enemy champions, lane opponent first")
    parser.add_argument("--position", choices=data.POSITIONS)
    parser.add_argument(
        "--swap",
        action="append",
        default=[],
        metavar="OLD=NEW",
        help='Swap a core item, e.g. --swap "Stridebreaker=triforce". Repeatable.',
    )
    args = parser.parse_args()

    swaps = []
    for pair in args.swap:
        if "=" not in pair:
            parser.error(f'--swap needs OLD=NEW, got "{pair}"')
        old, new = pair.split("=", 1)
        swaps.append((old, new))

    try:
        print(tailor_build(args.champion, args.enemies, swaps, args.position))
    except (data.UnknownChampionError, data.UnknownItemError, data.NoDataError, ValueError) as e:
        sys.exit(f"Error: {e.args[0]}")


if __name__ == "__main__":
    main()
