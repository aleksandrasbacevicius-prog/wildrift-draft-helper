import json

import pytest
from fastapi.testclient import TestClient

from wildrift import data
from wildrift.api import app

client = TestClient(app)


def darius():
    return data.get_build("Darius")


def test_rune_catalog_has_keystones_and_trees():
    runes = data.get_runes()
    assert any(r["kind"] == "keystone" for r in runes.values())
    assert {r["tree"] for r in runes.values() if r["kind"] == "minor"} >= {"Resolve", "Precision"}


def test_build_runes_are_valid_pages():
    build = darius()
    assert data.validate_runes("Darius", build["runes"]) == build["runes"]


def test_rune_swap_rules():
    runes = darius()["runes"]
    keystones = [r for r, v in data.get_runes().items() if v["kind"] == "keystone"]
    other_keystone = next(k for k in keystones if k != runes[0])
    swapped = [other_keystone, *runes[1:]]
    assert data.validate_runes("Darius", swapped)[0] == other_keystone
    with pytest.raises(ValueError):  # keystone in a minor slot
        data.validate_runes("Darius", [runes[0], other_keystone, *runes[2:]])
    with pytest.raises(ValueError):  # repeated rune
        data.validate_runes("Darius", [runes[0], runes[1], runes[1], *runes[3:]])
    with pytest.raises(ValueError):  # wrong length
        data.validate_runes("Darius", runes[:-1])
    with pytest.raises(data.UnknownRuneError):
        data.validate_runes("Darius", ["Not A Rune", *runes[1:]])


def test_preferences_save_load_reset():
    build = darius()
    core = ["Trinity Force", *build["core"][1:]]
    saved = data.save_preferences("alex", "darius", core, build["runes"])
    assert saved["core"][0] == "Trinity Force"
    assert data.get_preferences("alex", "Darius")["core"] == core
    assert data.get_preferences("sam", "Darius") is None
    assert data.get_preferences(None, "Darius") is None
    data.reset_preferences("alex", "Darius")
    assert data.get_preferences("alex", "Darius") is None


def test_preferences_reject_bad_core():
    build = darius()
    with pytest.raises(ValueError):
        data.save_preferences("alex", "Darius", [build["core"][0]] * 3, build["runes"])
    with pytest.raises(ValueError):
        data.save_preferences("alex", "Darius", ["Plated Steelcaps", *build["core"][1:]], build["runes"])


def test_preferences_api_round_trip():
    build = darius()
    body = {"core": ["triforce", *build["core"][1:]], "runes": build["runes"]}
    assert client.put("/api/preferences/Darius", json=body).json()["saved"]["core"][0] == "Trinity Force"
    assert client.get("/api/preferences/Darius").json()["saved"]["core"][0] == "Trinity Force"
    assert client.delete("/api/preferences/Darius").json() == {"saved": None}
    assert client.get("/api/preferences/Darius").json() == {"saved": None}


def test_preferences_api_validation():
    build = darius()
    bad = {"core": build["core"], "runes": ["Not A Rune", *build["runes"][1:]]}
    assert client.put("/api/preferences/Darius", json=bad).status_code == 404
    assert (
        client.put("/api/preferences/Nobody", json={"core": build["core"], "runes": build["runes"]}).status_code == 404
    )


def test_runes_endpoint_lists_keystones_first():
    runes = client.get("/api/runes").json()
    assert runes[0]["kind"] == "keystone"


def test_tailor_rejects_invalid_rune_page():
    runes = darius()["runes"]
    body = {"champion": "Darius", "enemies": ["Garen"], "runes": [runes[1], runes[0], *runes[2:]]}
    assert client.post("/api/builds/tailor", json=body).status_code == 400


def test_stale_saved_build_is_ignored():
    build = darius()
    data.save_preferences("alex", "Darius", build["core"], build["runes"])
    path = data.PREFS_DIR / "alex.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    key = data._prefs_key("Darius", None)
    saved[key]["core"][0] = "Item Removed In A Patch"
    path.write_text(json.dumps(saved), encoding="utf-8")
    assert data.get_preferences("alex", "Darius") is None
    saved[key]["core"][0] = build["core"][0]
    saved[key]["runes"][0] = "Rune Removed In A Patch"
    path.write_text(json.dumps(saved), encoding="utf-8")
    assert data.get_preferences("alex", "Darius") is None


def test_boots_cannot_be_swapped_into_core():
    with pytest.raises(ValueError, match="boots"):
        data.swap_core_item("Darius", darius()["core"][0], "Plated Steelcaps")
