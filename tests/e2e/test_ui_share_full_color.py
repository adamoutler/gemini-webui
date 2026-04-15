import pytest
import time
import os
from playwright.sync_api import sync_playwright, expect
from PIL import Image
import io


def count_unique_colors(image_bytes):
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    colors = image.getcolors(maxcolors=1000000)
    # Filter out near-black and near-white/grey backgrounds to only count colored text
    colorful = 0
    for count, (r, g, b) in colors:
        if max(r, g, b) - min(r, g, b) > 30:  # It's a colorful pixel, not grayscale
            colorful += 1
    return colorful


@pytest.fixture(scope="function")
def page(server, playwright):
    p = playwright
    if True:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        page = context.new_page()
        page.set_default_timeout(120000)
        page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
        page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
        page.goto(server, timeout=15000)
        page.wait_for_selector(
            ".launcher, .terminal-instance", state="attached", timeout=15000
        )
        yield page
        context.close()
        browser.close()


def test_share_full_color(page):
    # 1. Start a local session to ensure we have an active terminal
    btns = page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()

    # Wait for the terminal to load and the logo to appear
    expect(page.locator(".xterm-screen")).to_be_visible(timeout=15000)
    time.sleep(2)  # Give it time to render the colored text

    # Click share button
    page.locator("#share-session-btn").click()
    expect(page.locator("#share-modal")).to_be_visible(timeout=15000)
    time.sleep(1)

    page.locator("#confirm-share-btn").click()
    expect(page.locator("#share-result")).to_be_visible(timeout=15000)
    link_input = page.locator("#share-link-input")
    expect(link_input).to_be_visible()

    val = link_input.input_value()

    new_page = page.context.new_page()

    new_page.set_default_timeout(60000)
    new_page.goto(val, timeout=15000)

    # Wait for the share content to load
    expect(new_page.locator(".terminal-wrapper")).to_be_visible(timeout=15000)
    time.sleep(2)  # wait for styling

    # Take screenshot of the shared page
    os.makedirs("public/qa-screenshots", exist_ok=True)
    screenshot_path = "public/qa-screenshots/test_share_full_color_logo.png"
    screenshot_bytes = new_page.screenshot(path=screenshot_path)

    # Analyze colors
    colorful_pixel_count = count_unique_colors(screenshot_bytes)
    print(
        f"\nFound {colorful_pixel_count} unique colorful pixels in the shared Full Color session."
    )

    # Since the logo "GEMINI" is printed with 6 different distinct ANSI colors, there should be many colorful pixels
    assert (
        colorful_pixel_count > 5
    ), f"Expected colorful pixels for the logo, found only {colorful_pixel_count}"
