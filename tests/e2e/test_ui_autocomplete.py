import pytest
import re
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="function")
def page(server, playwright):
    p = playwright
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()

    page = context.new_page()
    page.set_default_timeout(60000)
    page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
    page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
    page.goto(server, timeout=15000)
    page.wait_for_selector(
        ".launcher, .terminal-instance", state="attached", timeout=15000
    )
    yield page
    context.close()
    browser.close()


@pytest.mark.prone_to_timeout
@pytest.mark.timeout(60)
def test_ui_autocomplete_dropdown(page, server, playwright):
    """Verify the autocomplete dropdown in the download modal works correctly."""
    # 1. Start a local session to ensure we have an active terminal
    btns = page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()

    # Wait for terminal to appear
    expect(page.locator("#active-connection-info")).to_be_visible(timeout=15000)

    # Force the session type to 'ssh' so autocomplete logic triggers
    page.evaluate("""() => {
        const tab = tabs.find(t => t.id === activeTabId);
        if (tab && tab.session) {
            tab.session.type = 'ssh';
        }
    }""")

    # 2. Open Files where the download input is located
    page.locator('button:has-text("Files")').click()

    # 3. Mock the autocomplete API
    def handle_route(route):
        url = route.request.url
        if "q=src%2F" in url or "q=src/" in url:
            route.fulfill(json={"matches": ["src/app.py", "src/config.py"]})
        elif "q=src" in url:
            route.fulfill(json={"matches": ["src/", "src/app.py"]})
        else:
            route.fulfill(json={"matches": []})

    page.route(re.compile(r"/api/sessions/.*/search_files"), handle_route)

    # 4. Type in the download input
    download_input = page.locator("#workspace-download-filename")
    expect(download_input).to_be_visible()

    download_input.fill("src")
    page.evaluate(
        "document.getElementById('workspace-download-filename').dispatchEvent(new Event('input', { bubbles: true }));"
    )
    page.wait_for_timeout(1000)

    # 5. Assert the dropdown appears with items
    dropdown = page.locator("#autocomplete-results")
    expect(dropdown).to_be_visible(timeout=15000)

    items = page.locator(".autocomplete-item")
    expect(items).to_have_count(2)
    expect(items.nth(0)).to_have_text("src/")
    expect(items.nth(1)).to_have_text("src/app.py")

    # 6. Click a directory (ends with '/')
    items.nth(0).click()

    # Assert input value updates
    expect(download_input).to_have_value("src/")

    # Since it ends with '/', it dispatches 'input' event, triggering another search for 'src/'
    # The dropdown should populate with the new mock results
    expect(dropdown).to_be_visible(timeout=15000)
    expect(items).to_have_count(2)
    expect(items.nth(0)).to_have_text("src/app.py")
    expect(items.nth(1)).to_have_text("src/config.py")

    # 7. Click a file (does not end with '/')
    items.nth(0).click()

    # Assert input value updates to the file
    expect(download_input).to_have_value("src/app.py")

    # Assert dropdown hides
    expect(dropdown).not_to_be_visible(timeout=15000)
