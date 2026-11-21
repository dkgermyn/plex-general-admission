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
        await page.locator('[data-view="details"]').click()
        await page.wait_for_timeout(900)
        await page.locator(".explorer-item").first.click()
        await page.locator(".explorer-item").nth(1).click(modifiers=["Control"])
        await expect(page.locator("[data-selection-count]")).to_have_text("2 selected")
        await page.wait_for_timeout(900)
        await page.locator(".explorer-item").first.click(button="right")
        await expect(page.locator("#item-context-menu")).to_be_visible()
        await page.wait_for_timeout(1200)
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
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.screenshot(path=output / "mobile.png", full_page=True)
        await context.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
