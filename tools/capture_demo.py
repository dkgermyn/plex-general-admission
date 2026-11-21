"""Record the README demo against an auth-disabled synthetic-data instance."""

import asyncio
import re
from pathlib import Path

from playwright.async_api import async_playwright, expect


async def main() -> None:
    output = Path("demo-capture")
    output.mkdir(exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            record_video_dir=output,
            record_video_size={"width": 1280, "height": 800},
        )
        page = await context.new_page()
        page.set_default_timeout(5000)
        await page.goto("http://127.0.0.1:18080/", wait_until="networkidle")
        await page.wait_for_timeout(1200)
        await page.locator("[data-library-search]").fill("Christmas")
        await expect(page.locator('.explorer-item:not([hidden])')).to_have_count(1)
        await page.wait_for_timeout(800)
        await page.locator("[data-library-search]").fill("")
        await page.locator('[data-view="details"]').click()
        await page.wait_for_timeout(900)
        await page.locator("[data-select-mode]").click()
        await page.locator(".explorer-item").first.click()
        await page.locator(".explorer-item").nth(1).click()
        await expect(page.locator("[data-selection-count]")).to_have_text("2 selected")
        await page.wait_for_timeout(900)
        await page.locator("[data-selection-done]").click()
        await page.locator(".explorer-item").first.click(button="right")
        await expect(page.locator("#item-context-menu")).to_be_visible()
        await expect(page.locator('[data-context-action="open"]')).to_be_visible()
        await expect(page.locator('[data-context-action="preview"]')).to_be_hidden()
        await page.wait_for_timeout(1200)
        await page.keyboard.press("Escape")
        await page.locator('.explorer-item[data-kind="video"]').click(button="right")
        await expect(page.locator('[data-context-action="open"]')).to_be_hidden()
        await expect(page.locator('[data-context-action="preview"]')).to_be_visible()
        await page.wait_for_timeout(800)
        await page.keyboard.press("Escape")
        await page.locator('[data-view="large"]').click()
        await page.locator('.explorer-item[data-path="Christmas"]').dblclick()
        await page.wait_for_timeout(1000)
        await page.locator(".preview").first.click()
        await page.wait_for_timeout(1700)
        await page.locator("#video-dialog [data-close]").click()
        await expect(page.locator("#video-dialog video")).not_to_have_attribute("src", re.compile(".+"))
        await page.wait_for_timeout(500)
        await page.locator("a.brand").click()
        await page.locator('[data-tab="collections"]').click()
        await page.wait_for_timeout(1400)
        await page.locator('[data-tab="schedule"]').click()
        await page.wait_for_timeout(1600)
        await page.locator('[data-tab="trash"]').click()
        await page.wait_for_timeout(900)
        await page.locator('[data-tab="library"]').click()
        await page.screenshot(path=output / "desktop.png", full_page=True)
        await context.close()

        mobile = await browser.new_context(viewport={"width": 412, "height": 915}, is_mobile=True, has_touch=True)
        mobile_page = await mobile.new_page()
        await mobile_page.goto("http://127.0.0.1:18080/", wait_until="networkidle")
        await mobile_page.locator("[data-select-mode]").click()
        await mobile_page.locator(".explorer-item").first.click()
        await mobile_page.locator(".explorer-item").nth(1).click()
        await expect(mobile_page.locator("[data-selection-count]")).to_have_text("2 selected")
        await mobile_page.screenshot(path=output / "mobile.png", full_page=True)
        await mobile_page.locator("[data-selection-done]").click()
        await mobile_page.locator("#upload-input").set_input_files({"name": "studio-intro.mp4", "mimeType": "video/mp4", "buffer": b"synthetic video"})
        await expect(mobile_page.locator("#conflict-dialog")).to_be_visible()
        await mobile_page.locator('[data-conflict-choice="keep_both"]').click()
        await mobile_page.wait_for_load_state("networkidle")
        await expect(mobile_page.locator('.explorer-item[data-name="studio-intro (2).mp4"]')).to_be_visible()
        await mobile.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
