import time
import os
import subprocess
from playwright.sync_api import sync_playwright


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.on("console", lambda msg: print("CONSOLE:", msg.text))
        page.route("**/socket.io/*", lambda route: route.abort())
        page.goto("http://127.0.0.1:5002", timeout=15000)
        page.wait_for_selector(".launcher", state="attached", timeout=15000)

        time.sleep(6)

        local_health = page.locator(
            'div[data-label="local"] .connection-title span[id$="_health_local"]'
        ).first
        print("Health text:", local_health.text_content())
        browser.close()


if __name__ == "__main__":
    proc = subprocess.Popen(
        ["python3", "src/app.py"],
        env=dict(os.environ, PORT="5002", BYPASS_AUTH_FOR_TESTING="true"),
    )
    time.sleep(3)
    try:
        run()
    finally:
        proc.terminate()
