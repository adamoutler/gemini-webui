import pytest
from playwright.sync_api import sync_playwright

MAX_TEST_TIME = 60.0


@pytest.fixture(scope="function")
def page(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(permissions=["notifications"])
        page = context.new_page()
        page.set_default_timeout(60000)
        page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
        page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
        page.goto(server)
        page.wait_for_selector(".launcher, .terminal-instance", state="attached")
        yield page
        context.close()
        browser.close()


@pytest.mark.timeout(60)
def test_wake_lock(page):
    """Verify Wake Lock API is invoked when a tab title changes to 'Working' and released on 'Ready'."""
    # Mock the wakeLock API in the browser
    page.evaluate("""() => {
        window.mockWakeLockState = { active: false, released: false };
        let currentLock = null;
        Object.defineProperty(navigator, 'wakeLock', {
            value: {
                request: async (type) => {
                    if (type === 'screen') {
                        window.mockWakeLockState.active = true;
                        window.mockWakeLockState.released = false;
                        currentLock = {
                            release: async () => {
                                window.mockWakeLockState.active = false;
                                window.mockWakeLockState.released = true;
                                if (currentLock.onrelease) {
                                    currentLock.onrelease();
                                }
                            },
                            addEventListener: (evt, cb) => {
                                if (evt === 'release') currentLock.onrelease = cb;
                            }
                        };
                        return currentLock;
                    }
                }
            },
            writable: true
        });
    }""")

    # Add a fake tab and trigger updatePageTitle
    page.evaluate("""() => {
        if (typeof tabs !== "undefined") {
            tabs.push({ id: 'test_tab', title: 'Working on task' });
            updatePageTitle();
        }
    }""")

    # Wait a bit for the async wakeLock.request to resolve
    page.wait_for_timeout(500)

    # Check that wake lock was requested
    active = page.evaluate("window.mockWakeLockState.active")
    assert (
        active is True
    ), "Wake Lock should be active when tab title contains 'Working'"

    # Now change to Ready
    page.evaluate("""() => {
        if (typeof tabs !== "undefined") {
            const t = tabs.find(tab => tab.id === 'test_tab');
            if (t) t.title = "Ready";
            updatePageTitle();
        }
    }""")

    page.wait_for_timeout(500)

    # Check that wake lock was released
    active = page.evaluate("window.mockWakeLockState.active")
    released = page.evaluate("window.mockWakeLockState.released")
    assert active is False, "Wake Lock should not be active when tab title is 'Ready'"
    assert released is True, "Wake Lock should be released when tab title is 'Ready'"
