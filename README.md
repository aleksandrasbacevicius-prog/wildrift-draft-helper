# Wild Rift Draft Helper

Champion-select helper for Wild Rift. Pick your lane, your champion and your opponent, and see the current core build, full build, situational swaps and the tier list. An AI agent can then tailor the build to the enemy team.

```
Website ── FastAPI ──> data layer ──> WildRiftFire data (refreshed when the patch changes)
                  └──> Strands agent (Claude Haiku 4.5) ──MCP──> MCP server ──> data layer
```

- **`wildrift/wildriftfire.py`**: downloads the tier list, every champion's build, the item list, icons and the patch number from [WildRiftFire.com](https://www.wildriftfire.com). It only reads public pages that robots.txt allows, one per second.
- **`wildrift/data.py`**: data access with no LLM calls. Covers champions by position and tier, builds, items, core swaps and your champion pool.
- **`wildrift/mcp_server.py`**: an MCP server exposing the data as tools. Any MCP client can use it, for example Claude Desktop.
- **`wildrift/agent.py`**: a Strands agent that calls those tools to tailor a build. Only this part costs API credits, and repeat drafts are cached.
- **`wildrift/api.py`** and **`static/index.html`**: a REST API and a phone-first website.
- **`data/tips.json`**: hand-written matchup tips (currently for 8 Baron champions).
- **`data/profile.default.json`**: the default champion pool per position. Edit it in the app with "Edit my pool". Your changes are saved to `data/profile.json`.

## Setup

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # then put your Anthropic API key in .env
python -m wildrift.wildriftfire   # first download, about 3-4 minutes
```

## Run

```powershell
python -m uvicorn wildrift.api:app --reload
```

Open http://localhost:8000. To use it on your iPhone, start it with `--host 0.0.0.0 --port 8000` and open `http://<your-PC's-IP>:8000` on the same Wi-Fi.

From the command line:

```powershell
python -m wildrift.agent Darius --position baron --enemies Garen Ahri --swap "Stridebreaker=triforce"
```

## Patch updates

The data is stamped with the patch it came from, which the site shows at the top. While the server runs, it checks WildRiftFire once a day. If the patch has changed, or the data is a week old, it downloads everything again. You can also press "Check for a new patch" in the footer, or run `python -m wildrift.wildriftfire`.

Downloaded data and icons are not committed to git (`data/wildriftfire/`, `static/icons/wrf/`). Tests use a small sample in `tests/fixtures/`.

## Tests

```powershell
python -m pytest -q
```

## Roadmap

- Docker image
- GitHub Actions: run the tests and build the image
- AWS: ECS Fargate behind an ALB, plus a scheduled Lambda for the patch check

Builds and tier list from WildRiftFire.com. Fan project, not endorsed by Riot Games.
