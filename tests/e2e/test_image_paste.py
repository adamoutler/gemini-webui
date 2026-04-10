import pytest
import os
import base64
from playwright.sync_api import Page, expect


def test_image_paste_logic(page: Page):
    page.on("console", lambda msg: print(f"BROWSER CONSOLE: {msg.text}"))
    page.on("pageerror", lambda err: print(f"BROWSER ERROR: {err.message}"))

    # 1. Load the page
    page.goto("http://127.0.0.1:5001/")
    expect(page.get_by_text("Select a Connection").first).to_be_visible(timeout=10000)

    # 2. Start a local session
    btns = page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=10000)
    btns.first.click()

    # Wait for terminal
    expect(page.locator(".terminal")).to_be_visible(timeout=10000)

    # 3. Call uploadPastedImage directly
    page.evaluate("""async () => {
        const tList = (typeof tabs !== 'undefined' ? tabs : window.tabs);
        console.log("Current tabs count:", tList.length);
        const activeTab = tList.find(t => t.active) || tList[0];
        if (!activeTab) {
            console.error("NO TAB FOUND AT ALL");
            return;
        }
        console.log("Using tab:", activeTab.id, "active:", activeTab.active);

        const file = new File(['dummy content'], 'test.png', { type: 'image/png' });

        const callback = (msg) => {
            console.log("TERMINAL EMIT:", msg);
            const div = document.createElement('div');
            div.id = 'test-emit-output';
            div.textContent = msg;
            document.body.appendChild(div);
        };

        await uploadPastedImage(file, activeTab, callback);
    }""")

    # 4. Verify that the terminal message was generated
    expect(page.locator("#test-emit-output")).to_contain_text(
        "> I pasted @pasted_images/pasted-image-", timeout=15000
    )
    page.screenshot(path="public/qa-screenshots/proof_260_image_paste.png")

    # 5. Check if the file was actually created in the workspace
    workspace_dir = "/data/workspace/pasted_images"
    import time

    time.sleep(2)
    if os.path.exists(workspace_dir):
        files = os.listdir(workspace_dir)
        print(f"Files in {workspace_dir}: {files}")
        assert any(f.startswith("pasted-image-") for f in files)
    else:
        print(f"Directory {workspace_dir} does not exist!")
        # List workspace to see what's there
        if os.path.exists("/data/workspace"):
            print(f"Workspace content: {os.listdir('/data/workspace')}")
        assert False, f"Directory {workspace_dir} should exist after upload"
