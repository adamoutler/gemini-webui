# Ticket 188: Implement full color properly
import pytest
import time
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="function")
def page(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(120000)
        page.goto(server)
        page.wait_for_selector(".launcher, .terminal-instance", state="attached")
        yield page
        context.close()
        browser.close()


@pytest.mark.timeout(120)
def test_full_color_logo(page, server):
    # Start a fresh local session which prints the Gemini logo
    btns = page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=15000)
    print("click new tab")
    btns.first.click()

    print("wait xterm-screen")
    expect(page.locator(".xterm-screen")).to_be_visible(timeout=15000)
    time.sleep(2)  # wait for term render and logo printing

    # Trigger TRUECOLOR output
    print("type TRUECOLOR")
    page.keyboard.type("TRUECOLOR\n")
    time.sleep(2)  # wait for truecolor render

    # Share session
    print("click share session")
    page.locator("#share-session-btn").click()
    print("wait share-modal")
    expect(page.locator("#share-modal")).to_be_visible(timeout=15000)
    time.sleep(1)

    # Select full color theme
    print("click confirm")
    page.locator("#confirm-share-btn").click()

    print("wait share-result")
    expect(page.locator("#share-result")).to_be_visible(timeout=15000)
    link_input = page.locator("#share-link-input")
    expect(link_input).to_be_visible()

    val = link_input.input_value()

    # Navigate to the generated link
    new_page = page.context.new_page()
    new_page.set_default_timeout(120000)
    print("goto share link")
    new_page.goto(val)

    print("wait new page terminal wrapper")
    expect(new_page.locator(".terminal-wrapper")).to_be_visible(timeout=15000)
    time.sleep(1)

    screenshot_path = "public/qa-screenshots/test_share_full_color_logo.png"
    import os

    os.makedirs("public/qa-screenshots", exist_ok=True)
    new_page.screenshot(path=screenshot_path)

    # Analyze elements with inline color styles
    # We expect multiple different colors because the Gemini logo is colorful
    colored_spans = new_page.locator('span[style*="color"]')
    count = colored_spans.count()
    assert (
        count > 0
    ), "No explicitly colored spans found. The Full Color theme is not preserving colors."

    colors_found = set()
    for i in range(count):
        style = colored_spans.nth(i).get_attribute("style")
        if style and "color:" in style:
            # Extract the color value
            import re

            m = re.search(r"color:\s*([^;]+)", style)
            if m:
                color_val = m.group(1).strip()
                colors_found.add(color_val)
                # Assert that the color is a valid hex code if it comes from TRUECOLOR (rgb conversion)
                if color_val.startswith("#"):
                    assert len(color_val) in (4, 7), f"Invalid hex color: {color_val}"

    print(f"Colors found: {colors_found}")
    # The logo uses at least 3 distinct colors usually, plus our TRUECOLOR #ff5733, #33ff57, #5733ff, etc.
    assert any(
        c.startswith("#") for c in colors_found
    ), "No hex codes (with # symbol) found in the serialized HTML output."

    new_page.close()
