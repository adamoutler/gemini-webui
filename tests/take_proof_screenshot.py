import subprocess
import time
import os
import signal
from playwright.sync_api import sync_playwright


def main():
    # Start the app in the background with auth bypassed
    env = os.environ.copy()
    env["BYPASS_AUTH_FOR_TESTING"] = "true"
    env["PORT"] = "5003"

    print("Starting server...")
    process = subprocess.Popen(
        ["python3", "src/app.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        # Give the server a few seconds to start
        time.sleep(3)

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()

            print("Navigating to http://127.0.0.1:5003...")
            page.goto("http://127.0.0.1:5003/")

            # Wait for the terminal or main UI to be visible
            # We can just wait for a network idle or a specific selector
            page.wait_for_load_state("networkidle")
            time.sleep(2)  # Extra time for rendering

            screenshot_path = "public/qa-screenshots/proof_216.png"
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"Screenshot saved to {screenshot_path}")

            browser.close()

    finally:
        print("Shutting down server...")
        os.kill(process.pid, signal.SIGTERM)
        process.wait()


if __name__ == "__main__":
    main()
