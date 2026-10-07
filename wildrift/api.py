"""REST API and website for the draft helper.

uvicorn wildrift.api:app --reload                    # this computer only
uvicorn wildrift.api:app --host 0.0.0.0 --port 8000  # reachable from your phone on the same Wi-Fi
"""

import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StringConstraints

from wildrift import data, wildriftfire
from wildrift.security import ai_usage, identify, require_access, write_rate_limit

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
CHECK_EVERY_SECONDS = 24 * 60 * 60
# Wait a while after starting before the first check, so waking up stays fast. That first check only
# refreshes for a new patch: the image already has recent data, and on a free host a full download
# right after every wake-up would slow the app down and be lost again when it sleeps.
STARTUP_CHECK_DELAY_SECONDS = 5 * 60
MAX_BODY_BYTES = 16 * 1024
REFRESH_COOLDOWN_SECONDS = 15 * 60
protected = [Depends(write_rate_limit)]  # valid token (or this computer) + per-user rate limit
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]

update_status = {"state": "idle", "message": ""}
_update_lock = threading.Lock()


def check_for_update(force: bool = False, check_age: bool = True) -> None:
    """Refresh data from WildRiftFire if the patch changed (or data is old). Runs in a thread."""
    if not _update_lock.acquire(blocking=False):
        return  # already running
    try:
        update_status.update(state="checking", message="Checking for a new patch")
        stale, reason = wildriftfire.needs_refresh(check_age=check_age)
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
    time.sleep(STARTUP_CHECK_DELAY_SECONDS)
    check_for_update(check_age=False)
    while True:
        time.sleep(CHECK_EVERY_SECONDS)
        check_for_update()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("WILDRIFT_AUTO_UPDATE", "1") != "0":  # tests and CI turn this off
        threading.Thread(target=_daily_checks, daemon=True).start()
    yield


app = FastAPI(title="Wild Rift Draft Helper", version="0.3.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)  # the item list alone is ~100 KB uncompressed

# Content Security Policy: only this site's own scripts, styles and images.
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
        return JSONResponse(status_code=413, content={"detail": "Request body too large."})
    response = await call_next(request)
    for header, value in SECURITY_HEADERS.items():
        # FastAPI's /docs page loads Swagger UI from a CDN, so it gets every header except the CSP.
        if header == "Content-Security-Policy" and request.url.path in ("/docs", "/redoc"):
            continue
        response.headers.setdefault(header, value)
    return response


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
        "runes": [{"name": r, "icon": data.rune_icon(r)} for r in build["runes"]],
        "spells": [{"name": s, "icon": data.spell_icon(s)} for s in build["spells"]],
        "server": _with_server_icons(build.get("server") or {}),
    }


def _with_server_icons(server: dict) -> dict:
    """The server build options with an icon for every item, rune and spell."""
    if not server:
        return {}

    def item(name):
        return {"name": name, "icon": data.item_icon(name)}

    return {
        **server,
        "cores": [{**c, "items": [item(i) for i in c["items"]]} for c in server.get("cores", [])],
        "boots": [{**b, "item": item(b["item"])} for b in server.get("boots", []) if b.get("item")],
        "rune_pages": [
            {**p, "runes": [{"name": r, "icon": data.rune_icon(r)} for r in p["runes"]]}
            for p in server.get("rune_pages", [])
        ],
        "spells": [
            {**s, "spells": [{"name": x, "icon": data.spell_icon(x)} for x in s["spells"]]}
            for s in server.get("spells", [])
        ],
    }


@app.get("/api/meta")
def get_meta() -> dict:
    try:
        meta = data.meta()
    except data.NoDataError:
        meta = {}
    return {**meta, "positions": data.POSITIONS, "update": update_status}


@app.get("/api/usage")
def get_usage(user: str = Depends(require_access)) -> dict:
    return ai_usage.status(user)


# Never refreshed yet. Not 0.0: on Linux the monotonic clock starts near 0 at boot, so a freshly started
# server or CI machine would otherwise look like it refreshed moments ago.
_last_manual_refresh = float("-inf")


@app.post("/api/refresh", status_code=202, dependencies=protected)
def refresh() -> dict:
    global _last_manual_refresh
    if time.monotonic() - _last_manual_refresh < REFRESH_COOLDOWN_SECONDS:
        raise HTTPException(status_code=429, detail="A patch check ran recently. Try again later.")
    _last_manual_refresh = time.monotonic()
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


Position = Annotated[str | None, Query(pattern="^(baron|jungle|mid|dragon|support)$")]


@app.get("/api/champions/{name}/build")
def get_build(name: str, position: Position = None) -> dict:
    """The build for that lane, or the champion's recommended lane if they have no separate build for it."""
    try:
        return _with_item_icons(data.get_build(name, position))
    except data.UnknownChampionError as e:
        raise HTTPException(status_code=404, detail=e.args[0]) from e
    except data.NoDataError:
        _no_data()


@app.get("/api/matchup")
def get_matchup(me: str, vs: str, position: Position = None) -> dict:
    try:
        return data.get_matchup(me, vs, position)
    except data.UnknownChampionError as e:
        raise HTTPException(status_code=404, detail=e.args[0]) from e
    except data.NoDataError:
        _no_data()


@app.get("/api/items")
def list_items() -> list[dict]:
    try:
        return sorted(data.get_items().values(), key=lambda i: i["name"])
    except data.NoDataError:
        _no_data()


@app.get("/api/runes")
def list_runes() -> list[dict]:
    try:
        return sorted(data.get_runes().values(), key=lambda r: (r["kind"] != "keystone", r["tree"], r["name"]))
    except data.NoDataError:
        _no_data()


class Preferences(BaseModel):
    core: list[Name] = Field(min_length=1, max_length=6)
    runes: list[Name] = Field(min_length=1, max_length=8)


@app.get("/api/common-opponents")
def common_opponents(position: Position = None) -> list[dict]:
    """Who you're most likely to face in a lane this patch (highest Diamond+ pick rate first)."""
    if not position:
        raise HTTPException(status_code=422, detail="position is required")
    try:
        return data.common_opponents(position)
    except data.NoDataError:
        _no_data()


@app.get("/api/counters/{champion}")
def get_counters(champion: str, position: Position = None) -> list[dict]:
    """Champions that are strong against this one in that lane (counterpicks)."""
    try:
        data.get_champion(champion)
        return data.strong_against(champion, position)
    except data.UnknownChampionError as e:
        raise HTTPException(status_code=404, detail=e.args[0]) from e
    except data.NoDataError:
        _no_data()


@app.get("/api/preferences/{champion}")
def get_preferences(champion: str, request: Request, position: Position = None) -> dict:
    try:
        return {"saved": data.get_preferences(identify(request), champion, position)}
    except data.UnknownChampionError as e:
        raise HTTPException(status_code=404, detail=e.args[0]) from e


@app.put("/api/preferences/{champion}")
def save_preferences(
    champion: str, body: Preferences, position: Position = None, user: str = Depends(write_rate_limit)
) -> dict:
    try:
        return {"saved": data.save_preferences(user, champion, body.core, body.runes, position)}
    except (data.UnknownChampionError, data.UnknownItemError, data.UnknownRuneError) as e:
        raise HTTPException(status_code=404, detail=e.args[0]) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.delete("/api/preferences/{champion}")
def reset_preferences(champion: str, position: Position = None, user: str = Depends(write_rate_limit)) -> dict:
    try:
        data.reset_preferences(user, champion, position)
    except data.UnknownChampionError as e:
        raise HTTPException(status_code=404, detail=e.args[0]) from e
    return {"saved": None}


@app.get("/api/profile")
def get_profile(request: Request) -> dict:
    return data.get_profile(identify(request))


class Profile(BaseModel):
    baron: list[Name] = Field(default=[], max_length=40)
    jungle: list[Name] = Field(default=[], max_length=40)
    mid: list[Name] = Field(default=[], max_length=40)
    dragon: list[Name] = Field(default=[], max_length=40)
    support: list[Name] = Field(default=[], max_length=40)


@app.put("/api/profile")
def save_profile(body: Profile, user: str = Depends(write_rate_limit)) -> dict:
    return data.save_profile(user, body.model_dump())


class Swap(BaseModel):
    remove: Name
    add: Name


class TailorRequest(BaseModel):
    champion: Name
    enemies: list[Name] = Field(min_length=1, max_length=5, description="Lane opponent first")
    swaps: list[Swap] = Field(default=[], max_length=3)
    runes: list[Name] | None = Field(default=None, max_length=8, description="Your rune page, if you changed it")
    position: str | None = Field(default=None, pattern="^(baron|jungle|mid|dragon|support)$")


@app.post("/api/builds/tailor")
def tailor(request: TailorRequest, user: str = Depends(write_rate_limit)) -> dict:
    # Plain `def` on purpose: the agent call blocks, so FastAPI runs it in a worker thread.
    from wildrift.agent import tailor_build  # imported lazily so the read-only endpoints work without the agent's deps

    try:
        result = tailor_build(
            request.champion,
            request.enemies,
            [(s.remove, s.add) for s in request.swaps],
            request.position,
            runes=request.runes,
            on_api_call=lambda: ai_usage.consume(user),
        )
    except (data.UnknownChampionError, data.UnknownItemError, data.UnknownRuneError) as e:
        raise HTTPException(status_code=404, detail=e.args[0]) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except data.NoDataError:
        _no_data()
    except RuntimeError as e:  # missing API key
        raise HTTPException(status_code=503, detail=str(e)) from e
    except HTTPException:
        raise  # usage limit reached
    except Exception as e:  # the AI service failed (network, overload, ...): don't charge for it
        ai_usage.refund(user)
        logging.getLogger(__name__).exception("AI build failed")
        raise HTTPException(
            status_code=502, detail="The AI service didn't answer. Try again; this one wasn't counted."
        ) from e
    return {"result": result, "ai_usage": ai_usage.status(user)}


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
