import subprocess
import time
import os
import signal
from playwright.sync_api import sync_playwright


def main():
    env = os.environ.copy()
    env["BYPASS_AUTH_FOR_TESTING"] = "true"
    env["PORT"] = "5004"

    print("Starting server...")
    process = subprocess.Popen(
        ["python3", "src/app.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=os.setsid,  # Important for tests to not kill host SSH per process isolation docs
    )

    try:
        time.sleep(3)

        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(**p.devices["iPhone 12"])
            page = context.new_page()

            print("Navigating to http://127.0.0.1:5004...")
            page.goto("http://127.0.0.1:5004/")
            page.wait_for_load_state("networkidle")

            print("Starting a new session...")
            try:
                page.click("#quick-connect-btn", timeout=5000)
            except Exception:
                pass

            time.sleep(3)

            # Proof 1: Initial sizing
            os.makedirs("docs/qa-images", exist_ok=True)
            sizing_path = "docs/qa-images/fitTerminal_sizing_388.png"
            page.screenshot(path=sizing_path)
            print(f"Saved {sizing_path}")

            # Output some lines
            page.evaluate("sendToTerminal('echo Hello World\\n');")
            time.sleep(2)

            # Trigger WebGL context loss and massive scroll jump
            page.evaluate("""
                if (window.tabs && tabs.length > 0) {
                    const tab = tabs.find(t => t.state === "terminal");
                    if (tab) {
                        // 1. WebGL Context Loss
                        if (tab.webglAddon && tab.webglAddon._gl) {
                            const ext = tab.webglAddon._gl.getExtension("WEBGL_lose_context");
                            if (ext) ext.loseContext();
                        }

                        // 2. Simulate massive scroll jump in mobile-scroll-proxy
                        const proxy = document.querySelector('.mobile-scroll-proxy');
                        if (proxy) {
                            proxy.scrollTop = 0; // Browser abrupt reset
                            // Dispatch scroll event
                            proxy.dispatchEvent(new Event('scroll'));
                        }
                    }
                }
            """)
            time.sleep(2)

            # Proof 2: Buffer clearing fix
            clearing_path = "docs/qa-images/mobile_buffer_clearing_388.png"
            page.screenshot(path=clearing_path)
            print(f"Saved {clearing_path}")

            browser.close()

    finally:
        print("Shutting down server...")
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        process.wait()


if __name__ == "__main__":
    main()
