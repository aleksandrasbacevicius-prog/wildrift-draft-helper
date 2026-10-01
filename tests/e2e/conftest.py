"""Start real servers on the sample data for the browser tests.

Run with: python -m pytest -m e2e
"""

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "wildriftfire"
TOKEN = "chocoloco-e2e-token-123"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(app_tokens: str):
    port = _free_port()
    tmp = Path(tempfile.mkdtemp(prefix="wildrift-e2e-"))
    env = {
        **os.environ,
        "WILDRIFT_DATA_DIR": str(FIXTURES),
        "WILDRIFT_PROFILE_DIR": str(tmp / "profiles"),
        "WILDRIFT_PREFS_DIR": str(tmp / "builds"),
        "WILDRIFT_USAGE_FILE": str(tmp / "usage.json"),
        "WILDRIFT_AUTO_UPDATE": "0",
        "APP_TOKENS": app_tokens,
        "ANTHROPIC_API_KEY": "",
    }
    process = subprocess.Popen(  # noqa: S603 - fixed command, test-only
        [sys.executable, "-m", "uvicorn", "wildrift.api:app", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT,
        env=env,
    )
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(url + "/api/meta", timeout=1)  # noqa: S310 - local test server
            return process, url
        except OSError:
            time.sleep(0.1)
    process.kill()
    raise RuntimeError("test server did not start")


@pytest.fixture(scope="session")
def open_server():
    """No tokens set: requests from this computer may save and use the AI."""
    process, url = _start_server("")
    yield url
    process.kill()


@pytest.fixture(scope="session")
def secured_server():
    """Tokens set, as on Render: saving needs a token."""
    process, url = _start_server(f"chocoloco:{TOKEN}")
    yield url
    process.kill()


@pytest.fixture
def phone(browser):
    """An iPhone-sized page that fails the test on any browser error or CSP violation."""
    context = browser.new_context(viewport={"width": 375, "height": 812}, is_mobile=True, has_touch=True)
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: m.type == "error" and page.errors.append(m.text))
    yield page
    context.close()
