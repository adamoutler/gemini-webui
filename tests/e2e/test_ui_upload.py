import pytest
import os
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="function")
def page(server, playwright):
    p = playwright
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()

    page = context.new_page()
    page.set_default_timeout(60000)
    page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
    page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
    page.goto(server, timeout=15000)
    page.wait_for_selector(
        ".launcher, .terminal-instance", state="attached", timeout=15000
    )
    yield page
    context.close()
    browser.close()


@pytest.mark.prone_to_timeout
@pytest.mark.timeout(60)
def test_drag_and_drop_upload(page, test_data_dir, playwright):
    # Start a terminal session so we can verify the text injection
    btns = page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()

    expect(page.locator("#active-connection-info")).to_be_visible(timeout=15000)

    # Wait for the terminal to connect
    page.wait_for_timeout(3000)

    # Trigger dragover to show dropzone
    page.evaluate("""() => {
        const dragEvent = new DragEvent('dragover', { bubbles: true, cancelable: true });
        document.dispatchEvent(dragEvent);
    }""")

    # Check dropzone became active
    expect(page.locator(".drop-zone")).to_have_class("drop-zone active")

    # Trigger drop
    page.evaluate("""() => {
        const file = new File(["dropped content"], "drop_test.txt", { type: 'text/plain' });

        const dropEvent = new Event('drop', { bubbles: true, cancelable: true });
        dropEvent.dataTransfer = {
            items: [
                {
                    webkitGetAsEntry: () => ({
                        isFile: true,
                        isDirectory: false,
                        name: 'drop_test.txt',
                        file: (cb) => cb(file)
                    })
                }
            ],
            files: [file]
        };
        document.dispatchEvent(dropEvent);
    }""")

    # Check dropzone inactive
    expect(page.locator(".drop-zone")).not_to_have_class("drop-zone active")

    # Wait for the terminal to echo the injected text
    # It might take a moment to upload, emit to socket, hit PTY, and echo back
    page.wait_for_timeout(2000)

    content = page.evaluate("""() => {
        const tab = tabs.find(t => t.id === activeTabId);
        if (tab && tab.term) {
            let out = "";
            for (let i = 0; i < 15; i++) {
                const line = tab.term.buffer.active.getLine(i);
                if (line) out += line.translateToString(true) + "\\n";
            }
            return out;
        }
        return "";
    }""")
    print("TERMINAL CONTENT:", repr(content))

    assert "drop_test.txt" in content, "Uploaded file name not found in terminal output"

    # Verify backend actually received and saved the file
    # Server runs in the same test environment or uses test_data_dir?
    # The `server` fixture runs the actual flask app in a background thread, using the default DATA_DIR
    # or the mocked DATA_DIR if configured. Let's wait for file to appear in `test_data_dir`.

    # Actually, let's just check if it was uploaded successfully via the UI confirmation
    # Oh wait, we don't alert on success if we inject to terminal. So text injection IS the confirmation.


@pytest.mark.prone_to_timeout
@pytest.mark.timeout(60)
def test_folder_drag_and_drop_upload(page, test_data_dir, playwright):
    btns = page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()

    expect(page.locator("#active-connection-info")).to_be_visible(timeout=15000)

    # Wait for the terminal to connect
    page.wait_for_timeout(3000)

    page.evaluate("""() => {
        const dragEvent = new DragEvent('dragover', { bubbles: true, cancelable: true });
        document.dispatchEvent(dragEvent);
    }""")

    expect(page.locator(".drop-zone")).to_have_class("drop-zone active")

    # Mock a drop event with webkitGetAsEntry simulating a directory
    page.evaluate("""() => {
        const file1 = new File(["file1 content"], "file1.txt", { type: 'text/plain' });
        const file2 = new File(["file2 content"], "file2.txt", { type: 'text/plain' });

        const dropEvent = new Event('drop', { bubbles: true, cancelable: true });
        dropEvent.dataTransfer = {
            items: [
                {
                    webkitGetAsEntry: () => ({
                        isDirectory: true,
                        isFile: false,
                        name: 'myfolder',
                        createReader: () => ({
                            readEntries: (cb) => cb([
                                {
                                    isDirectory: false,
                                    isFile: true,
                                    name: 'file1.txt',
                                    file: (cb2) => cb2(file1)
                                },
                                {
                                    isDirectory: true,
                                    isFile: false,
                                    name: 'subfolder',
                                    createReader: () => ({
                                        readEntries: (cb3) => cb3([
                                            {
                                                isDirectory: false,
                                                isFile: true,
                                                name: 'file2.txt',
                                                file: (cb4) => cb4(file2)
                                            }
                                        ])
                                    })
                                }
                            ])
                        })
                    })
                }
            ],
            files: []
        };

        document.dispatchEvent(dropEvent);
    }""")

    expect(page.locator(".drop-zone")).not_to_have_class("drop-zone active")

    page.wait_for_timeout(3000)

    content = page.evaluate("""() => {
        const tab = tabs.find(t => t.id === activeTabId);
        if (tab && tab.term) {
            let out = "";
            for (let i = 0; i < 15; i++) {
                const line = tab.term.buffer.active.getLine(i);
                if (line) out += line.translateToString(true) + "\\n";
            }
            return out;
        }
        return "";
    }""")

    assert (
        "> I uploaded multiple files to @upload-" in content
    ), f"Expected indication of multiple files uploaded to an upload- timestamped folder, got terminal content: {content}"

    # Check if files actually exist in test_data_dir within a timestamped upload folder
    import glob

    workspace_dir = os.path.join(test_data_dir, "workspace")
    upload_dirs = glob.glob(os.path.join(workspace_dir, "upload-*"))
    assert len(upload_dirs) >= 1, "Expected at least one upload-* directory"
    upload_dir = max(upload_dirs, key=os.path.getmtime)

    assert os.path.exists(os.path.join(upload_dir, "myfolder", "file1.txt"))
    assert os.path.exists(
        os.path.join(upload_dir, "myfolder", "subfolder", "file2.txt")
    )


@pytest.mark.prone_to_timeout
@pytest.mark.timeout(60)
def test_workspace_file_upload_button_injection(page, test_data_dir, playwright):
    # Start a terminal session
    btns = page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=15000)
    btns.first.click()

    expect(page.locator("#active-connection-info")).to_be_visible(timeout=15000)

    # Wait for the terminal to connect
    page.wait_for_timeout(3000)

    # Open the file transfer modal
    page.click('button:has-text("Files")')
    expect(page.locator("#file-transfer-modal")).to_be_visible(timeout=15000)

    # Create a temporary file to upload
    test_file_path = os.path.join(test_data_dir, "test_upload_file2.txt")
    with open(test_file_path, "w") as f:
        f.write("Test content for upload 2")

    # Set the file input
    page.locator("#workspace-upload-file").set_input_files(test_file_path)

    # Click upload button
    page.click('button:has-text("Upload File")')

    # Wait for the injection
    page.wait_for_timeout(2000)

    content = page.evaluate("""() => {
        const tab = tabs.find(t => t.id === activeTabId);
        if (tab && tab.term) {
            let out = "";
            for (let i = 0; i < 15; i++) {
                const line = tab.term.buffer.active.getLine(i);
                if (line) out += line.translateToString(true) + "\\n";
            }
            return out;
        }
        return "";
    }""")

    assert (
        "test_upload_file2.txt" in content
    ), "Uploaded file name not found in terminal output"


@pytest.mark.prone_to_timeout
@pytest.mark.timeout(60)
def test_drag_and_drop_disabled_on_launcher(page, playwright):
    # Ensure we are on the launcher screen
    expect(page.locator(".launcher").first).to_be_visible(timeout=15000)

    # Listen for requests to /api/upload to verify none are made
    upload_requests = []
    page.on(
        "request",
        lambda request: upload_requests.append(request)
        if "/api/upload" in request.url
        else None,
    )

    # Trigger dragover
    page.evaluate("""() => {
        const dragEvent = new DragEvent('dragover', { bubbles: true, cancelable: true });
        document.dispatchEvent(dragEvent);
    }""")

    # Check dropzone is NOT active
    expect(page.locator(".drop-zone")).not_to_have_class(
        "drop-zone active", timeout=15000
    )

    # Trigger drop
    page.evaluate("""() => {
        const file = new File(["dropped content"], "drop_test_launcher.txt", { type: 'text/plain' });

        const dropEvent = new Event('drop', { bubbles: true, cancelable: true });
        dropEvent.dataTransfer = {
            items: [
                {
                    webkitGetAsEntry: () => ({
                        isFile: true,
                        isDirectory: false,
                        name: 'drop_test_launcher.txt',
                        file: (cb) => cb(file)
                    })
                }
            ],
            files: [file]
        };
        document.dispatchEvent(dropEvent);
    }""")

    # Check dropzone is STILL inactive
    page.wait_for_timeout(1000)
    expect(page.locator(".drop-zone")).not_to_have_class(
        "drop-zone active", timeout=15000
    )

    # Ensure no upload API requests were triggered
    assert (
        len(upload_requests) == 0
    ), "Upload API requests should not be made on the launcher screen"
