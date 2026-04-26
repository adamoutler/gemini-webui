import os
import subprocess
import time
import signal
from playwright.sync_api import sync_playwright


def log(msg):
    print(msg)
    with open("zombie_test_v2.log", "a") as f:
        f.write(msg + "\n")


def get_zombie_count():
    # Using the user's preferred command for monitoring
    result = subprocess.run(
        "ps -aux | grep defunct | grep -v grep | wc -l",
        shell=True,
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip())


def main(playwright):
    if os.path.exists("zombie_test_v2.log"):
        os.remove("zombie_test_v2.log")

    log("--- Starting Zombie Reproduction Test V2 ---")

    initial_zombies = get_zombie_count()
    log(f"Initial zombie count: {initial_zombies}")

    # Create a fresh temporary data directory
    test_temp_dir = os.path.abspath("test_gemini_data")
    if os.path.exists(test_temp_dir):
        import shutil

        shutil.rmtree(test_temp_dir)
    os.makedirs(test_temp_dir, exist_ok=True)

    # Start the app
    log("Starting Gemini WebUI...")
    env = os.environ.copy()
    env["BYPASS_AUTH_FOR_TESTING"] = "true"
    env["PORT"] = "5009"
    env["FLASK_USE_RELOADER"] = "false"
    env["SKIP_MULTIPLEXER"] = "true"
    env["SKIP_MONKEY_PATCH"] = "false"
    env["SKIP_PRELOADER"] = "false"
    env["DATA_DIR"] = test_temp_dir
    env["GEMINI_BIN"] = os.path.abspath("tests/mock/gemini")
    import sys

    app_process = subprocess.Popen([sys.executable, "src/app.py"], env=env)
    time.sleep(5)

    try:
        p = playwright
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.on("console", lambda msg: log(f"BROWSER CONSOLE: {msg.text}"))
        page.on("pageerror", lambda err: log(f"BROWSER ERROR: {err.message}"))
        url = "http://127.0.0.1:5009/"

        # Reproduction Path 1: Ctrl-Z + Restart
        log("Path 1: Testing Ctrl-Z + Restart")
        page.goto(url)
        # Wait for connection card to appear
        page.wait_for_selector(".connection-card[data-label='local']")
        # Click "Start New" on local card
        page.locator(
            ".connection-card[data-label='local'] button:has-text('Start New')"
        ).first.click()
        page.wait_for_selector(".terminal-instance")

        # Wait for terminal to be ready and show welcome message
        page.wait_for_function(
            """() => {
            const term = document.querySelector('.xterm-rows');
            return term && term.innerText.includes('Welcome');
        }""",
            timeout=15000,
        )
        log("Terminal is ready.")

        # Send Ctrl-Z twice
        page.keyboard.press("Control+z")
        time.sleep(0.5)
        page.keyboard.press("Control+z")
        time.sleep(0.5)

        # Click Restart
        restart_btn = page.locator("button:has-text('Restart')")
        if restart_btn.count() > 0:
            restart_btn.first.click()
            log("Clicked Restart button.")
        else:
            log("Warning: Restart button not found.")

        time.sleep(5)  # Wait for reaping
        count_after_p1 = get_zombie_count()
        log(f"Zombies after Path 1: {count_after_p1}")

        # Reproduction Path 2: Ctrl-C
        log("Path 2: Testing Ctrl-C")
        page.keyboard.press("Control+c")
        time.sleep(5)
        count_after_p2 = get_zombie_count()
        log(f"Zombies after Path 2: {count_after_p2}")

        # Reproduction Path 3: Rapid-fire "+ New"
        log("Path 3: Testing Rapid-fire '+ New' -> 'Start New'")
        for i in range(5):
            log(f"Rapid-fire attempt {i+1}")
            # Click "+ New" (it's the last tab usually, or has specific content)
            page.click(".tab:not(:has(.tab-close))")
            page.wait_for_selector("button:has-text('Start New')")
            # Click "Start New" for Local (usually first)
            page.locator("button:has-text('Start New')").first.click()
            time.sleep(0.5)

        time.sleep(5)
        count_after_p3 = get_zombie_count()
        log(f"Zombies after Path 3: {count_after_p3}")

        # Reproduction Path 4: Rapid Page Reload (Lockup test)
        log("Path 4: Testing Rapid Page Reload (Lockup test)")
        for i in range(10):
            page.reload()

        log("Reloads finished. Checking if UI is still responsive...")
        page.goto(url)
        page.wait_for_selector(".connection-card[data-label='local']", timeout=10000)
        log("UI is still responsive: PASS")

        browser.close()

    except Exception as e:
        log(f"Error during test: {e}")
    finally:
        app_process.terminate()
        app_process.wait()
        try:
            os.kill(app_process.pid, signal.SIGKILL)  # Ensure it's gone
        except ProcessLookupError:
            pass

    final_zombies = get_zombie_count()
    log(f"Final zombie count: {final_zombies}")

    if final_zombies > initial_zombies:
        log(
            f"FAILURE: Zombie count increased from {initial_zombies} to {final_zombies}"
        )
        exit(1)
    else:
        log("SUCCESS: No new zombies detected.")
        exit(0)


if __name__ == "__main__":
    with sync_playwright() as playwright:
        main(playwright)
