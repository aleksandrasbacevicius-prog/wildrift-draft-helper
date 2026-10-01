"""REST API and website for the draft helper.

    uvicorn wildrift.api:app --reload                 # this computer only
    uvicorn wildrift.api:app --host 0.0.0.0 --port 8000  # reachable from your phone on the same Wi-Fi
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from wildrift import data

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="Wild Rift Draft Helper", version="0.1.0")


def _icon(kind: str, filename: str) -> str | None:
    path = STATIC_DIR / "icons" / kind / filename
    return f"/icons/{kind}/{filename}" if path.exists() else None


def champion_icon(name: str) -> str | None:
    return _icon("champions", f"{name}.png")


def item_icon(name: str) -> str | None:
    return _icon("items", f"{data.icon_slug(name)}.png")


def _with_item_icons(build: dict) -> dict:
    def entry(name: str) -> dict:
        return {"name": name, "icon": item_icon(name)}

    return {
        **build,
        "core": [entry(i) for i in build["core"]],
        "boots": entry(build["boots"]),
        "situational": [entry(i) for i in build["situational"]],
    }


def _not_found(e: KeyError):
    raise HTTPException(status_code=404, detail=e.args[0])


@app.get("/api/champions")
def list_champions() -> list[dict]:
    return [
        {"name": c["name"], "damage": c["damage"], "class": c["class"], "icon": champion_icon(c["name"])}
        for c in (data.get_champion(n) for n in data.list_champions())
    ]


@app.get("/api/champions/{name}/build")
def get_build(name: str) -> dict:
    try:
        return _with_item_icons(data.get_build(name))
    except data.UnknownChampionError as e:
        _not_found(e)


@app.get("/api/matchup")
def get_matchup(me: str, vs: str) -> dict:
    try:
        return data.get_matchup(me, vs)
    except data.UnknownChampionError as e:
        _not_found(e)


@app.get("/api/items")
def list_items() -> list[dict]:
    return [{"name": n, "tags": tags, "icon": item_icon(n)} for n, tags in data.get_items().items()]


class Swap(BaseModel):
    remove: str
    add: str


class TailorRequest(BaseModel):
    champion: str
    enemies: list[str] = Field(min_length=1, description="Lane opponent first")
    swaps: list[Swap] = []


@app.post("/api/builds/tailor")
def tailor(request: TailorRequest) -> dict:
    # Plain `def` on purpose: the agent call blocks, so FastAPI runs it in a worker thread.
    from wildrift.agent import tailor_build  # imported lazily so the read-only endpoints work without the agent's deps

    try:
        result = tailor_build(request.champion, request.enemies, [(s.remove, s.add) for s in request.swaps])
    except (data.UnknownChampionError, data.UnknownItemError) as e:
        _not_found(e)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:  # missing API key
        raise HTTPException(status_code=503, detail=str(e))
    return {"result": result}


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
