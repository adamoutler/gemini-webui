import os
import time
from playwright.sync_api import sync_playwright


def main(playwright):
    os.makedirs("docs/qa-images", exist_ok=True)
    screenshot_path = "docs/qa-images/issue_244_flash_transition.png"

    # We will just run a simple server or use the pytest fixture approach
    # Let's just start the app locally and take a screenshot
    import subprocess
    import signal

    env = os.environ.copy()
    env["BYPASS_AUTH_FOR_TESTING"] = "true"
    env["PORT"] = "5004"

    print("Starting server...")
    process = subprocess.Popen(
        ["python3", "src/app.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        time.sleep(3)

        p = playwright
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        print("Navigating to app...")
        page.goto("http://127.0.0.1:5004/")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector(".launcher", state="attached", timeout=15000)

        # Start a local session to see the connection items
        print("Starting a local session to view connection indicators...")
        try:
            page.locator(
                '.tab-instance.active button:has-text("Start New")'
            ).first.click()
            page.wait_for_selector("#active-connection-info", timeout=5000)

            # Go back to launcher
            page.locator("#new-tab-btn").click()
            page.wait_for_selector(
                ".backend-sessions-container .session-item", timeout=5000
            )

            # Force the pulse indicator to show by simulating a health check response organically
            print("Triggering the flash transition organically via HostStateManager...")
            page.evaluate("""() => {
                const activeTab = document.querySelector('.tab-instance.active');
                if (activeTab) {
                    const id = activeTab.id.replace('_instance', '');
                    // Force a status change to trigger the superbright flash naturally
                    HostStateManager.updateHealth(id, 'local', true, true);
                }
            }""")

            print("Taking screenshot mid-animation...")
            time.sleep(0.15)
            page.screenshot(
                path="docs/qa-images/issue_244_flash_mid.png", full_page=True
            )

            print("Taking screenshot near end of animation (0.8s) to prove fade...")
            time.sleep(0.65)
            page.screenshot(
                path="docs/qa-images/issue_244_flash_fade.png", full_page=True
            )

            print("Taking screenshot after animation (1.1s) to prove completion...")
            time.sleep(0.3)
            page.screenshot(
                path="docs/qa-images/issue_244_flash_end.png", full_page=True
            )
            print("Screenshots captured successfully!")

        except Exception as e:
            print(f"Error interacting with page: {e}")
        finally:
            browser.close()

    finally:
        os.kill(process.pid, signal.SIGTERM)
        process.wait()


if __name__ == "__main__":
    main()
