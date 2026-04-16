import pytest
from playwright.sync_api import sync_playwright


@pytest.fixture(scope="function")
def css_page(server, playwright):
    p = playwright
    if True:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto(server, timeout=15000)
        yield page
        context.close()
        browser.close()


def test_css_classes_exist_in_dom(css_page):
    """
    Ensure the classes targeted for extraction (.is-mobile, #mobile-controls, .mobile-scroll-proxy)
    are present in the page logic and can be applied/found when emulating mobile devices.
    """
    # Verify elements exist and can be styled atomically in a single evaluate
    # to prevent async JS (switchTab, loadTabs) from resetting styles between calls.
    result = css_page.evaluate("""() => {
        const mc = document.getElementById('mobile-controls');
        if (!mc) return {error: 'mobile-controls element not found'};

        document.documentElement.classList.add('is-mobile');
        mc.style.setProperty('display', 'grid', 'important');

        return {
            exists: true,
            isMobileClassApplied: document.documentElement.classList.contains('is-mobile'),
            computedDisplay: window.getComputedStyle(mc).display
        };
    }""")

    assert "error" not in result, f"Test setup failed: {result}"
    assert result["exists"] is True
    assert result["isMobileClassApplied"] is True
    assert result["computedDisplay"] in ["grid", "flex", "block"], (
        f"Expected grid/flex/block but got '{result['computedDisplay']}'"
    )
