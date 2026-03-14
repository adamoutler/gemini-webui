import pytest
from playwright.sync_api import sync_playwright


@pytest.fixture(scope="function")
def page(server):
    with sync_playwright() as p:
        iphone = p.devices["iPhone 13"]
        browser = p.chromium.launch()
        context = browser.new_context(**iphone)

        page = context.new_page()
        page.set_default_timeout(60000)
        page.goto(server, timeout=15000)
        yield page
        context.close()
        browser.close()


def test_overlay_box_colors_match_terminal_theme(page):
    page.locator('.tab-instance.active button:has-text("Start New")').first.click()
    page.wait_for_selector(".mobile-proxy-input", state="attached", timeout=15000)

    textarea = page.locator(".mobile-proxy-input").first

    # Simulate Voice Typing (STT) to invoke overlay
    long_text = "Testing STT"
    textarea.evaluate(
        "(el) => { el.dispatchEvent(new CompositionEvent('compositionstart')); }"
    )
    textarea.evaluate(
        f"(el) => {{ el.value = `{long_text}`; el.dispatchEvent(new Event('input', {{ bubbles: true, inputType: 'insertCompositionText' }})); }}"
    )

    # Get computed styles
    colors = page.evaluate("""() => {
        const textarea = document.querySelector(".mobile-proxy-input");
        const style = window.getComputedStyle(textarea);
        return {
            bg: style.backgroundColor,
            fg: style.color
        };
    }""")
    term_style = page.evaluate("""() => {
        const terminal = document.querySelector(".terminal");
        if (!terminal) return { bg: 'rgb(0, 0, 0)', fg: 'rgb(212, 212, 212)' };
        const style = window.getComputedStyle(terminal);
        return { bg: style.backgroundColor, fg: style.color };
    }""")

    # Check that it's definitively not black and white
    assert colors["bg"] != "rgb(0, 0, 0)", "Regression: Background is stark black!"
    assert (
        colors["fg"] != "rgb(255, 255, 255)"
    ), "Regression: Foreground is stark white!"

    # Check that it matches the transparent background and dynamic foreground
    assert colors["bg"] in [
        "rgba(0, 0, 0, 0)",
        "transparent",
    ], f"Expected transparent background, got {colors['bg']}"
    assert (
        colors["fg"] == term_style["fg"]
    ), f"Expected terminal foreground {term_style['fg']}, got {colors['fg']}"
