import os
import time
from playwright.sync_api import sync_playwright

def main():
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

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            print("Navigating to app...")
            page.goto("http://127.0.0.1:5004/")
            page.wait_for_load_state("networkidle")
            page.wait_for_selector(".launcher", state="attached", timeout=15000)
            
            # Start a local session to see the connection items
            print("Starting a local session to view connection indicators...")
            try:
                page.locator('.tab-instance.active button:has-text("Start New")').first.click()
                page.wait_for_selector("#active-connection-info", timeout=5000)
                
                # Go back to launcher
                page.locator("#new-tab-btn").click()
                page.wait_for_selector(".backend-sessions-container .session-item", timeout=5000)
                
                # Force the pulse indicator to show with the superbright class
                print("Triggering the flash transition...")
                page.evaluate("""() => {
                    const indicator = document.querySelector('.connections-list .pulse-indicator');
                    if (indicator) {
                        indicator.classList.add('pulsing', 'superbright');
                    }
                }""")
                
                # Wait just a tiny bit to catch it in the middle of the animation
                time.sleep(0.15)
                
                print(f"Taking screenshot of the transition: {screenshot_path}")
                page.screenshot(path=screenshot_path, full_page=True)
                print("Screenshot captured successfully!")
                
            except Exception as e:
                print(f"Error interacting with page: {e}")
            finally:
                browser.close()

    finally:
        os.kill(process.pid, signal.SIGTERM)
        process.wait()

if __name__ == "__main__":
    main()
