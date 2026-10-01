"""Point the app at a small checked-in sample of WildRiftFire data, so tests don't need the real download."""

import os
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
os.environ["WILDRIFT_DATA_DIR"] = str(FIXTURES / "wildriftfire")
os.environ["WILDRIFT_PROFILE"] = str(FIXTURES / "profile.test.json")
