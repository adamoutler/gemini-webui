import pytest
import os
from playwright.sync_api import sync_playwright, expect


def run_test_with_viewport(server, width, height, expect_visible, playwright):
    p = playwright
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
    errors = []
    page.on("pageerror", lambda err: errors.append(err))
    page.goto(server, timeout=15000)
    page.wait_for_selector(
        ".launcher, .terminal-instance", state="attached", timeout=15000
    )

    expect(page.get_by_text("Select a Connection").first).to_be_visible(timeout=5000)

    # Start a fresh local session
    btns = page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=5000)
    btns.first.click()

    # Wait for terminal to appear
    expect(page.locator("#active-connection-info")).to_be_visible(timeout=5000)

    # Wait for terminal to be ready
    page.wait_for_selector(".xterm-helper-textarea", state="attached", timeout=10000)

    textarea = page.locator(".xterm-helper-textarea").first

    # Inject a massive block of text with newlines simulating STT composition
    long_text = "Line 1\n" + "Line 2\n" * 50 + "Line 50"

    # Simulate Voice Typing (STT)
    textarea.evaluate(
        "(el) => { el.dispatchEvent(new CompositionEvent('compositionstart')); }"
    )
    textarea.evaluate(
        f"(el) => {{ el.value = `{long_text}`; el.dispatchEvent(new Event('input', {{ bubbles: true, inputType: 'insertCompositionText' }})); }}"
    )
    textarea.evaluate(
        f"(el) => {{ el.dispatchEvent(new CompositionEvent('compositionend', {{ data: `{long_text}` }})); }}"
    )

    # Get bounding box of textarea
    box = textarea.bounding_box()
    viewport = page.viewport_size

    print(f"Textarea Bounding Box: {box}")
    print(f"Viewport: {viewport}")

    screenshot_path = (
        f"/tmp/gemwe-stt-{width}x{height}_{os.environ.get('BUILD_NUMBER', 'local')}.png"
    )
    page.screenshot(path=screenshot_path)
    print(
        f"Empirical Evidence: Saved STT textarea screenshot to {screenshot_path}. Textarea dims: {box['width']}x{box['height']}, Viewport: {viewport['width']}x{viewport['height']}"
    )

    if expect_visible:
        expect(textarea).to_be_visible()
        assert box["height"] > 16, f"Textarea height did not expand: {box['height']}"
        assert (
            box["width"] <= viewport["width"]
        ), f"Textarea exceeds viewport width: {box['width']} > {viewport['width']}"
        assert (
            box["height"] <= viewport["height"]
        ), f"Textarea exceeds viewport height: {box['height']} > {viewport['height']}"
    else:
        expect(textarea).not_to_be_visible()
        assert (
            box["height"] == 0
        ), f"Textarea height should be 0 on desktop, but got: {box['height']}"
        assert (
            box["width"] == 0
        ), f"Textarea width should be 0 on desktop, but got: {box['width']}"

    # Now try to submit (press enter)
    page.keyboard.press("Enter")

    # Give it a bit to process
    page.wait_for_timeout(1000)

    assert len(errors) == 0, f"Page threw errors: {errors}"
    context.close()
    browser.close()


@pytest.mark.timeout(30)
def test_stt_multiline_overflow_mobile(server, playwright):
    # Test mobile view (visible)
    run_test_with_viewport(server, 375, 667, expect_visible=True, playwright=playwright)


@pytest.mark.timeout(30)
def test_stt_multiline_overflow_desktop(server, playwright):
    # Test desktop view (hidden)
    run_test_with_viewport(
        server, 800, 600, expect_visible=False, playwright=playwright
    )
