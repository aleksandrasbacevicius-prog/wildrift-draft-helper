"""Download champion and item icons from Riot's Data Dragon CDN into static/icons/.

These are PC League of Legends icons, close to but not identical to Wild Rift's.
Run once (and again after adding champions or items):

    python scripts/fetch_icons.py
"""

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wildrift.data import icon_slug, load_data  # noqa: E402

CDN = "https://ddragon.leagueoflegends.com"
OUT = ROOT / "static" / "icons"


def get_json(url: str):
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def download(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=30) as response:
        path.write_bytes(response.read())


def main() -> None:
    version = get_json(f"{CDN}/api/versions.json")[0]
    print(f"Data Dragon version {version}")
    data = load_data()

    for champion in data["champions"]:
        download(f"{CDN}/cdn/{version}/img/champion/{champion}.png", OUT / "champions" / f"{champion}.png")
        print(f"  champion  {champion}")

    # Several IDs can share a name (e.g. Arena variants); the lowest ID is the regular item.
    ids_by_name: dict[str, int] = {}
    for item_id, item in get_json(f"{CDN}/cdn/{version}/data/en_US/item.json")["data"].items():
        name = item["name"].lower()
        ids_by_name[name] = min(int(item_id), ids_by_name.get(name, 10**9))

    missing = []
    for item in data["items"]:
        item_id = ids_by_name.get(item.lower())
        if item_id is None:
            missing.append(item)
            continue
        download(f"{CDN}/cdn/{version}/img/item/{item_id}.png", OUT / "items" / f"{icon_slug(item)}.png")
        print(f"  item      {item}")

    if missing:
        print(f"No icon found for: {', '.join(missing)}. The site shows a text badge instead.")


if __name__ == "__main__":
    main()
