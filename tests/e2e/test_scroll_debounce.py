import pytest


@pytest.fixture(scope="function")
def mobile_page(server, playwright):
    p = playwright
    device = p.devices["Pixel 5"]
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(**device)
    page = context.new_page()
    page.goto(server, timeout=15000)
    yield page
    context.close()
    browser.close()


@pytest.mark.timeout(60)
def test_scroll_debounce(mobile_page, playwright):
    mobile_page.wait_for_selector(
        ".launcher, .terminal-instance", state="attached", timeout=15000
    )
    try:
        # Wait longer for the button to appear, as API calls might take time on CI
        mobile_page.wait_for_selector("text=Start New", timeout=10000)
        mobile_page.click("text=Start New")
    except Exception:
        pass
    mobile_page.wait_for_selector(".mobile-scroll-proxy", timeout=10000)

    # Test Momentum-Safe Scroll Logic
    scroll_script = """
    () => {
        return new Promise(resolve => {
            const proxy = document.querySelector('.mobile-scroll-proxy');
            if (!proxy) {
                resolve({ error: "No proxy found" });
                return;
            }

            const initialScroll = proxy.scrollTop; // Should be 0 initially
            const anchor = proxy.style.overflowAnchor;

            // Trigger scroll within bounds
            // Use actual rowHeight or at least 50 to guarantee deltaLines >= 1
            proxy.scrollTop = 50;
            proxy.dispatchEvent(new Event('scroll'));
            setTimeout(() => {
                const intermediateScroll = proxy.scrollTop; // Should be reset to 0 by rAF
                resolve({
                    initial: initialScroll,
                    intermediate: intermediateScroll,
                    anchor: anchor
                });
            }, 50);
        });
    }
    """
    result = mobile_page.evaluate(scroll_script)
    assert (
        result.get("anchor") == "none"
    ), f"Expected anchor to be 'none', got {result.get('anchor')}"
    assert result.get("initial") == 0, f"Expected 0, got {result.get('initial')}"
    assert (
        result.get("intermediate") == 0
    ), f"Expected 0 (reset by rAF), got {result.get('intermediate')}"


@pytest.mark.timeout(60)
def test_resize_observer_debounce(mobile_page, playwright):
    mobile_page.wait_for_selector(
        ".launcher, .terminal-instance", state="attached", timeout=15000
    )
    try:
        # Wait longer for the button to appear, as API calls might take time on CI
        mobile_page.wait_for_selector("text=Start New", timeout=10000)
        mobile_page.click("text=Start New")
    except Exception:
        pass
    mobile_page.wait_for_selector(".mobile-scroll-proxy", timeout=10000)

    # We just ensure rapid resizes don't crash or hang the page.
    # The debouncing ensures that ResizeObserver loop limits are not hit.
    resize_script = """
    () => {
        return new Promise(resolve => {
            const container = document.getElementById('terminal-container');
            for(let i = 0; i < 20; i++) {
                container.style.height = (400 + i) + 'px';
            }
            setTimeout(() => {
                resolve("success");
            }, 200);
        });
    }
    """
    result = mobile_page.evaluate(resize_script)
    assert result == "success"
