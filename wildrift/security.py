"""Access control and usage limits for the API.

- Access tokens: set APP_TOKENS in .env as "name:token" pairs separated by commas, one per person.
  Protected endpoints then need "Authorization: Bearer <token>". With no tokens set, protected
  endpoints only accept requests from this computer (as user "local").
- AI usage limit: AI_BUILD_LIMIT custom builds per AI_WINDOW_HOURS for each person (default 5 per
  48h), plus AI_GLOBAL_LIMIT across everyone as a safety net for the API credit. Saved to disk.
- Rate limit: a small per-person limit on protected endpoints against rapid repeat calls.
"""

import hmac
import json
import os
import re
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

USAGE_FILE = Path(os.getenv("WILDRIFT_USAGE_FILE", ROOT / "data" / "ai_usage.json"))
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}  # "testclient" is the test suite's fake host
USER_NAME = re.compile(r"^[a-z0-9_-]{1,32}$")


def _tokens() -> dict[str, str]:
    """token -> user name, from APP_TOKENS ("alex:abc123,sam:def456")."""
    tokens = {}
    for pair in os.getenv("APP_TOKENS", "").split(","):
        name, _, token = pair.strip().partition(":")
        name = name.strip().lower()
        if name and len(token.strip()) >= 12 and USER_NAME.match(name):
            tokens[token.strip()] = name
    return tokens


def identify(request: Request) -> str | None:
    """The user behind a valid token, "local" for this computer when no tokens are set, else None."""
    tokens = _tokens()
    if not tokens:
        client = request.client.host if request.client else ""
        return "local" if client in LOCAL_HOSTS else None
    supplied = request.headers.get("authorization", "").removeprefix("Bearer ").strip().encode()
    user = None
    for token, name in tokens.items():  # compare against every token so timing doesn't reveal which matched
        if hmac.compare_digest(supplied, token.encode()):
            user = name
    return user


def require_access(request: Request) -> str:
    """FastAPI dependency for endpoints that cost money or change state. Returns the user name."""
    user = identify(request)
    if user:
        return user
    if not _tokens():
        raise HTTPException(status_code=403, detail="Set APP_TOKENS in .env to allow access from other devices.")
    raise HTTPException(status_code=401, detail="Access token required.", headers={"WWW-Authenticate": "Bearer"})


class RateLimiter:
    """At most `limit` calls per `seconds` for each user, kept in memory."""

    def __init__(self, limit: int, seconds: float):
        self.limit, self.seconds = limit, seconds
        self.calls: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def __call__(self, user: str = Depends(require_access)) -> str:
        now = time.monotonic()
        with self.lock:
            calls = self.calls[user]
            while calls and now - calls[0] > self.seconds:
                calls.popleft()
            if len(calls) >= self.limit:
                raise HTTPException(status_code=429, detail="Too many requests. Wait a minute and try again.")
            calls.append(now)
        return user


class UsageLimit:
    """Rolling-window cap on paid AI calls per user and in total, persisted to a JSON file."""

    def __init__(self, limit: int, global_limit: int, window_hours: float, path: Path = USAGE_FILE):
        self.limit, self.global_limit, self.window, self.path = limit, global_limit, window_hours * 3600, path
        self.lock = threading.Lock()

    def _load(self) -> dict[str, list[float]]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        cutoff = time.time() - self.window
        return {user: sorted(t for t in stamps if t > cutoff) for user, stamps in raw.items()}

    def _hours_until_free(self, stamps: list[float]) -> float:
        return round(max(0, stamps[0] + self.window - time.time()) / 3600, 1) if stamps else 0

    def status(self, user: str) -> dict:
        usage = self._load()
        mine = usage.get(user, [])
        everyone = sorted(t for stamps in usage.values() for t in stamps)
        remaining = max(0, min(self.limit - len(mine), self.global_limit - len(everyone)))
        if remaining:
            wait = 0
        elif len(mine) >= self.limit:
            wait = self._hours_until_free(mine)
        else:
            wait = self._hours_until_free(everyone)
        return {
            "user": user,
            "limit": self.limit,
            "window_hours": self.window / 3600,
            "used": len(mine),
            "remaining": remaining,
            "next_free_in_hours": wait,
        }

    def consume(self, user: str) -> None:
        """Record one paid call for `user`, or raise 429 if their limit or the global limit is reached."""
        with self.lock:
            usage = self._load()
            mine = usage.get(user, [])
            everyone = sorted(t for stamps in usage.values() for t in stamps)
            if len(mine) >= self.limit:
                raise HTTPException(
                    status_code=429,
                    detail=f"You've used your {self.limit} custom builds for this {self.window / 3600:g}h window. "
                    f"Next one frees up in {self._hours_until_free(mine)}h.",
                )
            if len(everyone) >= self.global_limit:
                raise HTTPException(
                    status_code=429,
                    detail=f"The app's shared AI budget is used up for now. Try again in {self._hours_until_free(everyone)}h.",
                )
            usage[user] = mine + [time.time()]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(usage), encoding="utf-8")


ai_usage = UsageLimit(
    limit=int(os.getenv("AI_BUILD_LIMIT", "5")),
    global_limit=int(os.getenv("AI_GLOBAL_LIMIT", "30")),
    window_hours=float(os.getenv("AI_WINDOW_HOURS", "48")),
)
write_rate_limit = RateLimiter(limit=10, seconds=60)
