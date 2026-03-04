import pytest
from playwright.sync_api import sync_playwright, expect

# Individual test execution MUST NOT exceed 20 seconds.
MAX_TEST_TIME = 20.0

@pytest.fixture(scope="function")
def mobile_page(server):
    with sync_playwright() as p:
        # Emulate Pixel 5
        device = p.devices['Pixel 5']
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**device)
        page = context.new_page()
        page.goto(server, timeout=15000)
        page.wait_for_selector(".launcher, .terminal-instance", state="attached", timeout=15000)
        yield page
        context.close()
        browser.close()

@pytest.mark.timeout(20)
def test_mobile_text_selection_overlay(mobile_page):
    """Verify that the mobile text selection overlay is populated on touchstart."""
    # Ensure launcher is loaded
    mobile_page.wait_for_selector(".launcher", timeout=10000)
    
    # Click "Start New" specifically in the launcher connection card
    start_new_btn = mobile_page.locator(".connection-card .primary:has-text('Start New')").first
    start_new_btn.click()
    
    # Wait for terminal instance to be created
    mobile_page.wait_for_selector(".terminal-instance", timeout=10000)
    
    # Wait for terminal buffer to contain rendered text
    mobile_page.wait_for_function("""() => {
        const terminal = document.querySelector('.terminal-instance');
        return terminal && terminal.textContent.trim().length > 0;
    }""", timeout=10000)
    
    # Ensure overlay exists
    overlay = mobile_page.locator(".mobile-selection-overlay")
    expect(overlay.first).to_be_attached(timeout=5000)
    
    # Trigger a touchstart event to populate the overlay by tapping on it
    proxy = mobile_page.locator(".mobile-scroll-proxy").first
    proxy_box = proxy.bounding_box()
    mobile_page.touchscreen.tap(proxy_box["x"] + 10, proxy_box["y"] + 10)
    
    # Check if the overlay now has text content from the terminal
    mobile_page.wait_for_function("""() => {
        const overlay = document.querySelector('.mobile-selection-overlay');
        return overlay && overlay.textContent.trim().length > 0;
    }""", timeout=5000)

    text_content = overlay.first.text_content()
    assert text_content is not None
    assert len(text_content.strip()) > 0

@pytest.mark.timeout(20)
def test_mobile_quick_tap_focus(mobile_page):
    """Verify that a quick tap clears selection and focuses the terminal's textarea."""
    # Ensure launcher is loaded
    mobile_page.wait_for_selector(".launcher", timeout=10000)
    
    # Click "Start New" specifically in the launcher connection card
    start_new_btn = mobile_page.locator(".connection-card .primary:has-text('Start New')").first
    start_new_btn.click()
    
    # Wait for terminal instance to be created
    mobile_page.wait_for_selector(".terminal-instance", timeout=10000)
    
    # Wait for mobile selection overlay to be attached
    mobile_page.wait_for_selector(".mobile-selection-overlay", state="attached", timeout=10000)
    
    # Wait for terminal buffer to contain rendered text
    mobile_page.wait_for_function("""() => {
        const terminal = document.querySelector('.terminal-instance');
        // xterm renders content in .xterm-rows or simply has textContent if using DOM renderer
        return terminal && terminal.textContent.trim().length > 0;
    }""", timeout=10000)
    
    # Manually trigger a selection to clear later
    mobile_page.evaluate("""() => {
        const overlay = document.querySelector('.mobile-selection-overlay');
        if (overlay) {
            overlay.textContent = 'dummy text';
            const range = document.createRange();
            range.selectNodeContents(overlay);
            const selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(range);
        }
    }""")
    
    # Verify selection is NOT empty before tap
    selection_length_before = mobile_page.evaluate("window.getSelection().toString().length")
    assert selection_length_before > 0
    
    # Simulate a quick tap on the proxy
    proxy = mobile_page.locator(".mobile-scroll-proxy").first
    proxy_box = proxy.bounding_box()
    
    # Trigger a real tap
    mobile_page.touchscreen.tap(proxy_box["x"] + 50, proxy_box["y"] + 50)
    
    # Verify selection is cleared FIRST (this confirms touchend RAN)
    mobile_page.wait_for_function("window.getSelection().toString().length === 0", timeout=5000)

    # Verify textarea is focused (it should happen after touchend)
    textarea = mobile_page.locator("textarea.xterm-helper-textarea")
    expect(textarea.first).to_be_focused(timeout=5000)

@pytest.mark.timeout(20)
def test_mobile_text_selection_sanitization(mobile_page):
    """Verify that the mobile text selection overlay strips box characters and trailing whitespace."""
    # Ensure launcher is loaded
    mobile_page.wait_for_selector(".launcher", timeout=10000)
    
    # Click "Start New" specifically in the launcher connection card
    start_new_btn = mobile_page.locator(".connection-card .primary:has-text('Start New')").first
    start_new_btn.click()
    
    # Wait for terminal instance to be created
    mobile_page.wait_for_selector(".terminal-instance", timeout=10000)
    
    # Wait for terminal buffer to contain rendered text
    mobile_page.wait_for_function("""() => {
        const terminal = document.querySelector('.terminal-instance');
        return terminal && terminal.textContent.trim().length > 0;
    }""", timeout=10000)
    
    # Inject text with box characters and trailing spaces directly via xterm.write
    mobile_page.evaluate("""() => {
        const tab = tabs.find(t => t.id === activeTabId);
        if (tab && tab.term) {
            tab.term.write('BOX\\u2500CHAR   \\r\\n');
        }
    }""")
    
    # Wait for the injection to process
    mobile_page.wait_for_timeout(500)
    
    # Trigger a touchstart event to populate the overlay by tapping on it
    proxy = mobile_page.locator(".mobile-scroll-proxy").first
    proxy_box = proxy.bounding_box()
    mobile_page.touchscreen.tap(proxy_box["x"] + 10, proxy_box["y"] + 10)
    
    # Check if the overlay now has the injected text
    overlay = mobile_page.locator(".mobile-selection-overlay").first
    expect(overlay).to_contain_text("BOX", timeout=5000)
    text_content = overlay.text_content()
    
    assert text_content is not None
    
    # Assert that box drawing characters are removed (replaced by space or empty string)
    assert "\u2500" not in text_content
    # Depending on exactly how app.js replaces it, it's either empty string or space. 
    # In app.js: `.replace(/[\u2500-\u257F]/g, ' ')` so it becomes a space.
    assert "BOX CHAR" in text_content
    
    # Assert no line ends with trailing spaces
    lines = text_content.split("\\n")
    for line in lines:
        if line.startswith("BOX"):
            # The line should not end with spaces
            assert not line.endswith(" "), f"Line has trailing spaces: '{line}'"

