import pytest
from playwright.sync_api import Page, expect
import time


@pytest.fixture
def mobile_page(page: Page):
    page.set_viewport_size({"width": 375, "height": 667})
    # Emulate touch device
    page.goto("http://localhost:5001")
    # Ensure it's fully loaded
    page.wait_for_selector("#toolbar")
    return page


def test_mobile_pull_to_refresh_screenshots_and_behavior(mobile_page: Page):
    page = mobile_page

    toolbar = page.locator("#toolbar")
    indicator = page.locator("#ptr-indicator")

    # Helper to simulate touch drag
    def simulate_touch_drag(dx, dy, release=True):
        page.evaluate(f"""
            (async () => {{
                const el = document.getElementById('toolbar');
                const box = el.getBoundingClientRect();
                const startX = box.x + box.width / 2;
                const startY = box.y + box.height / 2;

                const touchStart = new TouchEvent('touchstart', {{
                    touches: [new Touch({{ identifier: 1, target: el, clientX: startX, clientY: startY }})]
                }});
                el.dispatchEvent(touchStart);

                const touchMove = new TouchEvent('touchmove', {{
                    touches: [new Touch({{ identifier: 1, target: el, clientX: startX + {dx}, clientY: startY + {dy} }})],
                    cancelable: true
                }});
                el.dispatchEvent(touchMove);

                if ({str(release).lower()}) {{
                    const touchEnd = new TouchEvent('touchend', {{
                        changedTouches: [new Touch({{ identifier: 1, target: el, clientX: startX + {dx}, clientY: startY + {dy} }})]
                    }});
                    el.dispatchEvent(touchEnd);
                }}
            }})()
        """)

    # Behavioral 1: Horizontal swipe does not trigger
    simulate_touch_drag(dx=100, dy=0)
    expect(indicator).not_to_have_class("ptr-indicator is-pulling", timeout=500)

    # Behavioral 2: Tap does not trigger
    simulate_touch_drag(dx=0, dy=0)
    expect(indicator).not_to_have_class("ptr-indicator is-pulling", timeout=500)

    # Behavioral 3: Releasing before threshold (60)
    # Let's pull down 100 raw pixels -> visualY = 40 (< 60)
    simulate_touch_drag(dx=0, dy=100, release=False)

    # Mid-pull Screenshot
    page.screenshot(path="docs/qa-images/ptr_mid_pull.png")
    expect(indicator).to_have_class("ptr-indicator is-pulling")

    # Release it
    page.evaluate("""
        const el = document.getElementById('toolbar');
        const touchEnd = new TouchEvent('touchend', {
            changedTouches: [new Touch({ identifier: 1, target: el, clientX: 0, clientY: 0 })]
        });
        el.dispatchEvent(touchEnd);
    """)
    # It should hide
    expect(indicator).to_have_class("ptr-indicator is-resetting")

    # Now pull past threshold
    # 200 * 0.4 = 80 visualY (>= 60)
    simulate_touch_drag(dx=0, dy=200, release=False)

    # Ready State Screenshot
    page.wait_for_timeout(100)  # give css a frame
    page.screenshot(path="docs/qa-images/ptr_ready_state.png")
    expect(indicator).to_have_class("ptr-indicator is-pulling is-ready")

    # Release it
    page.evaluate("""
        const el = document.getElementById('toolbar');
        const touchEnd = new TouchEvent('touchend', {
            changedTouches: [new Touch({ identifier: 1, target: el, clientX: 0, clientY: 0 })]
        });
        el.dispatchEvent(touchEnd);
    """)

    # Loading State Screenshot
    page.wait_for_timeout(50)  # immediately after
    page.screenshot(path="docs/qa-images/ptr_loading_state.png")
    expect(indicator).to_have_class("ptr-indicator is-loading")

    # Since it reloads, wait for reload
    page.wait_for_function(
        "() => window.performance.navigation.type === 1", timeout=5000
    )
