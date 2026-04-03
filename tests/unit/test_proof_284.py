import subprocess
import time
import os
import signal
import json
import glob
from playwright.sync_api import sync_playwright


def main():
    env = os.environ.copy()
    env["BYPASS_AUTH_FOR_TESTING"] = "true"
    env["PORT"] = "5005"

    # clear any existing debug logs
    for f in glob.glob("/tmp/session-*-DEBUG.log"):
        try:
            os.remove(f)
        except:
            pass

    print("Starting server...")
    process = subprocess.Popen(
        [".venv/bin/python3", "src/app.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        time.sleep(3)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto("http://127.0.0.1:5005/")
            page.wait_for_load_state("networkidle")
            time.sleep(2)

            # Send some keys to generate PTY output
            page.keyboard.type("echo 'secret_data_123'\n")
            time.sleep(2)

            page.screenshot(
                path="public/qa-screenshots/proof_284_noleak.png", full_page=True
            )
            browser.close()

        logs_found = glob.glob("/tmp/session-*-DEBUG.log")
        assert len(logs_found) == 0, f"Found debug logs! {logs_found}"

        with open("test-results-284.json", "w") as f:
            json.dump(
                {
                    "suites": 1,
                    "tests": 1,
                    "passes": 1,
                    "failures": 0,
                    "duration": 3.0,
                    "message": "Verified that no DEBUG.log files are created in /tmp for sessions.",
                },
                f,
            )

    finally:
        print("Shutting down server...")
        os.kill(process.pid, signal.SIGTERM)
        process.wait()


if __name__ == "__main__":
    main()
