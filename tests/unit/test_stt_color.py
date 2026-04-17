import pytest
from playwright.sync_api import sync_playwright


@pytest.fixture(scope="function")
def page(server, playwright):
    p = playwright
    iphone = p.devices["iPhone 13"]
    browser = p.chromium.launch()
    context = browser.new_context(**iphone)

    page = context.new_page()
    page.set_default_timeout(60000)
    page.goto(server, timeout=15000)
    yield page
    context.close()
    browser.close()


def test_stt_color(page, playwright):
    page.locator('.tab-instance.active button:has-text("Start New")').first.click()
    page.wait_for_selector(".mobile-text-area", state="attached", timeout=15000)
    textarea = page.locator(".mobile-text-area").first

    # Simulate Voice Typing (STT)
    long_text = "Testing STT"
    textarea.evaluate(
        "(el) => { el.dispatchEvent(new CompositionEvent('compositionstart')); }"
    )
    textarea.evaluate(
        f"(el) => {{ el.value = `{long_text}`; el.dispatchEvent(new Event('input', {{ bubbles: true, inputType: 'insertCompositionText' }})); }}"
    )

    # Check computed style during composition
    style = page.evaluate("""() => {
        const el = document.querySelector(".mobile-text-area");
        const style = window.getComputedStyle(el);
        return { bg: style.backgroundColor, fg: style.color };
    }""")
    print("Computed Styles during STT:", style)

    term_style = page.evaluate("""() => {
        const style = window.getComputedStyle(document.documentElement);
        const termFg = style.getPropertyValue('--terminal-fg').trim() || '#d4d4d4';

        const div = document.createElement('div');
        div.style.color = termFg;
        document.body.appendChild(div);
        const rgbColor = window.getComputedStyle(div).color;
        div.remove();

        return { fg: rgbColor };
    }""")

    assert style["bg"] in [
        "rgba(0, 0, 0, 0)",
        "transparent",
    ], f"Expected transparent background, got {style['bg']}"
    assert (
        style["fg"] == term_style["fg"]
    ), f"Expected {term_style['fg']}, got {style['fg']}"
