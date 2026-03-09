import pytest
import os
import subprocess
import time
import signal
from playwright.sync_api import sync_playwright, expect

@pytest.fixture(scope="function")
def csrf_enabled_server(test_data_dir):
    env = os.environ.copy()
    env["BYPASS_AUTH_FOR_TESTING"] = "true"
    env["SECRET_KEY"] = "testsecret"
    env["WTF_CSRF_ENABLED"] = "true"
    env["FLASK_USE_RELOADER"] = "false"
    import random
    port = str(random.randint(9000, 10000))
    env["PORT"] = port
    env["ALLOWED_ORIGINS"] = "*"
    env["DATA_DIR"] = str(test_data_dir)
    
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    python_bin = os.path.join(project_root, ".venv", "bin", "python")
    
    proc = subprocess.Popen(
        [python_bin, "-m", "src.app"],
        env=env,
        cwd=project_root,
        preexec_fn=os.setsid
    )
    import requests
    for _ in range(20):
        try:
            resp = requests.get(f"http://127.0.0.1:{port}/health", timeout=1)
            if resp.status_code == 200:
                break
        except requests.RequestException:
            pass
        time.sleep(1)

    url = f"http://127.0.0.1:{port}"
    yield url
    
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.wait()
    except OSError:
        pass

@pytest.mark.timeout(30)
def test_csrf_upload_over_ssh(csrf_enabled_server, test_data_dir):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        # We need to capture requests to see if CSRF token is present or rejected

        upload_requests = []
        page.on("request", lambda request: upload_requests.append(request) if "/api/upload" in request.url else None)
        
        # Capture console messages
        page.on("console", lambda msg: print(f"BROWSER CONSOLE: {msg.text}"))

        
        page.goto(csrf_enabled_server)
        
        btns = page.locator('.tab-instance.active button:has-text("Start New")')
        expect(btns.first).to_be_visible(timeout=5000)
        btns.first.click()
        
        expect(page.locator('#active-connection-info')).to_be_visible(timeout=5000)
        page.wait_for_timeout(3000)

        # Open file transfer
        page.click('button:has-text("Files")')
        expect(page.locator('#file-transfer-modal')).to_be_visible(timeout=5000)
        
        test_file_path = os.path.join(test_data_dir, "csrf_test_file.txt")
        with open(test_file_path, "w") as f:
            f.write("Test content for CSRF upload")
            
        page.locator('#workspace-upload-file').set_input_files(test_file_path)
        
        
        # Corrupt the token right before upload to simulate token expiration
        page.evaluate('''() => {
            const meta = document.querySelector('meta[name="csrf-token"]');
            if (meta) meta.setAttribute('content', 'token_expired_123');
        }''')
        
        page.once("dialog", lambda dialog: dialog.accept())
 # accept any alerts (success or failure)
        page.click('button:has-text("Upload File")')
        
        page.wait_for_timeout(2000)
        
        assert len(upload_requests) > 0, "Upload API request should have been made"
        
        req = upload_requests[-1]
        # X-CSRFToken header check
        csrf_header = req.headers.get("x-csrftoken")
        assert csrf_header, "CSRF Token missing from upload request headers!"
        
        # Verify response was not 400 Bad Request (CSRF failure)
        resp = req.response()
        assert resp.status != 400, "CSRF validation failed on backend!"
        assert resp.status == 200, "Upload failed for another reason"
        
        context.close()
        browser.close()

@pytest.mark.timeout(30)
def test_csrf_drag_drop_upload_over_ssh(csrf_enabled_server, test_data_dir):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        

        upload_requests = []
        page.on("request", lambda request: upload_requests.append(request) if "/api/upload" in request.url else None)
        
        # Capture console messages
        page.on("console", lambda msg: print(f"BROWSER CONSOLE: {msg.text}"))

        
        page.goto(csrf_enabled_server)
        
        btns = page.locator('.tab-instance.active button:has-text("Start New")')
        expect(btns.first).to_be_visible(timeout=5000)
        btns.first.click()
        
        expect(page.locator('#active-connection-info')).to_be_visible(timeout=5000)
        page.wait_for_timeout(3000)

        # Trigger dragover
        page.evaluate("""() => {
            const dragEvent = new DragEvent('dragover', { bubbles: true, cancelable: true });
            document.dispatchEvent(dragEvent);
        }""")
        
        expect(page.locator('.drop-zone')).to_have_class('drop-zone active')

        # Trigger drop
        page.evaluate("""() => {
            const file = new File(["dropped content"], "drop_test_csrf.txt", { type: 'text/plain' });
            
            const dropEvent = new Event('drop', { bubbles: true, cancelable: true });
            dropEvent.dataTransfer = {
                items: [
                    {
                        webkitGetAsEntry: () => ({
                            isFile: true,
                            isDirectory: false,
                            name: 'drop_test_csrf.txt',
                            file: (cb) => cb(file)
                        })
                    }
                ],
                files: [file]
            };
            document.dispatchEvent(dropEvent);
        }""")

        page.wait_for_timeout(2000)
        
        assert len(upload_requests) > 0, "Upload API request should have been made"
        
        req = upload_requests[-1]
        csrf_header = req.headers.get("x-csrftoken")
        assert csrf_header, "CSRF Token missing from upload request headers!"
        
        resp = req.response()
        assert resp.status != 400, "CSRF validation failed on backend!"
        assert resp.status == 200, "Upload failed for another reason"
        
        context.close()
        browser.close()

@pytest.mark.timeout(60)
def test_csrf_upload_stale_cache_recovery(csrf_enabled_server, test_data_dir):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        
        # Intercept the HTML response to serve a stale CSRF token
        def handle_route(route, request):
            if request.url == csrf_enabled_server or request.url == f"{csrf_enabled_server}/":
                # Fetch original and inject stale token
                response = route.fetch()
                html = response.text()
                import re
                stale_html = re.sub(r'content="[^"]*" name="csrf-token"', 'content="invalid_stale_token_123" name="csrf-token"', html)
                route.fulfill(response=response, body=stale_html)
            else:
                route.continue_()
        
        page = context.new_page()
        page.route(csrf_enabled_server, handle_route)
        page.route(f"{csrf_enabled_server}/", handle_route)
        

        upload_requests = []
        page.on("request", lambda request: upload_requests.append(request) if "/api/upload" in request.url else None)
        
        # Capture console messages
        page.on("console", lambda msg: print(f"BROWSER CONSOLE: {msg.text}"))

        
        page.goto(csrf_enabled_server)
        
        btns = page.locator('.tab-instance.active button:has-text("Start New")')
        expect(btns.first).to_be_visible(timeout=5000)
        btns.first.click()
        
        expect(page.locator('#active-connection-info')).to_be_visible(timeout=5000)
        page.wait_for_timeout(3000)

        # Open file transfer
        page.click('button:has-text("Files")')
        expect(page.locator('#file-transfer-modal')).to_be_visible(timeout=5000)
        
        test_file_path = os.path.join(test_data_dir, "csrf_stale_test.txt")
        with open(test_file_path, "w") as f:
            f.write("Test content for stale cache upload")
            
        page.locator('#workspace-upload-file').set_input_files(test_file_path)
        
        
        # Corrupt the token right before upload to simulate token expiration
        page.evaluate('''() => {
            const meta = document.querySelector('meta[name="csrf-token"]');
            if (meta) meta.setAttribute('content', 'token_expired_123');
        }''')
        
        page.once("dialog", lambda dialog: dialog.accept())

        page.click('button:has-text("Upload File")')
        
        page.wait_for_timeout(2000)
        
        assert len(upload_requests) > 0, "Upload API request should have been made"
        
        req = upload_requests[-1]
        resp = req.response()
        assert resp.status != 400, "CSRF validation failed on backend! The token was not recovered."
        assert resp.status == 200, f"Upload failed for another reason: {resp.status}"
        
        page.screenshot(path="/tmp/gemwe-180.png")
        import warnings
        warnings.warn("Empirical Evidence: Stale CSRF cache upload succeeded. Visual proof saved to /tmp/gemwe-180.png")

        context.close()
        browser.close()
