import pytest
import os
import glob
import random
import string
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="function")
def page(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        page = context.new_page()
        page.set_default_timeout(60000)
        page.goto(server)

        # Log in if needed
        if page.locator("text=Login").is_visible():
            page.fill('input[name="username"]', "admin")
            page.fill('input[name="password"]', "admin")
            page.click('button[type="submit"]')
            page.wait_for_selector(".launcher", state="attached", timeout=15000)
        yield page
        context.close()
        browser.close()


@pytest.mark.prone_to_timeout
@pytest.mark.timeout(60)
def test_bulk_random_upload_e2e(page, test_data_dir):
    import os
    import shutil

    try:
        os.remove(os.path.join(str(test_data_dir), "sessions.db"))
    except FileNotFoundError:
        pass
    shutil.rmtree(os.path.join(str(test_data_dir), "workspace"), ignore_errors=True)
    os.makedirs(os.path.join(str(test_data_dir), "workspace"), exist_ok=True)
    with open(
        os.path.join(str(test_data_dir), "workspace", "gemini_mock_sessions.json"), "w"
    ) as f:
        f.write("[]")

    # 1. Start a terminal session
    page.locator("#new-tab-btn").click()
    btns = page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()

    expect(page.locator("#active-connection-info")).to_be_visible(timeout=15000)

    # Wait for the terminal to connect
    page.wait_for_timeout(3000)
    page.wait_for_function(
        """() => {
        const tab = tabs.find(t => t.id === activeTabId);
        if (tab && tab.term) {
            let out = "";
            for (let i = 0; i < 10; i++) {
                const line = tab.term.buffer.active.getLine(i);
                if (line) out += line.translateToString() + "\\n";
            }
            return out.includes("Welcome to Fake Gemini");
        }
        return false;
    }""",
        timeout=15000,
    )

    # 2. Generate random 8-letter names
    def rand_name():
        return "".join(random.choices(string.ascii_lowercase, k=8)) + ".txt"

    file1_name = rand_name()
    file2_name = rand_name()
    file3_name = rand_name()

    # 3. Simulate drag-and-drop multiple files
    page.evaluate(f"""() => {{
        const file1 = new File(["content1"], "{file1_name}", {{ type: 'text/plain' }});
        const file2 = new File(["content2"], "{file2_name}", {{ type: 'text/plain' }});
        const file3 = new File(["content3"], "{file3_name}", {{ type: 'text/plain' }});

        const dropEvent = new Event('drop', {{ bubbles: true, cancelable: true }});
        dropEvent.dataTransfer = {{
            items: [
                {{
                    webkitGetAsEntry: () => ({{
                        isFile: true,
                        isDirectory: false,
                        name: '{file1_name}',
                        file: (cb) => cb(file1)
                    }})
                }},
                {{
                    webkitGetAsEntry: () => ({{
                        isFile: true,
                        isDirectory: false,
                        name: '{file2_name}',
                        file: (cb) => cb(file2)
                    }})
                }},
                {{
                    webkitGetAsEntry: () => ({{
                        isFile: true,
                        isDirectory: false,
                        name: '{file3_name}',
                        file: (cb) => cb(file3)
                    }})
                }}
            ],
            files: [file1, file2, file3]
        }};
        document.dispatchEvent(dropEvent);
    }}""")

    # 4. Wait for terminal injection
    page.wait_for_timeout(3000)
    content_text = page.evaluate("""() => {
        const tab = tabs.find(t => t.id === activeTabId);
        if (tab && tab.term) {
            let out = "";
            for (let i = 0; i < 20; i++) {
                const line = tab.term.buffer.active.getLine(i);
                if (line) out += line.translateToString(true) + "\\n";
            }
            return out;
        }
        return "";
    }""")

    print("TERMINAL CONTENT:", repr(content_text))
    assert (
        "> I uploaded multiple files to @upload-" in content_text
    ), "Upload message not found in terminal output"

    # 5. Check actual files in the target folder
    workspace_dir = os.path.join(str(test_data_dir), "workspace")
    upload_dirs = glob.glob(os.path.join(workspace_dir, "upload-*"))
    assert (
        len(upload_dirs) >= 1
    ), f"Expected at least one upload-* directory, found {upload_dirs}"

    # Find the latest upload dir
    upload_dir = max(upload_dirs, key=os.path.getmtime)

    # Verify our random files exist inside
    assert os.path.exists(os.path.join(upload_dir, file1_name)), f"{file1_name} missing"
    assert os.path.exists(os.path.join(upload_dir, file2_name)), f"{file2_name} missing"
    assert os.path.exists(os.path.join(upload_dir, file3_name)), f"{file3_name} missing"
