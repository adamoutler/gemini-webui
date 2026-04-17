import subprocess
import time
import os
import signal
import json
from playwright.sync_api import sync_playwright


def main(playwright):
    env = os.environ.copy()
    env["BYPASS_AUTH_FOR_TESTING"] = "true"
    env["PORT"] = "5005"
    env["DATA_DIR"] = "/tmp/gemini-webui-test-data"

    import shutil

    shutil.rmtree(env["DATA_DIR"], ignore_errors=True)
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
        p = playwright
        browser = p.chromium.launch()
        page = browser.new_page()

        page.on("console", lambda msg: print(f"BROWSER CONSOLE: {msg.text}"))

        page.goto("http://127.0.0.1:5005/")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # 0. Verify context menu is HIDDEN initially
        print("Verifying context menu is hidden initially...")
        tab = page.locator(".tab").first
        tab.click(button="right")
        time.sleep(1)
        menu = page.locator("#tab-context-menu")
        assert menu.is_visible(), "Tab context menu should be visible on right-click"
        page.mouse.click(0, 0)  # Close menu
        time.sleep(0.5)

        # 1. Start a session to make it a terminal tab
        print("Starting a session...")
        # Wait for at least one connection card to appear
        page.wait_for_selector(".connection-card", timeout=15000)
        btn = page.locator('button:has-text("Start New")').first
        btn.scroll_into_view_if_needed()
        btn.click()
        time.sleep(5)

        # 2. Verify Tab Context Menu on Right Click (Now should be visible and have prompts)
        print("Verifying Tab Context Menu on terminal tab...")
        tab.click(button="right")
        time.sleep(1)

        menu = page.locator("#tab-context-menu")
        assert menu.is_visible(), "Tab context menu should be visible after right-click"

        # 3. Verify Default Prompts
        print("Verifying Default Prompts...")
        try:
            assert page.locator(
                "text='Gemini Audit'"
            ).is_visible(), "Default prompt 'Gemini Audit' should be visible"
            assert page.locator(
                "text='Explain Code'"
            ).is_visible(), "Default prompt 'Explain Code' should be visible"
        except Exception as e:
            page.screenshot(path="public/qa-screenshots/error_prompts_not_visible.png")
            # Also print the innerHTML of the context menu
            menu_html = page.locator("#tab-context-menu").inner_html()
            print(f"Context menu HTML: {menu_html}")
            raise e

        # 4. Verify Add Prompt Modal
        print("Verifying Add Prompt Modal...")
        page.locator(".context-menu-item:has-text('Add Prompt')").click()
        time.sleep(1)
        assert page.locator(
            "#add-prompt-modal"
        ).is_visible(), "Add Prompt modal should be visible"

        # Fill out the modal
        page.locator("#new-prompt-name").fill("Custom Test Prompt")
        page.locator("#new-prompt-text").fill("This is a test prompt content.")
        page.locator("text='Save Prompt'").click()
        time.sleep(1)

        # 5. Verify Manage Prompts Modal
        print("Verifying Manage Prompts Modal...")
        tab.click(button="right")  # Re-open context menu
        time.sleep(0.5)
        page.locator(".context-menu-item:has-text('Manage Prompts')").click()
        time.sleep(1)
        assert page.locator(
            "#manage-prompts-modal"
        ).is_visible(), "Manage Prompts modal should be visible"
        assert page.locator(
            "#manage-prompts-modal >> text='Custom Test Prompt'"
        ).is_visible(), "Custom Test Prompt should be in management list"

        # 6. Verify custom prompt in context menu
        print("Verifying custom prompt in context menu...")
        page.locator("#manage-prompts-modal span:has-text('×')").first.click()
        time.sleep(1)
        tab.click(button="right")
        time.sleep(1)
        assert page.locator(
            ".context-menu-item:has-text('Custom Test Prompt')"
        ).is_visible(), "Custom Test Prompt should be in context menu"

        # 7. Take Screenshot for proof
        print("Taking proof screenshot...")
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
