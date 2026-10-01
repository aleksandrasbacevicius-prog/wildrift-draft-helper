"""Browser tests: click through the real page at phone size. Run with: python -m pytest -m e2e"""

import re

import pytest
from playwright.sync_api import Page, expect

from .conftest import TOKEN

pytestmark = pytest.mark.e2e


def load(page: Page, url: str) -> None:
    page.goto(url)
    expect(page.locator("#core .item")).to_have_count(3)


def no_real_errors(page: Page) -> list[str]:
    # Icons aren't in the test sample, so missing images are expected; anything else is a bug.
    return [e for e in page.errors if "404" not in e and "Failed to load resource" not in e]


def test_page_loads_with_patch_lanes_and_build(phone, open_server):
    load(phone, open_server)
    expect(phone.locator("#patch")).to_have_text(re.compile(r"Patch \d+\.\d+"))
    expect(phone.locator(".lane")).to_have_count(5)
    expect(phone.locator('.lane[data-pos="baron"]')).to_have_attribute("aria-pressed", "true")
    expect(phone.locator(".rune")).not_to_have_count(0)
    expect(phone.locator("#buildState")).to_have_text("Recommended build")
    assert no_real_errors(phone) == []


def test_no_sideways_scrolling_on_a_phone(phone, open_server):
    load(phone, open_server)
    assert phone.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_switching_lane_changes_the_champion_list(phone, open_server):
    load(phone, open_server)
    phone.locator('.lane[data-pos="mid"]').click()
    expect(phone.locator('.lane[data-pos="mid"]')).to_have_attribute("aria-pressed", "true")
    options = phone.locator("#me option").all_inner_texts()
    assert any("Ahri" in o for o in options) and not any("Darius" in o for o in options)
    assert all(re.match(r"^(S\+|S|A|B|C|D) · ", o) for o in options)  # tier shown before each name


def test_item_swap_saves_and_survives_reload(phone, open_server):
    load(phone, open_server)
    phone.locator('#core .item[data-slot="0"]').click()
    expect(phone.locator("#sheet")).to_be_visible()
    phone.locator("#sheetSearch").fill("trinity")
    phone.locator('.pick[data-name="Trinity Force"]').click()
    expect(phone.locator("#sheet")).to_be_hidden()
    first = phone.locator('#core .item[data-slot="0"]')
    expect(first).to_contain_text("Trinity Force")
    expect(first).to_contain_text("was ")
    expect(phone.locator("#buildState")).to_have_text("Your saved build")
    phone.reload()
    expect(phone.locator('#core .item[data-slot="0"]')).to_contain_text("Trinity Force")
    phone.locator("#resetBuild").click()
    expect(phone.locator("#buildState")).to_have_text("Recommended build")


def test_item_picker_blocks_duplicates(phone, open_server):
    load(phone, open_server)
    second_core = phone.locator('#core .item[data-slot="1"] div').first.inner_text()
    phone.locator('#core .item[data-slot="0"]').click()
    expect(phone.locator(f'.pick[data-name="{second_core}"]').first).to_be_disabled()
    phone.locator("#sheetClose").click()
    expect(phone.locator("#sheet")).to_be_hidden()


def test_rune_swap_offers_only_keystones_for_the_first_slot(phone, open_server):
    load(phone, open_server)
    phone.locator('.rune[data-rune-slot="0"]').click()
    expect(phone.locator("#sheetBody h3")).to_have_text(["Keystones"])
    phone.locator(".pick:not(.current):not([disabled])").first.click()
    expect(phone.locator('.rune[data-rune-slot="0"]')).to_have_class(re.compile("swapped"))
    expect(phone.locator("#buildState")).to_have_text("Your saved build")
    phone.locator("#resetBuild").click()
    expect(phone.locator("#buildState")).to_have_text("Recommended build")


def test_pool_editor_saves(phone, open_server):
    load(phone, open_server)
    phone.locator('.lane[data-pos="mid"]').click()
    phone.locator("#editPool").click()
    phone.locator('.pool-pick[data-name="Syndra"]').click()
    phone.locator("#savePool").click()
    expect(phone.locator('#me optgroup[label="My pool"] option')).to_have_count(1)


def test_token_is_asked_for_once(phone, secured_server):
    dialogs = []

    def answer(dialog):
        dialogs.append(dialog.message)
        dialog.accept(f"chocoloco:{TOKEN}")  # pasting "name:token" works too

    phone.on("dialog", answer)
    load(phone, secured_server)
    assert dialogs == []  # just browsing never asks
    phone.locator('#core .item[data-slot="0"]').click()
    phone.locator(".pick:not(.current):not([disabled])").first.click()
    expect(phone.locator("#buildState")).to_have_text("Your saved build")
    phone.locator('.rune[data-rune-slot="1"]').click()
    phone.locator(".pick:not(.current):not([disabled])").first.click()
    expect(phone.locator("#buildState")).to_have_text("Your saved build")
    assert len(dialogs) == 1  # one prompt for two saves
    phone.reload()
    expect(phone.locator("#buildState")).to_have_text("Your saved build")  # remembered on this device
    expect(phone.locator("#signOut")).to_have_text("Forget access token")
    assert len(dialogs) == 1


def test_wrong_token_explains_and_stops_asking(phone, secured_server):
    dialogs = []

    def answer(dialog):
        dialogs.append(dialog.message)
        dialog.accept("not-the-right-token")

    phone.on("dialog", answer)
    load(phone, secured_server)
    phone.locator('#core .item[data-slot="0"]').click()
    phone.locator(".pick:not(.current):not([disabled])").first.click()
    expect(phone.locator("#buildState")).to_contain_text("wasn't accepted")
    phone.locator('#core .item[data-slot="1"]').click()
    phone.locator(".pick:not(.current):not([disabled])").first.click()
    expect(phone.locator("#buildState")).to_contain_text("Access token needed")
    assert len(dialogs) == 1  # no prompt on every move


def test_ai_button_without_api_key_shows_an_error(phone, open_server):
    load(phone, open_server)
    expect(phone.locator("#aiUsage")).to_contain_text("5 of 5")
    phone.locator("#tailor").click()
    expect(phone.locator("#result .error")).to_contain_text("ANTHROPIC_API_KEY")
    expect(phone.locator("#aiUsage")).to_contain_text("5 of 5")  # a failed setup doesn't use up a build


def test_champion_without_build_shows_a_message(phone, open_server):
    load(phone, open_server)
    phone.locator('.lane[data-pos="support"]').click()
    phone.locator("#me").select_option("Yuumi")
    expect(phone.locator("#core")).to_contain_text("No build available for Yuumi")
    phone.locator("#me").select_option("Thresh")  # the page still works afterwards
    expect(phone.locator("#core .item")).to_have_count(3)


def test_counterpicks_group_your_champion_list(phone, open_server):
    load(phone, open_server)
    phone.locator("#me").select_option("Garen")  # your own pick is never in the opponent list
    phone.locator("#vs").select_option("Darius")
    group = phone.locator('#me optgroup[label="Strong against Darius"]')
    expect(group).to_have_count(1)
    assert {"Malphite", "Dr. Mundo", "Ornn"} & {o.split(" · ")[-1] for o in group.locator("option").all_inner_texts()}
    expect(phone.locator('#me optgroup[label="Baron tier list"]')).to_have_count(1)  # general tier list still there


def test_matchup_shows_who_counters_whom(phone, open_server):
    load(phone, open_server)
    phone.locator("#me").select_option("Garen")
    phone.locator("#vs").select_option("Darius")
    phone.locator("#me").select_option("Malphite")
    expect(phone.locator("#matchupTags")).to_contain_text("You counter Darius")


def test_build_follows_the_lane(phone, open_server):
    load(phone, open_server)
    phone.locator('.lane[data-pos="jungle"]').click()
    phone.locator("#me").select_option("Darius")
    expect(phone.locator('#core .item[data-slot="0"]')).to_contain_text("Trinity Force")  # Darius' jungle build


def test_press_and_hold_shows_item_details(phone, open_server):
    load(phone, open_server)
    first = phone.locator('#core .item[data-slot="0"] [data-info]')
    first.dispatch_event("pointerdown")
    phone.wait_for_timeout(600)
    first.dispatch_event("pointerup")
    expect(phone.locator("#info")).to_be_visible()
    expect(phone.locator("#infoBody")).to_contain_text("gold")
    expect(phone.locator("#sheet")).to_be_hidden()  # the hold didn't also open the swap picker
    phone.wait_for_timeout(500)  # a person's next tap
    phone.locator("#infoClose").click()
    expect(phone.locator("#info")).to_be_hidden()


def test_right_click_shows_rune_details(phone, open_server):
    load(phone, open_server)
    phone.locator('.rune[data-rune-slot="0"] [data-info]').click(button="right")
    expect(phone.locator("#infoBody")).to_contain_text("Keystone")
