import pytest
import os
import time
from playwright.sync_api import sync_playwright, expect


@pytest.mark.timeout(60)
def test_ui_tab_management(server, playwright):
    p = playwright
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
    page.on("pageerror", lambda err: print(f"ERROR: {err}"))

    page.goto(server)

    # Wait for the app to load and the connection card to be visible
    expect(page.locator(".connection-card").first).to_be_visible(timeout=15000)

    # Click "Start New" on the first connection (Local)
    page.locator('button:has-text("Start New")').first.click()

    # Wait for terminal to be active
    expect(page.locator(".tab-instance.active .xterm")).to_be_visible(timeout=15000)

    # Locate the active tab
    active_tab = page.locator(".tab.active")

    # Right click the tab to open context menu
    active_tab.click(button="right")

    # Expect the context menu to appear
    context_menu = page.locator("#tab-context-menu")
    expect(context_menu).to_be_visible(timeout=5000)

    # Click "Rename Tab"
    # We need to handle the window.prompt that "Rename Tab" creates
    page.on("dialog", lambda dialog: dialog.accept("My Custom Tab Name"))

    page.locator("div.context-menu-item", has_text="Rename Tab").click()

    # The tab title should update to the new name
    expect(active_tab.locator("span").first).to_have_text(
        "My Custom Tab Name", timeout=5000
    )

    # Take a screenshot for proof
    os.makedirs("docs/qa-images", exist_ok=True)
    page.screenshot(path="docs/qa-images/tab_renamed_proof.png")
    print("Proof screenshot saved to docs/qa-images/tab_renamed_proof.png")

    # Verify that a backend update_title event does NOT overwrite the userNamed title
    # We can simulate the backend sending a new title by executing JS
    page.evaluate("""() => {
        const tab = tabs.find(t => t.id === activeTabId);
        // Simulate xterm.js emitting a title change event
        if (tab && tab.term) {
            tab.term._core._onTitleChange.fire("Malicious Auto Name");
        }
    }""")

    # Wait a bit to ensure the title did not change
    page.wait_for_timeout(1000)

    # The title should still be the custom one
    expect(active_tab.locator("span").first).to_have_text(
        "My Custom Tab Name", timeout=5000
    )

    # Close browser
    context.close()
    browser.close()
