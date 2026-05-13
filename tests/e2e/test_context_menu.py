import pytest
from playwright.sync_api import expect


@pytest.mark.timeout(60)
def test_desktop_context_menu(page, server, playwright):
    page.on("console", lambda msg: print(f"BROWSER CONSOLE: {msg.text}"))
    page.on("pageerror", lambda err: print(f"BROWSER ERROR: {err.message}"))
    # 1. Load the page
    page.goto(f"{server}/")
    expect(page.get_by_text("Select a Connection").first).to_be_visible(timeout=10000)

    # 2. Start a local session
    btns = page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=10000)
    btns.first.click()

    # Wait for terminal
    expect(page.locator(".terminal")).to_be_visible(timeout=10000)

    # 3. Right click on terminal
    page.locator(".terminal").click(button="right")

    # 4. Expect context menu
    context_menu = page.locator("#desktop-context-menu")
    expect(context_menu).to_be_visible(timeout=10000)

    page.screenshot(path="docs/qa-images/desktop_context_menu_proof.png")


@pytest.mark.timeout(60)
def test_desktop_context_menu_with_selection(page, server, playwright):
    page.on("console", lambda msg: print(f"BROWSER CONSOLE: {msg.text}"))
    page.on("pageerror", lambda err: print(f"BROWSER ERROR: {err.message}"))
    # 1. Load the page
    page.goto(f"{server}/")
    expect(page.get_by_text("Select a Connection").first).to_be_visible(timeout=10000)

    # 2. Start a local session
    btns = page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=10000)
    btns.first.click()

    # Wait for terminal
    expect(page.locator(".terminal")).to_be_visible(timeout=10000)

    # 3. Output some text and select it
    page.evaluate(
        "() => { if (globalThis.globalState && globalThis.globalState.tabs && globalThis.globalState.tabs[0]) { globalThis.globalState.tabs[0].term.write('Hello World'); } }"
    )
    page.wait_for_timeout(500)
    page.evaluate(
        "() => { if (globalThis.globalState && globalThis.globalState.tabs && globalThis.globalState.tabs[0]) { globalThis.globalState.tabs[0].term.select(0, 0, 5); } }"
    )
    page.wait_for_timeout(500)

    # 4. Right click on terminal
    page.locator(".terminal").click(button="right")

    # 5. Expect context menu
    context_menu = page.locator("#desktop-context-menu")
    expect(context_menu).to_be_visible(timeout=10000)

    page.screenshot(path="docs/qa-images/desktop_context_menu_selection_proof.png")
