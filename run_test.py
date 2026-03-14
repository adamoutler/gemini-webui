import pytest
from playwright.sync_api import sync_playwright


def run():
    with sync_playwright() as p:
        device = p.devices["Pixel 5"]
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**device)
        page = context.new_page()
        page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
        page.goto("http://127.0.0.1:5002")
        page.locator('.tab-instance.active button:has-text("Start New")').first.click()
        page.wait_for_selector(".xterm-cursor", timeout=15000)
        browser.close()


if __name__ == "__main__":
    import subprocess, time, os

    proc = subprocess.Popen(
        ["python3", "src/app.py"],
        env=dict(os.environ, PORT="5002", BYPASS_AUTH_FOR_TESTING="true"),
    )
    time.sleep(3)
    try:
        run()
    finally:
        proc.terminate()
