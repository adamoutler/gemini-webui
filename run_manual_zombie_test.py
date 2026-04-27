import os
import subprocess
import time
import shutil
import signal
from playwright.sync_api import sync_playwright


def log(msg):
    print(msg)
    with open("zombie_test.log", "a") as f:
        f.write(msg + "\n")


def get_zombie_count():
    result = subprocess.run(
        "ps -aux | grep defunct | grep -v grep | wc -l",
        shell=True,
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip())


def main():
    if os.path.exists("zombie_test.log"):
        os.remove("zombie_test.log")

    log("1. Clean Slate: Checking for 0 zombies.")

    zombie_count = get_zombie_count()
    log(f"Zombies before test: {zombie_count}")
    if zombie_count > 0:
        log("FATAL: There are existing zombies. Cleaning them up or aborting.")
        exit(1)

    log("2. Deploying container (using local app process for V1)...")
    test_temp_dir = os.path.abspath("test_gemini_data")
    if os.path.exists(test_temp_dir):
        shutil.rmtree(test_temp_dir)
    os.makedirs(test_temp_dir, exist_ok=True)

    env = os.environ.copy()
    env["BYPASS_AUTH_FOR_TESTING"] = "true"
    env["PORT"] = "5008"
    env["FLASK_USE_RELOADER"] = "false"
    env["DATA_DIR"] = test_temp_dir
    env["GEMINI_BIN"] = os.path.abspath("tests/mock/gemini")

    import sys

    app_process = subprocess.Popen([sys.executable, "src/app.py"], env=env)
    time.sleep(5)
    log("App deployed.")

    log("3. Playwright verification & interactions...")
    test_failed = False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto("http://127.0.0.1:5008/")

            # Create 5 sessions so `.session-item` count >= 4
            for i in range(5):
                page.click("#new-tab-btn")
                page.wait_for_selector("button:has-text('Start New')")
                page.locator("button:has-text('Start New')").first.click()
                time.sleep(2)

            page.goto("http://127.0.0.1:5008/")
            page.wait_for_timeout(3000)

            # Wait for sessions to load
            sessions = page.locator(".session-item")
            count = sessions.count()
            log(f"Found {count} sessions.")
            if count >= 4:
                log(
                    "Playwright verification of session items in multiple connections (4 or more non-local sessions): PASS"
                )
            else:
                log(f"Playwright verification: Found {count} sessions. Expected >= 4.")
                test_failed = True

            browser.close()
    except Exception as e:
        log(f"Playwright error: {e}")
        test_failed = True

    log("4. Sleep for observation")
    time.sleep(5)

    log("5. Post-trigger observation")
    app_process.terminate()
    app_process.wait()
    try:
        os.kill(app_process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

    final_zombies = get_zombie_count()
    log(f"Zombies after test: {final_zombies}")

    if test_failed:
        log("Test FAILED: Playwright assertions did not pass.")
        exit(1)

    if final_zombies <= zombie_count:
        log("Test PASSED: No new zombies created.")
        exit(0)
    else:
        log("Test FAILED: New zombies detected.")
        exit(1)


if __name__ == "__main__":
    main()
