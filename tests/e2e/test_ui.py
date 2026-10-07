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
    phone.locator("#vs").select_option("Syndra")  # the opponent's champion is left out of your list
    phone.locator('.pool-pick[data-name="Ahri"]').click()
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
    expect(phone.locator("#signOut")).to_have_text("Sign out on this phone")
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
    expect(phone.locator("#buildState")).to_contain_text("isn't valid anymore")
    phone.locator('#core .item[data-slot="1"]').click()
    phone.locator(".pick:not(.current):not([disabled])").first.click()
    expect(phone.locator("#buildState")).to_contain_text("Sign-in needed")
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
    phone.locator("#vs").select_option("Nami")  # the most picked support may be the default opponent
    phone.locator("#me").select_option("Yuumi")
    expect(phone.locator("#core")).to_contain_text("No build available for Yuumi")
    phone.locator("#me").select_option("Thresh")  # the page still works afterwards
    expect(phone.locator("#core .item")).to_have_count(3)


def test_counter_strip_under_the_opponent(phone, open_server):
    load(phone, open_server)
    phone.locator("#vs").select_option("Darius")
    strip = phone.locator("#counterStrip")
    expect(strip).to_contain_text("Counters to Darius")
    names = set(strip.locator(".counter-pick").evaluate_all("els => els.map(e => e.dataset.champ)"))
    assert names and names <= {"Malphite", "Dr. Mundo", "Ornn"}
    expect(phone.locator('#me optgroup[label="Baron tier list"]')).to_have_count(1)  # general tier list still there
    assert "Darius" not in phone.locator("#me option").all_inner_texts()[0]  # can't pick the opponent's champion


def test_tapping_a_counter_plays_it_and_shows_the_verdict(phone, open_server):
    load(phone, open_server)
    phone.locator("#vs").select_option("Malphite")
    phone.locator('.counter-pick[data-champ="Mordekaiser"]').click()
    expect(phone.locator("#me")).to_have_value("Mordekaiser")
    expect(phone.locator("#verdict .good")).to_contain_text("Mordekaiser counters Malphite")


def test_verdict_warns_and_suggests_counters(phone, open_server):
    load(phone, open_server)
    phone.locator("#vs").select_option("Mordekaiser")
    phone.locator("#me").select_option("Malphite")
    expect(phone.locator("#verdict .bad")).to_contain_text("Mordekaiser counters Malphite")
    expect(phone.locator("#verdict")).to_contain_text("Try:")


def test_mutual_counters_show_as_even(phone, open_server):
    load(phone, open_server)
    phone.locator("#vs").select_option("Malphite")
    phone.locator("#me").select_option("Darius")
    expect(phone.locator("#verdict .even")).to_contain_text("Even matchup")


def test_personal_link_signs_in_without_typing(phone, secured_server):
    dialogs = []
    phone.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    phone.goto(f"{secured_server}/#key={TOKEN}")
    expect(phone.locator("#core .item")).to_have_count(3)
    expect(phone.locator("#whoami")).to_have_text("Signed in as chocoloco")
    assert "#key" not in phone.url  # removed from the address bar
    phone.locator('#core .item[data-slot="0"]').click()
    phone.locator(".pick:not(.current):not([disabled])").first.click()
    expect(phone.locator("#buildState")).to_have_text("Your saved build")
    assert dialogs == []


def test_hold_target_is_not_an_image(phone, open_server):
    # iPhone shows its "save image" menu when an <img> is held; the hold target must be the box around it.
    load(phone, open_server)
    target = phone.locator('#core .item[data-slot="0"] [data-info]')
    assert target.evaluate("el => el.tagName") == "SPAN"
    assert target.locator("img").evaluate("el => getComputedStyle(el).pointerEvents") == "none"


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


def test_server_core_choice_applies_and_saves(phone, open_server):
    load(phone, open_server)
    chips = phone.locator("#coreChoices .choice")
    expect(chips.first).to_contain_text("Guide")
    expect(chips.first).to_have_attribute("aria-pressed", "true")
    expect(chips.nth(1)).to_contain_text(re.compile(r"Most popular.*\d+\.\d% win · \d+\.\d% pick", re.S))
    expect(phone.locator("#coreChoices")).to_contain_text("Diamond+")
    chips.nth(1).click()
    expect(chips.nth(1)).to_have_attribute("aria-pressed", "true")
    expect(phone.locator("#buildState")).to_have_text("Your saved build")
    phone.reload()
    expect(phone.locator("#coreChoices .choice").nth(1)).to_have_attribute("aria-pressed", "true")
    phone.locator("#coreChoices .choice").first.click()
    expect(phone.locator("#buildState")).to_have_text("Recommended build")


def test_server_rune_page_choice(phone, open_server):
    load(phone, open_server)
    chips = phone.locator("#runeChoices .choice")
    expect(chips.nth(1)).to_contain_text("Most popular")
    chips.nth(1).click()
    expect(chips.nth(1)).to_have_attribute("aria-pressed", "true")
    expect(phone.locator("#serverSpells")).to_contain_text("On the server")
    chips.first.click()
    expect(phone.locator("#buildState")).to_have_text("Recommended build")


def test_opponents_grouped_by_most_common(phone, open_server):
    load(phone, open_server)
    groups = phone.locator("#vs optgroup")
    expect(groups.first).to_have_attribute("label", "Most common this patch")
    assert re.search(r"\d+% picked$", groups.first.locator("option").first.inner_text())
    expect(phone.locator("#laneStats")).to_contain_text("not head-to-head")
