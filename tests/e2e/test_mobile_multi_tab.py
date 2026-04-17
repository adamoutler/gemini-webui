import pytest
from playwright.sync_api import expect, sync_playwright
import time


@pytest.fixture(scope="function")
def android_page(server, playwright):
    p = playwright
    pixel = p.devices["Pixel 5"]
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(**pixel)
    page = context.new_page()
    page.set_default_timeout(60000)
    page.goto(server, timeout=15000)
    page.wait_for_selector(
        ".launcher, .terminal-instance", state="attached", timeout=15000
    )
    yield page
    context.close()
    browser.close()


def get_terminal_text(page, tab_index):
    return page.evaluate(f"""
        (() => {{
            const activeTab = tabs[{tab_index}];
            return (activeTab && activeTab.term) ? Array.from({{length: activeTab.term.buffer.active.length}}).map((_, i) => activeTab.term.buffer.active.getLine(i)?.translateToString().trimEnd()).filter(l => l.length > 0).join('\\n') : '';
        }})()
    """)


@pytest.mark.timeout(60)
def test_mobile_multi_tab_input(android_page, playwright):
    try:
        # Start Tab 1
        btns = android_page.locator('.tab-instance.active button:has-text("Start New")')
        expect(btns.first).to_be_visible(timeout=15000)
        btns.first.click()

        expect(android_page.locator(".xterm-screen")).to_be_visible(timeout=15000)
        time.sleep(1)

        # Type in Tab 1
        print("Typing in Tab 1")
        tab1_id = android_page.evaluate("window.activeTabId")
        android_page.evaluate(
            f"() => {{ const el = document.getElementById('terminal-input-mobile-{tab1_id}'); el.focus(); el.value = 'hello'; el.dispatchEvent(new InputEvent('input', {{data: 'o'}})); }}"
        )
        android_page.keyboard.press("Enter")
        time.sleep(1)

        # Verify Tab 1 has text
        print("Verifying Tab 1")
        text1 = get_terminal_text(android_page, 0)
        assert "hello" in text1

        # Open Tab 2
        print("Opening Tab 2")
        android_page.locator("#new-tab-btn").click()
        time.sleep(1)
        btns = android_page.locator('.tab-instance.active button:has-text("Start New")')
        expect(btns.first).to_be_visible(timeout=15000)
        btns.first.click()

        expect(
            android_page.locator(".tab-instance.active .xterm-screen")
        ).to_be_visible(timeout=15000)
        time.sleep(1)

        # Type in Tab 2
        print("Typing in Tab 2")
        tab2_id = android_page.evaluate("window.activeTabId")
        android_page.evaluate(
            f"() => {{ const el = document.getElementById('terminal-input-mobile-{tab2_id}'); el.focus(); el.value = 'world'; el.dispatchEvent(new InputEvent('input', {{data: 'd'}})); }}"
        )
        android_page.keyboard.press("Enter")
        time.sleep(1)

        # Verify Tab 2 has text but Tab 1 doesn't have 'world'
        print("Verifying Tab 2")
        text1_after = get_terminal_text(android_page, 0)
        text2 = get_terminal_text(android_page, 1)

        assert "hello" in text1_after
        assert "world" not in text1_after
        assert "world" in text2

        # Switch back to Tab 1
        print("Switching back to Tab 1")
        android_page.evaluate("switchTab(tabs[0].id)")
        time.sleep(1)

        # Type in Tab 1 again
        print("Typing in Tab 1 again")
        android_page.evaluate(
            f"() => {{ const el = document.getElementById('terminal-input-mobile-{tab1_id}'); el.focus(); el.value = 'again'; el.dispatchEvent(new InputEvent('input', {{data: 'n'}})); }}"
        )
        android_page.keyboard.press("Enter")
        time.sleep(1)

        # Verify Tab 1 gets 'again', Tab 2 doesn't
        print("Verifying Tab 1 again")
        text1_final = get_terminal_text(android_page, 0)
        text2_final = get_terminal_text(android_page, 1)

        assert "again" in text1_final
        assert "again" not in text2_final

    except Exception as e:
        import traceback

        traceback.print_exc()
        raise e
