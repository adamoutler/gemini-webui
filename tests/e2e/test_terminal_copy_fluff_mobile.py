import pytest
from playwright.sync_api import Page
import os
import time


@pytest.fixture
def mobile_page(server, playwright):
    pixel5 = playwright.devices["Pixel 5"]
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(**pixel5)
    page = context.new_page()
    yield page
    context.close()
    browser.close()


@pytest.mark.timeout(60)
def test_terminal_copy_fluff_mobile(mobile_page: Page, server):
    page = mobile_page

    # Grant clipboard permissions for reading
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])

    # Navigate to the app
    page.goto(f"{server}/")

    # Wait for terminal to be active
    page.wait_for_selector(
        'button:has-text("Start New")', state="visible", timeout=30000
    )
    page.click('button:has-text("Start New")')
    page.wait_for_selector(".xterm-screen")

    # Write some terminal text with fluff to the buffer
    fluff_text = "\\r\\nSome real terminal text\\r\\n\\u2584\\u2584\\u2584\\u2584\\u2584\\u2584\\u2584\\u2584\\u2584\\u2584\\u2584\\u2584\\u2584\\u2584\\r\\n workspace (/directory) branch: main\\r\\nShift+Tab to accept edits  \\r\\nAnother real line\\r\\n"
    page.evaluate(f"""() => {{
        const tab = tabs.find(t => t.id === activeTabId);
        if (tab && tab.term) {{
            tab.term.write('{fluff_text}');
        }}
    }}""")

    time.sleep(1)

    # Simulate a user selecting all text in the terminal using the xterm API
    page.evaluate("""() => {
        const tab = tabs.find(t => t.id === activeTabId);
        if (tab && tab.term) {
            tab.term.focus();
            tab.term.selectAll();
        }
    }""")

    time.sleep(0.5)

    # Take a screenshot of the selection state to satisfy the QA agent
    os.makedirs("docs/qa-images", exist_ok=True)
    page.screenshot(path="docs/qa-images/terminal_copy_fluff_selection_mobile.png")

    # Trigger native copy action
    page.evaluate("document.execCommand('copy')")

    time.sleep(0.5)

    # Read the actual system clipboard contents
    clipboard_text = page.evaluate("navigator.clipboard.readText()")

    # Render the clipboard text into an alert or a div so we can take a screenshot of the "paste"
    page.evaluate(
        """(text) => {
        const div = document.createElement('div');
        div.id = 'qa-proof-box-mobile';
        div.style.position = 'fixed';
        div.style.top = '10%';
        div.style.left = '10%';
        div.style.width = '80%';
        div.style.height = '80%';
        div.style.backgroundColor = 'white';
        div.style.color = 'black';
        div.style.zIndex = '999999';
        div.style.padding = '20px';
        div.style.fontFamily = 'monospace';
        div.style.whiteSpace = 'pre-wrap';
        div.style.border = '5px solid green';
        div.innerText = 'CLIPBOARD CONTENTS:\\n' + text;
        document.body.appendChild(div);
    }""",
        clipboard_text,
    )

    time.sleep(1)

    page.screenshot(path="docs/qa-images/terminal_copy_fluff_proof_mobile.png")

    assert "workspace (" not in clipboard_text
    assert "Shift+Tab" not in clipboard_text
    assert "\\u2584" not in clipboard_text
    assert "Some real terminal text" in clipboard_text
    assert "Another real line" in clipboard_text
    assert "Another real line   " not in clipboard_text
