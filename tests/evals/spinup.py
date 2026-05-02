"""PortSwigger lab spin-up via Playwright.

Authenticates with a PortSwigger account, navigates to a lab page,
clicks "Access the lab", and returns the unique lab instance URL.

Usage:
    python evals/spinup.py <portswigger_lab_url>

Environment variables required:
    PORTSWIGGER_EMAIL    — account email
    PORTSWIGGER_PASSWORD — account password
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from playwright.async_api import BrowserContext, Page, async_playwright

PORTSWIGGER_BASE = "https://portswigger.net"
LAB_INSTANCE_DOMAIN = "web-security-academy.net"
SESSION_FILE = Path(__file__).parent / ".portswigger_session.json"


async def _login(page: Page, email: str, password: str) -> None:
    await page.goto(f"{PORTSWIGGER_BASE}/users")
    await page.wait_for_selector("#EmailAddress")
    await page.fill("#EmailAddress", email)
    await page.fill("#Password", password)
    await page.click("#Login")
    await page.wait_for_url(f"{PORTSWIGGER_BASE}/users/youraccount**", timeout=15_000)


async def _save_session(context: BrowserContext) -> None:
    cookies = await context.cookies()
    SESSION_FILE.write_text(json.dumps(cookies))


async def _is_logged_in(page: Page) -> bool:
    await page.goto(f"{PORTSWIGGER_BASE}/users/youraccount")
    return "youraccount" in page.url


async def spinup_lab(lab_url: str, *, headless: bool = True) -> str:
    """Spin up a PortSwigger lab and return the unique instance URL.

    Args:
        lab_url:  The canonical PortSwigger lab page URL (from portswigger_labs.json).
        headless: Run browser headlessly. Set False for debugging.

    Returns:
        The unique lab instance URL, e.g. https://abc123.web-security-academy.net
    """
    email = os.environ["PORTSWIGGER_EMAIL"]
    password = os.environ["PORTSWIGGER_PASSWORD"]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()

        # Restore saved session if available
        if SESSION_FILE.exists():
            saved = json.loads(SESSION_FILE.read_text())
            await context.add_cookies(saved)

        page = await context.new_page()

        if not await _is_logged_in(page):
            await _login(page, email, password)
            await _save_session(context)

        # Navigate to the lab's canonical page
        await page.goto(lab_url)

        # Wait for the JS widget to render the "Access the lab" button
        await page.wait_for_selector(
            "[widget-id='academy-launchlab'] a",
            timeout=20_000,
        )

        # The button opens the lab in a new tab
        async with context.expect_page() as new_page_info:
            await page.click("[widget-id='academy-launchlab'] a")

        lab_page = await new_page_info.value
        await lab_page.wait_for_load_state("domcontentloaded")

        # Wait until the page URL becomes the unique lab instance
        await lab_page.wait_for_url(
            f"**{LAB_INSTANCE_DOMAIN}**",
            timeout=30_000,
        )
        instance_url = lab_page.url

        await browser.close()
        return instance_url


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python evals/spinup.py <portswigger_lab_url>")
        sys.exit(1)

    lab_url = sys.argv[1]
    headless = "--headed" not in sys.argv

    instance_url = await spinup_lab(lab_url, headless=headless)
    print(instance_url)


if __name__ == "__main__":
    asyncio.run(main())
