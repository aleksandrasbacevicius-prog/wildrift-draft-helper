# Wild Rift Draft Helper

Champion-select helper for Wild Rift. Pick your lane, your champion and your opponent, and see the current core build, full build, runes, situational swaps and the tier list. Pick your champion with counterpicks in mind ("Strong against [opponent]"), see who counters whom and who pairs well with you, and press and hold any item for its stats. Server stats from real Diamond+ ranked games let you switch to the most popular item core or rune page this patch in one tap, and the opponent list starts with the champions you're most likely to face in your lane. Builds follow the lane you play. Swap core items and runes, and your choices are saved per champion and lane. An AI agent can then tailor the build to the enemy team.

```
Website ── FastAPI ──> data layer ──> WildRiftFire data (refreshed when the patch changes)
                  └──> Strands agent (Claude Haiku 4.5) ──MCP──> MCP server ──> data layer
```

- **`wildrift/wildriftfire.py`**: downloads the tier list, every champion's builds per lane (with counters and synergies), the item and rune lists, icons and the patch number from [WildRiftFire.com](https://www.wildriftfire.com), plus item stats and descriptions from [WR-META](https://wr-meta.com/items/), and Diamond+ server builds and lane win/pick/ban rates from [RiftPatchNotes](https://www.riftpatchnotes.com) (`wildrift/riftpatchnotes.py`). It only reads public pages that robots.txt allows, one per second.
- **`wildrift/data.py`**: data access with no LLM calls. Covers champions by position and tier, builds, items, core swaps and your champion pool.
- **`wildrift/mcp_server.py`**: an MCP server exposing the data as 9 tools. Any MCP client can use it, for example Claude Desktop.
- **`wildrift/agent.py`**: a Strands agent that calls those tools to tailor a build. Only this part costs API credits, and repeat drafts are cached.
- **`wildrift/api.py`** and **`static/index.html`**: a REST API and a phone-first website.
- **`data/tips.json`**: hand-written matchup tips (currently for 8 Baron champions).
- **`data/profile.default.json`**: the default champion pool per position. Edit it in the app with "Edit my pool". Each person's pool is saved to `data/profiles/<name>.json`, and their item and rune choices to `data/builds/<name>.json`.

## Setup

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
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

## Counter data

Counters are combined from two independent sources for each lane:

- **WildRiftFire**: 3 "countered by" picks per lane on each champion guide.
- **WR-META**: the free "Extreme threats" list per lane on each champion page. Its premium-locked lists aren't used.

Each source ranks its picks (1st = 1.0, 2nd = 0.9, ...), and a champion's score is the **average across the sources that rate that lane**. A champion both sites name ranks above one only a single site names, and the app marks those "both sites". Tencent's Chinese server stats were considered, but its CDN's robots.txt blocks AI crawlers, so they're not used.

## Server builds and common opponents

RiftPatchNotes publishes per-lane stats from Diamond+ ranked games on the CN server (the only region with official ranked stats): the most popular item core plus two alternatives, boots, rune pages and summoner spells, each with a win and pick rate. The build card shows them as choices next to the WildRiftFire guide build. The opponent list puts the lane's most picked champions first ("Most common this patch"), and the matchup card shows both champions' lane win, pick and ban rates. These are overall lane stats, not head-to-head results: no free source that allows crawling publishes per-matchup win rates.

## Security

- **Access tokens, one per person** (`APP_TOKENS` in `.env`, generate with `python -m wildrift.tokens alex sam`). They're needed for the AI button, saving your pool and patch checks. Browsing builds and tiers stays open. With no tokens set, those actions only work from this computer.
- **AI limit:** 5 custom builds per person per 48h, plus a total of 30 across everyone, to protect the API credit. Repeat drafts come from the cache and are free. The agent is also capped at 8 tool calls per request.
- **Input limits:** names, list lengths and request sizes are capped, and there's a per-person rate limit.
- **Browser hardening:** a strict Content-Security-Policy (no inline scripts), plus nosniff, no-referrer and no framing.
- **Data fetcher:** only HTTPS requests to WildRiftFire/MobaFire, with size limits, and only images are saved as icons.
- Also set a monthly spend limit in the Anthropic Console as the final backstop.

## Deploy to Render

1. Create tokens for everyone: `python -m wildrift.tokens alex sam jonas`.
2. On [render.com](https://render.com), choose **New > Blueprint** and pick this GitHub repo. `render.yaml` sets up a free Docker web service.
3. When asked, fill in `ANTHROPIC_API_KEY` and `APP_TOKENS` (the `APP_TOKENS=...` line without the prefix).
4. The build downloads the current patch's data into the image, which takes about 5 minutes. Then share the `onrender.com` link, and send each friend their own token privately.

Free tier notes: the service sleeps after 15 minutes idle and takes about 30 seconds to wake. Its disk is temporary, so pools and AI usage counters reset when it restarts or redeploys, while the Anthropic Console spend limit still applies.

## Patch updates

The data is stamped with the patch it came from, which the site shows at the top. While the server runs, it checks WildRiftFire once a day. If the patch has changed, or the data is a week old, it downloads everything again. You can also press "Check for a new patch" in the footer, or run `python -m wildrift.wildriftfire`.

Downloaded data and icons are not committed to git (`data/wildriftfire/`, `static/icons/wrf/`). Tests use a small sample in `tests/fixtures/`.

## Tests

```powershell
pip install -r requirements-dev.txt
python -m playwright install chromium   # once, for the browser tests
```

| Command | What it runs |
|---|---|
| `python -m pytest --cov=wildrift` | Unit and API tests with coverage (fails under 90%). The AI model and the network are faked, so this is free and offline. |
| `python -m pytest -m e2e` | Browser tests at iPhone size: lanes, item and rune swaps, saved builds, the token prompt asking only once |
| `ruff check . && ruff format --check .` | Lint and formatting |
| `pip-audit -r requirements.txt` | Known vulnerabilities in dependencies |

GitHub Actions runs all of these on every push, plus a Docker build (`.github/workflows/ci.yml`).

## Roadmap

- AWS: ECS Fargate behind an ALB, plus a scheduled Lambda for the patch check
- Persistent storage for pools and usage counters (e.g. a small database)

Builds, tiers and counters from WildRiftFire.com; item details from WR-META.com; server stats from RiftPatchNotes.com. Fan project, not endorsed by Riot Games.
