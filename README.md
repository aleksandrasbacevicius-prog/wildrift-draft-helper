# Wild Rift Draft Helper

Champion-select helper for Wild Rift: standard builds, matchup tips, and an AI agent that adjusts the build to the enemy team.

```
Strands agent (Claude Haiku 4.5) ──MCP (stdio)──> MCP server ──> data/champions.json
```

- **`wildrift/data.py`**: data access, with no network calls and no LLM.
- **`wildrift/mcp_server.py`**: an MCP server exposing `list_champions`, `get_champion`, `get_build`, `get_matchup` and `get_items`. Any MCP client can use it, for example Claude Desktop.
- **`wildrift/agent.py`**: a Strands agent that calls those tools to tailor a build. Only this part costs API credits, and repeat drafts are served from a cache.

> **Data status:** `data/champions.json` is hand-curated starter data. The kit tips come from champion abilities. The builds are **placeholders**, not current server builds, and there are no win rates. Replace them with real data before relying on them.

## Setup

```powershell
py -3.11 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env   # then put your Anthropic API key in .env
```

## Run

```powershell
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m wildrift.agent Darius --enemies Garen Swain Irelia Fiora Mordekaiser
```

The first enemy listed is treated as your lane opponent.

To lock in your own core item choice, use `--swap OLD=NEW`. You can repeat it, and common nicknames work:

```powershell
.venv\Scripts\python -m wildrift.agent Darius --enemies Garen Swain --swap "Black Cleaver=triforce"
```

Swaps are checked locally before the agent runs, so a typo fails straight away and costs nothing. The swapped-out item moves to the situational list.

## Website

```powershell
.venv\Scripts\python -m uvicorn wildrift.api:app --reload
```

Open http://localhost:8000. The layout is phone-first: pick your champion and lane opponent, optionally tap up to 4 more enemies, tap a core item to swap it, then press **Tailor build with AI**. Only that button calls the model. Everything else is instant and free. API docs are at `/docs`.

**On your iPhone:** start the server with `--host 0.0.0.0`, then open `http://<your-PC's-IP>:8000` on the same Wi-Fi. Find the IP with `ipconfig`, and allow Python through the Windows firewall if asked.

Icons are Riot's PC League of Legends art from Data Dragon. They're already in `static/icons`. Re-download them with `python scripts/fetch_icons.py`.

## Roadmap

- Docker image
- GitHub Actions: run the tests and build the image
- AWS: ECS Fargate behind an ALB, plus a scheduled Lambda that refreshes the data
