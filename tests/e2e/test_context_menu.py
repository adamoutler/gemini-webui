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
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
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
        "() => { if (globalThis.globalState && globalThis.globalState.tabs && globalThis.globalState.tabs[0]) { globalThis.globalState.tabs[0].term.selectAll(); } }"
    )
    page.wait_for_timeout(500)

    # 4. Right click on terminal
    page.locator(".terminal").click(button="right")

    # 5. Expect context menu
    context_menu = page.locator("#desktop-context-menu")
    expect(context_menu).to_be_visible(timeout=10000)

    # Check terminal selection before copy
    term_selection = page.evaluate(
        "() => globalThis.globalState.tabs[0].term.getSelection()"
    )
    print(f"TERMINAL SELECTION: '{term_selection}'")

    # 6. Click Copy and verify clipboard
    page.locator("#ctx-copy").click()
    page.wait_for_timeout(500)

    clipboard_text = page.evaluate("navigator.clipboard.readText()")
    assert "Hello" in clipboard_text

    page.screenshot(path="docs/qa-images/desktop_context_menu_selection_proof.png")


@pytest.mark.timeout(60)
def test_mobile_context_menu_does_not_override_native(page, server, playwright):
    # Set up mobile context
    device = playwright.devices["Pixel 5"]
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(**device)
    mobile_page = context.new_page()
    mobile_page.goto(f"{server}/")

    # Ensure mobile class is present
    expect(mobile_page.locator("html")).to_have_class("is-mobile", timeout=10000)

    expect(mobile_page.get_by_text("Select a Connection").first).to_be_visible(
        timeout=10000
    )

    # Start a local session
    btns = mobile_page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=10000)
    btns.first.click()

    # Wait for terminal
    expect(mobile_page.locator(".terminal")).to_be_visible(timeout=10000)

    # Dispatch context menu event (simulating long press natively handled by browser)
    mobile_page.evaluate(
        '() => document.querySelector(".terminal").dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true, button: 2 }))'
    )

    # The custom desktop context menu should NOT appear on mobile
    context_menu = mobile_page.locator("#desktop-context-menu")
    expect(context_menu).to_be_hidden()

    # Output some text and select it to test selection mode
    mobile_page.evaluate(
        "() => { if (globalThis.globalState && globalThis.globalState.tabs && globalThis.globalState.tabs[0]) { globalThis.globalState.tabs[0].term.write('Hello Mobile'); } }"
    )
    mobile_page.wait_for_timeout(500)
    mobile_page.evaluate(
        "() => { if (globalThis.globalState && globalThis.globalState.tabs && globalThis.globalState.tabs[0]) { globalThis.globalState.tabs[0].term.selectAll(); } }"
    )
    mobile_page.wait_for_timeout(500)

    mobile_page.evaluate(
        '() => document.querySelector(".terminal").dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true, button: 2 }))'
    )
    expect(context_menu).to_be_hidden()

    mobile_page.screenshot(path="docs/qa-images/mobile_context_menu_native_proof.png")

    context.close()
    browser.close()
