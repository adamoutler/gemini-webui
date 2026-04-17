import pytest
import os
import time
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="function")
def page(server, playwright):
    p = playwright
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1280, "height": 800})

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
def test_e2e_smart_search_ordering(page, test_data_dir, playwright):
    """
    Test E2E smart search ordering by mocking an extensive directory structure.
    It simulates typing in the UI, verifies the dropdown, and checks priority logic.
    """
    # 1. Create real files in the workspace directory to mock an extensive directory structure
    workspace_dir = os.path.join(test_data_dir, "workspace")
    os.makedirs(workspace_dir, exist_ok=True)

    files_to_create = [
        "app.py",
        "src/app.py",
        "tests/test_app.py",
        "myapp/main.py",
        "other/file.txt",
    ]

    for f_path in files_to_create:
        full_path = os.path.join(workspace_dir, f_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
            f.write("mock content")

    # 2. Start a local session to ensure we have an active terminal
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

    # 3. Open Files where the download input is located
    page.locator('button:has-text("Files")').click()

    download_input = page.locator("#workspace-download-filename")
    expect(download_input).to_be_visible()

    # Wait a bit for update_file_cache to complete in the background thread
    time.sleep(2)

    # 4. Type "app" in the download input to trigger smart search
    download_input.fill("app")

    # 5. Assert the dropdown appears
    dropdown = page.locator("#autocomplete-results")
    expect(dropdown).to_be_visible(timeout=15000)

    # 6. Verify results are correctly prioritized according to smart search logic
    items = page.locator(".autocomplete-item")

    # Wait for the first result to appear to ensure dropdown is populated
    expect(items.first).to_be_visible(timeout=15000)

    # Expected order for "app" query:
    # 1. ./app.py (score 80, len 8)
    # 2. ./src/app.py (score 80, len 12)
    # 3. ./tests/test_app.py (score 50, len 19)
    # 4. ./myapp/ (score 25, len 9)
    # 5. ./myapp/main.py (score 25, len 15)

    # We will poll since it might take a moment to sort and filter correctly
    expect(items.nth(0)).to_have_text("./app.py", timeout=15000)
    expect(items.nth(1)).to_have_text("./src/app.py", timeout=15000)
    expect(items.nth(2)).to_have_text("./tests/test_app.py", timeout=15000)
    expect(items.nth(3)).to_have_text("./myapp/", timeout=15000)
    expect(items.nth(4)).to_have_text("./myapp/main.py", timeout=15000)
