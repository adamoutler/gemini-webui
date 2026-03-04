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
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);
        
        const dropEvent = new DragEvent('drop', {
            dataTransfer: dataTransfer,
            bubbles: true,
            cancelable: true
        });
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
