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
        await page.locator('[data-tab="collections"]').click()
        await page.locator('#collections form[action="/collections"] input[name="name"]').fill("Christmas")
        await page.locator('#collections form[action="/collections"] textarea').fill("Festive pre-rolls for December")
        await page.locator('#collections form[action="/collections"] button.primary').click()
        await expect(page.locator('#collections')).to_have_class(re.compile("active"))
        await page.wait_for_timeout(900)
        await page.locator('.collection-row:has-text("Christmas") [data-add-members]').click()
        await page.locator('[data-member-search]').fill("Christmas")
        await page.locator('#add-members-dialog input[value="Christmas"]').check()
        await page.locator('#add-members-dialog button.primary').click()
        await expect(page.locator('#collections')).to_have_class(re.compile("active"))
        await page.wait_for_timeout(1000)
        await page.locator('[data-tab="schedule"]').click()
        schedule_form = page.locator('#schedule form[action="/schedules"]')
        await schedule_form.locator('input[name="name"]').fill("Christmas")
        await schedule_form.locator('select[name="collection_id"]').select_option(label="Christmas")
        await schedule_form.locator('input[name="starts_at"]').fill("2026-12-01T00:00")
        await schedule_form.locator('input[name="ends_at"]').fill("2027-01-01T00:00")
        await schedule_form.locator('[data-recurrence]').select_option("FREQ=YEARLY")
        await schedule_form.locator('input[name="color"]').fill("#ef4444")
        await schedule_form.locator('button.primary').click()
        await expect(page.locator('#schedule')).to_have_class(re.compile("active"))
        await page.wait_for_timeout(900)
        await page.locator('[data-calendar-next]').click()
        await expect(page.locator('[data-calendar-title]')).to_have_text("December 2026")
        await page.wait_for_timeout(1600)
        await page.locator('[data-edit-schedule]').click()
        await expect(page.locator('#edit-schedule-dialog')).to_be_visible()
        await page.wait_for_timeout(1000)
        await page.locator('#edit-schedule-dialog [data-close]').click()
        await page.locator('[data-tab="library"]').click()
        await page.locator('.explorer-item[data-path="Christmas"]').dblclick()
        await expect(page.locator('.collection-tag')).to_have_text("Christmas")
        await page.wait_for_timeout(1200)
        await page.screenshot(path=output / "desktop.png", full_page=True)
        await context.close()

        mobile = await browser.new_context(viewport={"width": 412, "height": 915}, is_mobile=True, has_touch=True)
        mobile_page = await mobile.new_page()
        await mobile_page.goto("http://127.0.0.1:18080/", wait_until="networkidle")
        await mobile_page.locator('.explorer-item[data-path="Christmas"]').click()
        await mobile_page.locator("[data-select-mode]").click()
        await mobile_page.locator(".explorer-item").first.click()
        await expect(mobile_page.locator("[data-selection-count]")).to_have_text("1 selected")
        await mobile_page.screenshot(path=output / "mobile.png", full_page=True)
        await mobile_page.locator("[data-selection-done]").click()
        await mobile.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
