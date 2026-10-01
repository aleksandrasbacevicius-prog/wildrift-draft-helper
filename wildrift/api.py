"""REST API and website for the draft helper.

    uvicorn wildrift.api:app --reload                    # this computer only
    uvicorn wildrift.api:app --host 0.0.0.0 --port 8000  # reachable from your phone on the same Wi-Fi
"""

import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from wildrift import data, wildriftfire

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
CHECK_EVERY_SECONDS = 24 * 60 * 60

update_status = {"state": "idle", "message": ""}
_update_lock = threading.Lock()


def check_for_update(force: bool = False) -> None:
    """Refresh data from WildRiftFire if the patch changed (or data is old). Runs in a thread."""
    if not _update_lock.acquire(blocking=False):
        return  # already running
    try:
        update_status.update(state="checking", message="Checking for a new patch")
        stale, reason = wildriftfire.needs_refresh()
        if force or stale:
            update_status.update(state="updating", message=f"Updating: {reason}")
            wildriftfire.refresh(log=lambda m: update_status.update(message=m))
            data.reload()
            update_status.update(state="idle", message=f"Updated to patch {data.meta()['patch']}")
        else:
            update_status.update(state="idle", message=reason.capitalize())
    except Exception as e:
        update_status.update(state="error", message=f"Update failed: {e}")
    finally:
        _update_lock.release()


def _daily_checks() -> None:
    while True:
        check_for_update()
        time.sleep(CHECK_EVERY_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=_daily_checks, daemon=True).start()
    yield


app = FastAPI(title="Wild Rift Draft Helper", version="0.2.0", lifespan=lifespan)


def _no_data():
    raise HTTPException(status_code=503, detail="Champion data is still downloading. Try again in a few minutes.")


def _with_item_icons(build: dict) -> dict:
    def entry(name: str) -> dict:
        return {"name": name, "icon": data.item_icon(name)}

    return {
        **build,
        **{section: [entry(i) for i in build[section]] for section in ("starting", "core", "boots", "final")},
        "situational": [
            {"when": s["when"], "replace": entry(s["replace"]), "with": entry(s["with"])} for s in build["situational"]
        ],
    }


@app.get("/api/meta")
def get_meta() -> dict:
    try:
        meta = data.meta()
    except data.NoDataError:
        meta = {}
    return {**meta, "positions": data.POSITIONS, "update": update_status}


@app.post("/api/refresh", status_code=202)
def refresh() -> dict:
    threading.Thread(target=check_for_update, daemon=True).start()
    return {"update": update_status}


@app.get("/api/champions")
def list_champions(position: str | None = None) -> list[dict]:
    if position and position not in data.POSITIONS:
        raise HTTPException(status_code=400, detail=f"position must be one of {data.POSITIONS}")
    try:
        return data.list_champions(position)
    except data.NoDataError:
        _no_data()


@app.get("/api/champions/{name}/build")
def get_build(name: str) -> dict:
    try:
        return _with_item_icons(data.get_build(name))
    except data.UnknownChampionError as e:
        raise HTTPException(status_code=404, detail=e.args[0])
    except data.NoDataError:
        _no_data()


@app.get("/api/matchup")
def get_matchup(me: str, vs: str) -> dict:
    try:
        return data.get_matchup(me, vs)
    except data.UnknownChampionError as e:
        raise HTTPException(status_code=404, detail=e.args[0])
    except data.NoDataError:
        _no_data()


@app.get("/api/items")
def list_items() -> list[dict]:
    try:
        return sorted(data.get_items().values(), key=lambda i: i["name"])
    except data.NoDataError:
        _no_data()


@app.get("/api/profile")
def get_profile() -> dict:
    return data.get_profile()


@app.put("/api/profile")
def save_profile(profile: dict[str, list[str]]) -> dict:
    try:
        return data.save_profile(profile)
    except data.UnknownChampionError as e:
        raise HTTPException(status_code=404, detail=e.args[0])


class Swap(BaseModel):
    remove: str
    add: str


class TailorRequest(BaseModel):
    champion: str
    enemies: list[str] = Field(min_length=1, description="Lane opponent first")
    swaps: list[Swap] = []
    position: str | None = None


@app.post("/api/builds/tailor")
def tailor(request: TailorRequest) -> dict:
    # Plain `def` on purpose: the agent call blocks, so FastAPI runs it in a worker thread.
    from wildrift.agent import tailor_build  # imported lazily so the read-only endpoints work without the agent's deps

    try:
        result = tailor_build(
            request.champion, request.enemies, [(s.remove, s.add) for s in request.swaps], request.position
        )
    except (data.UnknownChampionError, data.UnknownItemError) as e:
        raise HTTPException(status_code=404, detail=e.args[0])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except data.NoDataError:
        _no_data()
    except RuntimeError as e:  # missing API key
        raise HTTPException(status_code=503, detail=str(e))
    return {"result": result}


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
