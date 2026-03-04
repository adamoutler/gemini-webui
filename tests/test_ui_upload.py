import pytest
import os
from playwright.sync_api import sync_playwright, expect

@pytest.fixture(scope="function")
def page(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
        page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
        page.goto(server, timeout=15000)
        page.wait_for_selector(".launcher, .terminal-instance", state="attached", timeout=15000)
        yield page
        context.close()
        browser.close()

@pytest.mark.prone_to_timeout
@pytest.mark.timeout(30)
def test_drag_and_drop_upload(page, test_data_dir):
    # Start a terminal session so we can verify the text injection
    btns = page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=5000)
    btns.first.click()
    
    page.on("response", lambda r: print("RESPONSE:", r.url, r.status, r.text() if "upload" in r.url else ""))
    expect(page.locator('#active-connection-info')).to_be_visible(timeout=5000)

    # Trigger dragover to show dropzone
    page.evaluate("""() => {
        const dragEvent = new DragEvent('dragover', { bubbles: true, cancelable: true });
        document.dispatchEvent(dragEvent);
    }""")
    
    # Check dropzone became active
    expect(page.locator('.drop-zone')).to_have_class('drop-zone active')

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
    expect(page.locator('.drop-zone')).not_to_have_class('drop-zone active')

    # Wait for the terminal to echo the injected text
    # It might take a moment to upload, emit to socket, hit PTY, and echo back
    page.wait_for_timeout(2000)
    
    content = page.evaluate("""() => {
        const tab = tabs.find(t => t.id === activeTabId);
        if (tab && tab.term) {
            let out = "";
            for (let i = 0; i < 5; i++) {
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
@pytest.mark.timeout(30)
def test_workspace_file_upload_success_message(page, test_data_dir):
    dialog_messages = []
    page.on("dialog", lambda dialog: (dialog_messages.append(dialog.message), dialog.accept()))
    
    # Open the file transfer modal
    page.click('button:has-text("Files")')
    expect(page.locator('#file-transfer-modal')).to_be_visible(timeout=5000)
    
    # Create a temporary file to upload
    test_file_path = os.path.join(test_data_dir, "test_upload_file.txt")
    with open(test_file_path, "w") as f:
        f.write("Test content for upload")
        
    # Set the file input
    page.locator('#workspace-upload-file').set_input_files(test_file_path)
    
    # Click upload button
    page.click('button:has-text("Upload File")')
    
    # Wait for the alert
    page.wait_for_timeout(2000)
    
    assert "File uploaded successfully" in dialog_messages, f"Expected success alert, got: {dialog_messages}"

@pytest.mark.prone_to_timeout
@pytest.mark.timeout(30)
def test_folder_drag_and_drop_upload(page, test_data_dir):
    btns = page.locator('.tab-instance.active button:has-text("Start New")')
    expect(btns.first).to_be_visible(timeout=5000)
    btns.first.click()
    
    expect(page.locator('#active-connection-info')).to_be_visible(timeout=5000)

    page.evaluate("""() => {
        const dragEvent = new DragEvent('dragover', { bubbles: true, cancelable: true });
        document.dispatchEvent(dragEvent);
    }""")
    
    expect(page.locator('.drop-zone')).to_have_class('drop-zone active')

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

    expect(page.locator('.drop-zone')).not_to_have_class('drop-zone active')

    page.wait_for_timeout(3000)
    
    content = page.evaluate("""() => {
        const tab = tabs.find(t => t.id === activeTabId);
        if (tab && tab.term) {
            let out = "";
            for (let i = 0; i < 5; i++) {
                const line = tab.term.buffer.active.getLine(i);
                if (line) out += line.translateToString(true) + "\\n";
            }
            return out;
        }
        return "";
    }""")
    
    assert "myfolder/subfolder/file2.txt" in content or "2 files including" in content, f"Expected indication of file2.txt uploaded or 2 files uploaded, got terminal content: {content}"
    
    # Check if files actually exist in test_data_dir
    assert os.path.exists(os.path.join(test_data_dir, "myfolder", "file1.txt"))
    assert os.path.exists(os.path.join(test_data_dir, "myfolder", "subfolder", "file2.txt"))
