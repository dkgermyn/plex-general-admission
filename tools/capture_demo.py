"""Capture stable README screenshots and one focused schedule-creation GIF.

Run against an auth-disabled synthetic-data instance at http://127.0.0.1:18080.
The script deliberately seeds data before recording so page setup and navigation do
not appear in the GIF.
"""

import asyncio
import re
import subprocess
from pathlib import Path

from playwright.async_api import Page, async_playwright, expect


ASSETS = Path("assets/screenshots")
CAPTURE = Path("demo-capture")


async def open_tab(page: Page, name: str) -> None:
    await page.locator(f'[data-tab="{name}"]').click()
    await expect(page.locator(f"#{name}")).to_have_class(re.compile("active"))


async def select_december_2026(page: Page) -> None:
    await page.locator("[data-calendar-next]").click()
    await expect(page.locator("[data-calendar-title]")).to_have_text("December 2026")


async def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    CAPTURE.mkdir(exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)

        # Seed representative data before any animation is recorded.
        setup = await browser.new_context(viewport={"width": 1440, "height": 1000})
        page = await setup.new_page()
        page.set_default_timeout(7000)
        await page.goto("http://127.0.0.1:18080/", wait_until="networkidle")
        await open_tab(page, "collections")
        collection_form = page.locator('#collections form[action="/collections"]')
        await collection_form.locator('input[name="name"]').fill("Christmas")
        await collection_form.locator("textarea").fill("Festive pre-rolls for December")
        await collection_form.locator('input[name="color"]').fill("#b91c1c")
        await collection_form.locator("button.primary").click()
        await page.locator('.collection-row:has-text("Christmas") [data-add-members]').click()
        await page.locator('[data-member-search]').fill("Christmas")
        await page.locator('#add-members-dialog input[value="Christmas"]').check()
        await page.locator('#add-members-dialog button.primary').click()
        await open_tab(page, "schedule")
        schedule_form = page.locator("[data-new-schedule]")
        christmas_value = await schedule_form.locator(
            'select[name="collection_id"] option', has_text="Christmas"
        ).get_attribute("value")
        await schedule_form.locator('input[name="name"]').fill("Christmas season")
        await schedule_form.locator('select[name="collection_id"]').select_option(christmas_value)
        await schedule_form.locator('input[name="starts_at"]').fill("2026-12-01T00:00")
        await schedule_form.locator('input[name="ends_at"]').fill("2027-01-01T00:00")
        await schedule_form.locator("[data-recurrence]").select_option("FREQ=YEARLY")
        await schedule_form.locator('input[name="color"]').fill("#ef4444")
        await schedule_form.locator("button.primary").click()

        # Static gallery: each image is composed independently and allowed to settle.
        await open_tab(page, "library")
        await page.locator("#library").screenshot(path=ASSETS / "library.png")
        await open_tab(page, "collections")
        await page.locator("#collections").screenshot(path=ASSETS / "collections.png")
        await open_tab(page, "schedule")
        await select_december_2026(page)
        await page.add_style_tag(content="#schedule > .split { display: none !important; }")
        await page.locator("#schedule").screenshot(path=ASSETS / "schedule.png")
        await setup.close()

        mobile = await browser.new_context(viewport={"width": 412, "height": 915}, is_mobile=True, has_touch=True)
        mobile_page = await mobile.new_page()
        await mobile_page.goto("http://127.0.0.1:18080/", wait_until="networkidle")
        await mobile_page.locator('.explorer-item[data-path="Christmas"]').click()
        await mobile_page.locator("[data-select-mode]").click()
        await mobile_page.locator(".explorer-item").first.click()
        await expect(mobile_page.locator("[data-selection-count]")).to_have_text("1 selected")
        await mobile_page.screenshot(path=ASSETS / "mobile.png", full_page=False)
        await mobile.close()

        # Focused animation: one task, real-time typing, and deliberate pauses.
        recording = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            record_video_dir=CAPTURE,
            record_video_size={"width": 1280, "height": 800},
        )
        flow = await recording.new_page()
        flow.set_default_timeout(7000)
        await flow.goto("http://127.0.0.1:18080/", wait_until="networkidle")
        await open_tab(flow, "schedule")
        await select_december_2026(flow)
        await flow.locator("#calendar").scroll_into_view_if_needed()
        await flow.wait_for_timeout(1500)
        start_cell = flow.locator('[data-calendar-date="2026-12-24"]')
        end_cell = flow.locator('[data-calendar-date="2026-12-26"]')
        start_box, end_box = await start_cell.bounding_box(), await end_cell.bounding_box()
        await flow.mouse.move(start_box["x"] + 12, start_box["y"] + 12)
        await flow.mouse.down()
        await flow.mouse.move(end_box["x"] + 12, end_box["y"] + 12, steps=18)
        await flow.mouse.up()
        form = flow.locator("[data-new-schedule]")
        await expect(form.locator('input[name="starts_at"]')).to_have_value("2026-12-24T00:00")
        await flow.wait_for_timeout(700)
        await form.locator('input[name="name"]').press_sequentially("Holiday premiere", delay=85)
        await form.locator('select[name="collection_id"]').select_option(christmas_value)
        await form.locator('input[name="priority"]').fill("10")
        await form.locator('select[name="overlap_policy"]').select_option("exclusive")
        await form.locator('input[name="color"]').fill("#f59e0b")
        await flow.wait_for_timeout(1200)
        await form.locator("button.primary").click()
        await open_tab(flow, "schedule")
        await select_december_2026(flow)
        await flow.locator("#calendar").scroll_into_view_if_needed()
        await expect(flow.locator('.calendar-event-span:has-text("Holiday premiere")')).to_be_visible()
        await flow.wait_for_timeout(2500)
        video = flow.video
        await recording.close()
        video_path = await video.path()
        await browser.close()

    subprocess.run(
        [
            "ffmpeg", "-y", "-ss", "2", "-i", str(video_path), "-vf",
            "fps=10,scale=960:-1:flags=lanczos,split[s0][s1];"
            "[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3",
            "-loop", "0", "assets/schedule-flow.gif",
        ],
        check=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
