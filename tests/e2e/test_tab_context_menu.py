import subprocess
import time
import os
import signal
import json
from playwright.sync_api import sync_playwright


def main():
    env = os.environ.copy()
    env["BYPASS_AUTH_FOR_TESTING"] = "true"
    env["PORT"] = "5005"
    env["DATA_DIR"] = "/tmp/gemini-webui-test-data"
    os.makedirs(env["DATA_DIR"], exist_ok=True)

    print("Starting server...")
    process = subprocess.Popen(
        [".venv/bin/python3", "src/app.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        time.sleep(5)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto("http://127.0.0.1:5005/")
            page.wait_for_load_state("networkidle")
            time.sleep(2)

            # 0. Verify Pin Tab is HIDDEN on Launcher Tab
            print("Verifying Pin Tab is hidden on launcher...")
            tab = page.locator(".tab").first
            tab.click(button="right")
            time.sleep(1)
            assert page.locator(
                "#ctx-pin-tab"
            ).is_hidden(), "Pin Tab option should be hidden on launcher tab"
            page.mouse.click(0, 0)  # Close menu
            time.sleep(0.5)

            # 1. Start a session to make it a terminal tab
            print("Starting a session...")
            page.locator(
                '.tab-instance.active button:has-text("Start New")'
            ).first.click()
            time.sleep(3)

            # 2. Verify Tab Context Menu on Right Click (Now should be visible)
            print("Verifying Tab Context Menu on terminal tab...")
            tab.click(button="right")
            time.sleep(1)

            menu = page.locator("#tab-context-menu")
            assert (
                menu.is_visible()
            ), "Tab context menu should be visible after right-click"

            # 3. Verify Pin Tab and Default Prompt
            assert page.locator(
                "#ctx-pin-tab"
            ).is_visible(), "Pin Tab option should be visible on terminal tab"
            assert page.locator(
                "text='Gemini Audit'"
            ).is_visible(), "Default prompt 'Gemini Audit' should be visible"

            # 4. Verify Add Prompt Modal
            print("Verifying Add Prompt Modal...")
            page.locator("text='Add Prompt...'").click()
            time.sleep(1)
            assert page.locator(
                "#add-prompt-modal"
            ).is_visible(), "Add Prompt modal should be visible"
            page.locator(
                "#add-prompt-modal span:has-text('×')"
            ).first.click()  # Close modal
            time.sleep(0.5)

            # 5. Verify Manage Prompts Modal
            print("Verifying Manage Prompts Modal...")
            tab.click(button="right")  # Re-open context menu
            time.sleep(0.5)
            page.locator("text='Manage Prompts...'").click()
            time.sleep(1)
            assert page.locator(
                "#manage-prompts-modal"
            ).is_visible(), "Manage Prompts modal should be visible"
            assert page.locator(
                "#manage-prompts-modal >> text='Gemini Audit'"
            ).is_visible(), "Gemini Audit should be in management list"

            # 6. Verify Pinning (Local Storage)
            print("Verifying Pinning...")
            page.locator(
                "#manage-prompts-modal span:has-text('×')"
            ).first.click()  # Close modal
            time.sleep(0.5)
            tab.click(button="right")
            time.sleep(0.5)
            page.locator("#ctx-pin-tab").click()
            time.sleep(0.5)

            # Verify pinned tab in localStorage
            pinned = page.evaluate("localStorage.getItem('pinned_tabs')")
            assert pinned is not None, "Pinned tabs should be saved in localStorage"
            assert (
                "New Tab" in pinned or "local" in pinned
            ), "Pinned tab title should be in storage"

            # 7. Take Screenshot for proof
            print("Taking proof screenshot...")
            tab.click(button="right")
            time.sleep(0.5)
            page.screenshot(path="public/qa-screenshots/proof_301_tab_context_menu.png")

            browser.close()

        print("Tests passed successfully!")
        with open("test-results-301.json", "w") as f:
            json.dump(
                {
                    "suites": 1,
                    "tests": 1,
                    "passes": 1,
                    "failures": 0,
                    "duration": 20.0,
                    "message": "Tab context menu, pinning, and prompt management verified successfully.",
                },
                f,
            )

    except Exception as e:
        print(f"Test failed: {e}")
        raise e
    finally:
        print("Shutting down server...")
        os.kill(process.pid, signal.SIGTERM)
        process.wait()


if __name__ == "__main__":
    main()
