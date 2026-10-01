"""Point the app at a small checked-in sample of WildRiftFire data, so tests don't need the real download."""

import os
import tempfile
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
TMP = Path(tempfile.mkdtemp(prefix="wildrift-tests-"))
os.environ["WILDRIFT_DATA_DIR"] = str(FIXTURES / "wildriftfire")
os.environ["WILDRIFT_PROFILE_DIR"] = str(TMP / "profiles")
os.environ["WILDRIFT_PREFS_DIR"] = str(TMP / "builds")
os.environ["WILDRIFT_USAGE_FILE"] = str(TMP / "ai_usage.json")
os.environ["APP_TOKENS"] = ""  # tests run as "this computer" unless a test sets tokens


@pytest.fixture(autouse=True)
def reset_limits(monkeypatch):
    import shutil

    from wildrift import data, security

    security.write_rate_limit.calls.clear()
    security.ai_usage.path.unlink(missing_ok=True)
    shutil.rmtree(data.PROFILE_DIR, ignore_errors=True)
    shutil.rmtree(data.PREFS_DIR, ignore_errors=True)
    monkeypatch.setenv("APP_TOKENS", "")
    yield
