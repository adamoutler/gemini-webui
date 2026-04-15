import pytest
from playwright.sync_api import expect, sync_playwright
import time


@pytest.fixture(scope="function")
def mobile_page(server, playwright):
    p = playwright
    if True:
        iphone_12 = p.devices["iPhone 12"]
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**iphone_12)
        page = context.new_page()
        page.set_default_timeout(60000)
        page.goto(server, timeout=15000)
        page.wait_for_selector(
            ".launcher, .terminal-instance", state="attached", timeout=15000
        )
        yield page
        context.close()
        browser.close()


def get_terminal_text(page):
    return page.evaluate(
        "() => { const tab = tabs.find(t => t.id === activeTabId); return (tab && tab.term) ? Array.from({length: tab.term.buffer.active.length}).map((_, i) => tab.term.buffer.active.getLine(i)?.translateToString().trimEnd()).filter(l => l.length > 0).join('\\n') : ''; }"
    )


@pytest.mark.timeout(60)
def test_mobile_extension_rule_parser(mobile_page):
    mobile_page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
    mobile_page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
    btns = mobile_page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()

    expect(mobile_page.locator(".xterm-screen")).to_be_visible(timeout=15000)
    time.sleep(1)

    # Inject a custom rule into the active tab's rule parser
    mobile_page.evaluate("""
        () => {
            const tab = tabs.find(t => t.id === activeTabId);
            if (tab && tab.mobileProxy && tab.mobileProxy.ruleParser) {
                console.log("Rule Parser found, registering rule.");
                class TestRule extends InputRule {
                    handleEvent(event, context) {
                        console.log("Event type: " + event.type + " data: " + event.data);
                        if (event.type === 'input' && event.data === 'x') {
                            console.log("Intercepting x");
                            context.emitToTerminal('Z');
                            context.getProxyInput().value = '';
                            return true; // prevent default
                        }
                        return false;
                    }
                }
                tab.mobileProxy.ruleParser.registerRule(new TestRule());
            } else {
                console.log("Could not find rule parser", !!tab, !!(tab&&tab.mobileProxy), !!(tab&&tab.mobileProxy&&tab.mobileProxy.ruleParser));
            }
        }
    """)

    textarea = mobile_page.locator(".mobile-text-area")
    textarea.focus()

    # Normal typing should work (fallback)
    textarea.evaluate(
        "el => { el.value = 'a'; el.dispatchEvent(new InputEvent('input', {data: 'a'})); }"
    )
    mobile_page.keyboard.press("Enter")
    time.sleep(0.5)

    # The rule should intercept 'x' and send 'Z'
    textarea.evaluate(
        "el => { el.value = 'x'; el.dispatchEvent(new InputEvent('input', {data: 'x'})); }"
    )
    mobile_page.keyboard.press("Enter")
    time.sleep(0.5)

    text = get_terminal_text(mobile_page)
    # The terminal echos what we send.
    assert "You said: a" in text
    assert "You said: Z" in text
    assert "You said: x" not in text
