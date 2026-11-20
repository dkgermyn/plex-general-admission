"""Record the README demo against an auth-disabled synthetic-data instance."""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright


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
        await page.locator('a[href="/?path=Christmas"]').click()
        await page.wait_for_timeout(1000)
        await page.locator(".preview").first.click()
        await page.wait_for_timeout(1700)
        await page.locator("#video-dialog [data-close]").click()
        await page.wait_for_timeout(500)
        await page.locator("a.brand").click()
        await page.locator('[data-tab="collections"]').click()
        await page.wait_for_timeout(1400)
        await page.locator('[data-tab="schedule"]').click()
        await page.wait_for_timeout(1600)
        await page.locator('[data-tab="trash"]').click()
        await page.wait_for_timeout(900)
        await context.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
