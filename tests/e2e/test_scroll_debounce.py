import pytest
from playwright.sync_api import sync_playwright


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

            const initialScroll = proxy.scrollTop; // Should be 50000

            // Trigger scroll within bounds
            proxy.scrollTop = 50016;
            proxy.dispatchEvent(new Event('scroll'));

            setTimeout(() => {
                const intermediateScroll = proxy.scrollTop; // Should be 50016

                // Trigger scroll outside bounds
                proxy.scrollTop = 91000;
                proxy.dispatchEvent(new Event('scroll'));

                setTimeout(() => {
                    const finalScroll = proxy.scrollTop; // Should be 50000
                    resolve({
                        initial: initialScroll,
                        intermediate: intermediateScroll,
                        final: finalScroll
                    });
                }, 50);
            }, 50);
        });
    }
    """
    result = mobile_page.evaluate(scroll_script)
    assert (
        result.get("initial") == 50000
    ), f"Expected 50000, got {result.get('initial')}"
    assert (
        result.get("intermediate") == 50016
    ), f"Expected 50016, got {result.get('intermediate')}"
    assert result.get("final") == 50000, f"Expected 50000, got {result.get('final')}"


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
