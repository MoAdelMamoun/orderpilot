"""Capture real screenshots of the running OrderPilot app via Playwright.

The FastAPI app must already be running on the given base URL:
    uvicorn app:app --port 8773
    python tools/shoot.py http://localhost:8773
"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"


def drive_simulator(page, base: str) -> None:
    """Play a short order conversation so the screenshot shows a real chat."""
    page.goto(base + "/", wait_until="networkidle")
    page.wait_for_selector("#input")
    time.sleep(1.2)  # let the greeting render

    script = ["1", "2", "2", "5", "1", "done", "Jamie Example", "+1-555-0188", "yes"]
    box = page.locator("#input")
    for msg in script:
        box.fill(msg)
        page.locator("#composer button").click()
        time.sleep(0.7)
    time.sleep(1.0)
    page.screenshot(path=str(OUT / "simulator.png"))
    print("saved simulator.png")


def main(base: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    base = base.rstrip("/")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900},
                                device_scale_factor=2)

        # 1) Chat simulator mid-order.
        drive_simulator(page, base)

        # 2) Admin dashboard (now has the just-placed order).
        page.goto(base + "/admin", wait_until="networkidle")
        page.wait_for_selector("table")
        time.sleep(0.8)
        page.screenshot(path=str(OUT / "admin.png"))
        print("saved admin.png")

        # 3) Order detail — open the newest order from the dashboard.
        page.locator("table tbody tr").first.click()
        page.wait_for_selector("h1")
        time.sleep(0.8)
        page.screenshot(path=str(OUT / "order_detail.png"))
        print("saved order_detail.png")

        # 4) Conversations list.
        page.goto(base + "/admin/conversations", wait_until="networkidle")
        page.wait_for_selector("table")
        time.sleep(0.6)
        page.screenshot(path=str(OUT / "conversations.png"))
        print("saved conversations.png")

        browser.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8773")
