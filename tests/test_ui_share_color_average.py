import pytest
import time
from playwright.sync_api import sync_playwright, expect
from PIL import Image
import io

def get_average_color(image_bytes):
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    # Resize to 1x1 pixel to easily get the average color
    image = image.resize((1, 1))
    return image.getpixel((0, 0))

def get_luminance(color):
    r, g, b = color
    return 0.299 * r + 0.587 * g + 0.114 * b

@pytest.fixture(scope="function")
def page(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto(server, timeout=15000)
        page.wait_for_selector(".launcher, .terminal-instance", state="attached", timeout=15000)
        yield page
        context.close()
        browser.close()

@pytest.mark.timeout(30)
def test_share_color_averages(page, server):
    # Start a fresh local session
    btns = page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=5000)
    btns.first.click()

    expect(page.locator('.xterm-screen')).to_be_visible(timeout=5000)
    time.sleep(1) # wait for term render

    # Helper function to create a share and get its screenshot
    def get_share_screenshot(theme):
        page.locator('#share-session-btn').click()
        expect(page.locator('#share-modal')).to_be_visible(timeout=5000)
        
        page.locator('#share-theme-select').select_option(theme)
        page.locator('#confirm-share-btn').click()
        
        expect(page.locator('#share-result')).to_be_visible(timeout=5000)
        link_input = page.locator('#share-link-input')
        expect(link_input).to_be_visible()
        
        val = link_input.input_value()
        
        # Navigate to the generated link
        new_page = page.context.new_page()
        new_page.goto(val, timeout=15000)
        
        # wait for content to load
        expect(new_page.locator('.terminal-wrapper')).to_be_visible(timeout=5000)
        time.sleep(1) # wait for styling to settle
        
        body_bg = new_page.evaluate("window.getComputedStyle(document.body).backgroundColor")
        print(f"\\nComputed body background for theme {theme}: {body_bg}")

        screenshot_path = f"public/qa-screenshots/test_share_{theme}.png"
        import os
        os.makedirs("public/qa-screenshots", exist_ok=True)
        screenshot_bytes = new_page.screenshot(path=screenshot_path)
        print(f"\\nSaved screenshot for {theme} mode to {screenshot_path}")
        new_page.close()
        
        # Close modal for next iteration
        page.locator('#share-modal .modal-content span').click()
        return screenshot_bytes

    # Get screenshot for light mode
    light_screenshot = get_share_screenshot('light')
    light_color = get_average_color(light_screenshot)
    light_lum = get_luminance(light_color)
    print(f"\\nLight mode average color: {light_color}, luminance: {light_lum}")

    # Get screenshot for dark mode
    dark_screenshot = get_share_screenshot('dark')
    dark_color = get_average_color(dark_screenshot)
    dark_lum = get_luminance(dark_color)
    print(f"Dark mode average color: {dark_color}, luminance: {dark_lum}")

    # Verify dark is darker than light
    assert dark_lum < light_lum, f"Dark mode ({dark_lum}) should be darker than light mode ({light_lum})"

    # Get screenshot for full mode
    full_screenshot = get_share_screenshot('full')
    full_color = get_average_color(full_screenshot)
    full_lum = get_luminance(full_color)
    print(f"Full mode average color: {full_color}, luminance: {full_lum}")
    
    # After the swap, full mode should behave like the original dark mode, which means it might be dark or look specific based on the terminal's theme.
    # The original "Dark" mode was light content with a dark border, so full_lum should be relatively high.
    assert dark_lum < 100, f"Dark mode luminance ({dark_lum}) should be relatively low (dark)"
    assert light_lum > 150, f"Light mode luminance ({light_lum}) should be relatively high (light)"
    assert full_lum > 150, f"Full mode luminance ({full_lum}) should be relatively high (reflecting previous light content dark mode)"

