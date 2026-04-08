import pytest
from playwright.sync_api import sync_playwright


def run_proof():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 375, "height": 800},
            is_mobile=True,
            has_touch=True,
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
        )
        page = context.new_page()
        page.goto("http://localhost:5000")

        # Wait for app load
        page.wait_for_timeout(2000)

        # Start a session to ensure UI is fully active
        page.click("text=Start New")
        page.wait_for_selector(".terminal-instance", timeout=10000)

        # Simulate keyboard opening on iOS Safari
        # The visual viewport height drops to 400, and it scrolls down to offset 300
        page.evaluate("""() => {
            if (window.appVisualViewport) {
                Object.defineProperty(window.appVisualViewport, 'height', { get: () => 400 });
                Object.defineProperty(window.appVisualViewport, 'offsetTop', { get: () => 300 });

                if (window.visualViewport) {
                    window.visualViewport.dispatchEvent(new Event('resize'));
                    window.visualViewport.dispatchEvent(new Event('scroll'));
                }
            }
        }""")

        page.wait_for_timeout(500)

        # Check where the mobile controls are relative to the visual viewport
        controls_rect = page.evaluate("""() => {
            const controls = document.getElementById("mobile-controls");
            const rect = controls.getBoundingClientRect();
            // In layout viewport coordinates
            return { top: rect.top, bottom: rect.bottom };
        }""")

        transform = page.evaluate("document.body.style.transform")

        # The visual viewport is from Y=300 to Y=700 (offsetTop=300, height=400)
        # If the controls are at bottom of body (which is height 400, transform Y=300),
        # they will be at layout Y=700.

        print("Controls rect:", controls_rect)
        print("Body transform:", transform)

        page.screenshot(path="public/qa-screenshots/visual_viewport_after.png")

        with open("docs/qa-images/visual_viewport_proof.txt", "w") as f:
            f.write(f"Controls layout coordinates: {controls_rect}\n")
            f.write(f"Body transform: {transform}\n")
            if controls_rect["bottom"] == 700:
                f.write(
                    "Proof: The controls are at the bottom of the visual viewport (Y=700), perfectly nailed to the virtual keyboard!\n"
                )
            else:
                f.write(
                    f"Proof: The controls are incorrectly positioned at {controls_rect['bottom']}!\n"
                )

        browser.close()


if __name__ == "__main__":
    run_proof()
