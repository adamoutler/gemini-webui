import asyncio
from playwright.async_api import async_playwright
import subprocess
import time
import os
import json
import sys

os.environ["DATA_DIR"] = "test_gemini_data"
os.environ["AUTH_METHOD"] = "local"
os.environ["LOCAL_ADMIN_PASS"] = "admin"
os.environ["SECRET_KEY"] = "supersecret"
os.environ["PORT"] = "5008"

data_dir = os.path.join(os.getcwd(), "test_gemini_data")
os.makedirs(data_dir, exist_ok=True)
sessions_file = os.path.join(data_dir, "persisted_sessions.json")

sessions = {}
if os.path.exists(sessions_file):
    with open(sessions_file, "r") as f:
        try:
            sessions = json.load(f)
        except json.JSONDecodeError:
            pass

sessions["tab_123456789"] = {
    "tab_id": "tab_123456789",
    "title": "Very Long Server Name That Should Overflow And Ellipsis Instead Of Squishing The Green Status Indicator Circle",
    "ssh_target": "localhost",
    "ssh_dir": "",
    "user_id": "admin",
    "resume": "new",
}

with open(sessions_file, "w") as f:
    json.dump(sessions, f)

# Start server as subprocess
proc = subprocess.Popen([sys.executable, "src/app.py"])
time.sleep(3)  # Wait for server to start


async def main():
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context(
                viewport={"width": 400, "height": 800},
                http_credentials={"username": "admin", "password": "admin"},
            )
            page = await context.new_page()

            await page.goto("http://127.0.0.1:5008")
            await page.wait_for_selector(
                ".connection-title", state="attached", timeout=15000
            )
            await asyncio.sleep(2)  # Give it time to render the DOM fully

            os.makedirs("docs/qa-images", exist_ok=True)
            await page.screenshot(
                path="docs/qa-images/fix_indicator_circle_proof.png", full_page=True
            )
            await browser.close()
    finally:
        proc.terminate()
        proc.wait()


asyncio.run(main())
