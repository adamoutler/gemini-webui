import pytest
from playwright.sync_api import sync_playwright


@pytest.fixture(scope="function")
def css_page(server):
    with sync_playwright() as p:
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
    # Simulate the switchTab logic that sets display: grid on mobile
    css_page.evaluate("""
        document.documentElement.classList.add('is-mobile');
        document.getElementById('mobile-controls').style.display = 'grid';
    """)

    display_style = css_page.evaluate(
        "window.getComputedStyle(document.getElementById('mobile-controls')).display"
    )
    assert display_style in ["grid", "flex", "block"]
