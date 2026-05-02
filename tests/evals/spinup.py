"""PortSwigger lab spin-up via Playwright.

Authenticates with a PortSwigger account, navigates to a lab page,
clicks "Access the lab", and returns the unique lab instance URL.

Usage:
    python evals/spinup.py <portswigger_lab_url>
    python evals/spinup.py --batch-subset quick [--headed]

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
LABS_FILE = Path(__file__).parent / "datasets" / "portswigger_mvp.json"


class PortSwiggerAuthError(Exception):
    """Raised when credentials are missing or login fails."""


class PortSwiggerTimeoutError(Exception):
    """Raised when a lab fails to spin up within the expected time."""


def _load_credentials() -> tuple[str, str]:
    email = os.environ.get("PORTSWIGGER_EMAIL")
    password = os.environ.get("PORTSWIGGER_PASSWORD")
    if not email or not password:
        raise PortSwiggerAuthError(
            "Missing credentials: set PORTSWIGGER_EMAIL and PORTSWIGGER_PASSWORD environment variables."
        )
    return email, password


async def _login(page: Page, email: str, password: str) -> None:
    await page.goto(f"{PORTSWIGGER_BASE}/users")
    await page.wait_for_selector("#EmailAddress")
    await page.fill("#EmailAddress", email)
    await page.fill("#Password", password)
    await page.click("#Login")
    try:
        await page.wait_for_url(f"{PORTSWIGGER_BASE}/users/youraccount**", timeout=15_000)
    except Exception as exc:
        raise PortSwiggerAuthError(
            "Login failed: check PORTSWIGGER_EMAIL and PORTSWIGGER_PASSWORD. "
            "The account page was not reached after submitting credentials."
        ) from exc


async def _save_session(context: BrowserContext) -> None:
    cookies = await context.cookies()
    SESSION_FILE.write_text(json.dumps(cookies))


async def _is_logged_in(page: Page) -> bool:
    await page.goto(f"{PORTSWIGGER_BASE}/users/youraccount")
    # Logged-in: stays under /users/youraccount (e.g. /users/youraccount/licenses).
    # Not logged-in: redirects to /users?returnurl=... which does NOT start with /users/youraccount.
    return page.url.startswith(f"{PORTSWIGGER_BASE}/users/youraccount")


async def spinup_lab(lab_url: str, *, headless: bool = True) -> str:
    """Spin up a PortSwigger lab and return the unique instance URL.

    Args:
        lab_url:  The canonical PortSwigger lab page URL (from portswigger_labs.json).
        headless: Run browser headlessly. Set False for debugging.

    Returns:
        The unique lab instance URL, e.g. https://abc123.web-security-academy.net

    Raises:
        PortSwiggerAuthError: If credentials are missing or login fails.
        PortSwiggerTimeoutError: If the lab fails to spin up in time.
    """
    email, password = _load_credentials()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()

        if SESSION_FILE.exists():
            saved = json.loads(SESSION_FILE.read_text())
            await context.add_cookies(saved)

        page = await context.new_page()

        if not await _is_logged_in(page):
            await _login(page, email, password)
            await _save_session(context)

        await page.goto(lab_url)

        # "Access the lab" button — class="button-orange" inside .container-buttons-left
        lab_button = ".container-buttons-left a.button-orange"
        try:
            await page.wait_for_selector(lab_button, timeout=20_000)
        except Exception as exc:
            raise PortSwiggerTimeoutError(
                f"Timed out waiting for lab launch button on {lab_url}. "
                "The lab page may not have loaded or the selector may have changed."
            ) from exc

        async with context.expect_page() as new_page_info:
            await page.click(lab_button)

        lab_page = await new_page_info.value
        await lab_page.wait_for_load_state("domcontentloaded")

        try:
            await lab_page.wait_for_url(
                f"**{LAB_INSTANCE_DOMAIN}**",
                timeout=30_000,
            )
        except Exception as exc:
            raise PortSwiggerTimeoutError(
                f"Lab instance URL never resolved for {lab_url}. Current URL: {lab_page.url}"
            ) from exc

        instance_url = lab_page.url
        await browser.close()
        return instance_url


async def spinup_batch(lab_ids: list[str], *, headless: bool = True) -> dict[str, str]:
    """Spin up multiple labs sequentially and return a mapping of lab_id → instance_url.

    Args:
        lab_ids: List of lab IDs from portswigger_mvp.json.
        headless: Run browser headlessly. Set False for debugging.

    Returns:
        Dict mapping lab_id to its unique instance URL (empty string on failure).
    """
    with open(LABS_FILE) as f:
        dataset = json.load(f)

    labs_by_id = {lab["lab_id"]: lab for lab in dataset["labs"]}
    results: dict[str, str] = {}

    for lab_id in lab_ids:
        if lab_id not in labs_by_id:
            print(f"[WARN] Unknown lab_id: {lab_id}", file=sys.stderr)
            continue
        lab_url = labs_by_id[lab_id]["lab_url"]
        print(f"[spinup] {lab_id} ...", file=sys.stderr)
        try:
            instance_url = await spinup_lab(lab_url, headless=headless)
            results[lab_id] = instance_url
            print(f"[spinup] {lab_id} -> {instance_url}", file=sys.stderr)
        except (PortSwiggerAuthError, PortSwiggerTimeoutError) as e:
            print(f"[ERROR] {lab_id}: {e}", file=sys.stderr)
            results[lab_id] = ""

    return results


async def main() -> None:
    headless = "--headed" not in sys.argv

    if "--batch-subset" in sys.argv:
        idx = sys.argv.index("--batch-subset")
        if idx + 1 >= len(sys.argv):
            print("Usage: python evals/spinup.py --batch-subset <subset_name>", file=sys.stderr)
            sys.exit(1)
        subset_name = sys.argv[idx + 1]
        with open(LABS_FILE) as f:
            dataset = json.load(f)
        if subset_name not in dataset["subsets"]:
            print(f"Error: unknown subset '{subset_name}'", file=sys.stderr)
            sys.exit(1)
        lab_ids = dataset["subsets"][subset_name]["labs"]
        try:
            results = await spinup_batch(lab_ids, headless=headless)
        except PortSwiggerAuthError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(results, indent=2))
        return

    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not positional:
        print("Usage: python evals/spinup.py <portswigger_lab_url>")
        print("       python evals/spinup.py --batch-subset <subset_name> [--headed]")
        sys.exit(1)

    lab_url = positional[0]
    try:
        instance_url = await spinup_lab(lab_url, headless=headless)
        print(instance_url)
    except (PortSwiggerAuthError, PortSwiggerTimeoutError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
