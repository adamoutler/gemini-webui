import pytest
import time
import subprocess
import os
import signal
import json
from playwright.sync_api import sync_playwright, expect

@pytest.fixture(scope="function")
def custom_server(test_data_dir):
    env = os.environ.copy()
    env["BYPASS_AUTH_FOR_TESTING"] = "true"
    env["SECRET_KEY"] = "testsecret"
    import random
    port = str(random.randint(10000, 20000))
    env["PORT"] = port
    env["ALLOWED_ORIGINS"] = "*"
    env["DATA_DIR"] = str(test_data_dir)
    env["FLASK_USE_RELOADER"] = "false"
    env["GEMWEBUI_HARNESS"] = "1"
    env["FLASK_DEBUG"] = "false"
    env["SKIP_MONKEY_PATCH"] = "false"
    
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    python_bin = os.path.join(project_root, ".venv", "bin", "python")
    
    # Pre-configure mock gemini by adding tests/mock to PATH
    mock_dir = os.path.join(project_root, "tests", "mock")
    env["PATH"] = f"{mock_dir}:{env.get('PATH', '')}"
    env["PYTHONPATH"] = project_root
    
    def start_server():
        proc = subprocess.Popen(
            [python_bin, "-m", "src.app"],
            env=env,
            cwd=str(test_data_dir), # run in test_data_dir so gemini_mock_state.json is written there
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
        return proc

    process = start_server()
    url = f"http://127.0.0.1:{port}"
    
    class ServerController:
        def __init__(self, process, start_fn, url):
            self.process = process
            self.start_fn = start_fn
            self.url = url
            
        def stop(self):
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                self.process.wait()
            except OSError:
                pass
                
        def start(self):
            self.process = self.start_fn()

    controller = ServerController(process, start_server, url)
    yield controller
    controller.stop()

@pytest.mark.timeout(60)
def test_new_session_no_resume(custom_server, test_data_dir):
    """
    Test that a 'Start New' connection executes without the -r flag.
    We verify this by pre-creating the mock state file. If -r is NOT passed,
    the mock script clears the state file. If -r IS passed (regression), it keeps it.
    """
    state_file = test_data_dir / "gemini_mock_state.json"
    with open(state_file, "w") as f:
        json.dump({"TEST_VALUE": "REGRESSION_FAIL"}, f)
        
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(60000)
        
        page.goto(custom_server.url)
        expect(page.get_by_text("Select a Connection").first).to_be_visible(timeout=15000)
        
        # Click "Start New"
        page.locator('.tab-instance.active button:has-text("Start New")').first.click()
        
        # Wait for terminal to load
        expect(page.locator('#active-connection-info')).to_be_visible(timeout=15000)
        
        # Focus terminal and type
        page.locator('.xterm').first.click()
        page.keyboard.type("What is the TEST_VALUE\r")
        
        # Check output
        def check_text(page):
            return page.evaluate("""() => {
                if (typeof tabs === 'undefined' || typeof activeTabId === 'undefined') return '';
                const tab = tabs.find(t => t.id === activeTabId);
                if (!tab || !tab.term) return '';
                let text = '';
                for (let i = 0; i < tab.term.buffer.active.length; i++) {
                    text += tab.term.buffer.active.getLine(i)?.translateToString(true) || '';
                    text += '\\n';
                }
                return text;
            }""")

        term_text = ""
        for _ in range(10):
            term_text = check_text(page)
            if "I don't know the TEST_VALUE" in term_text or "The TEST_VALUE is REGRESSION_FAIL" in term_text:
                break
            time.sleep(0.5)
            
        assert "I don't know the TEST_VALUE" in term_text, "Start New incorrectly used -r, causing it to load previous state"
        assert "The TEST_VALUE is REGRESSION_FAIL" not in term_text
        
        context.close()
        browser.close()

@pytest.mark.timeout(60)
def test_auto_resume_after_server_restart(custom_server, test_data_dir):
    """
    Test that after a server restart, the UI automatically reconnects and resumes the session using -r.
    """
    state_file = test_data_dir / "gemini_mock_state.json"
    if os.path.exists(state_file):
        os.remove(state_file)
        
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(60000)
        
        page.goto(custom_server.url)
        expect(page.get_by_text("Select a Connection").first).to_be_visible(timeout=15000)
        
        # 1. Start New Session
        page.locator('.tab-instance.active button:has-text("Start New")').first.click()
        expect(page.locator('#active-connection-info')).to_be_visible(timeout=15000)
        
        # 2. Set state
        page.locator('.xterm').first.click()
        page.keyboard.type("Remember this TEST_VALUE: AUTO_RESUME_SUCCESS\r")
        
        def check_text(page):
            return page.evaluate("""() => {
                if (typeof tabs === 'undefined' || typeof activeTabId === 'undefined') return '';
                const tab = tabs.find(t => t.id === activeTabId);
                if (!tab || !tab.term) return '';
                let text = '';
                for (let i = 0; i < tab.term.buffer.active.length; i++) {
                    text += tab.term.buffer.active.getLine(i)?.translateToString(true) || '';
                    text += '\\n';
                }
                return text;
            }""")

        for _ in range(10):
            term_text = check_text(page)
            if "I will remember TEST_VALUE: AUTO_RESUME_SUCCESS" in term_text:
                break
            time.sleep(0.5)
            
        assert "I will remember TEST_VALUE: AUTO_RESUME_SUCCESS" in term_text
        
        # Wait for localStorage to be populated with geminiResume
        for _ in range(10):
            val = page.evaluate("localStorage.getItem('geminiResume')")
            if val is not None and int(val) > 0:
                break
            time.sleep(0.5)
        
        # 3. Stop server for 10 seconds
        custom_server.stop()
        time.sleep(10) # Requirement: verify if server is stopped for 10 seconds and restarted
        
        status_el = page.locator('#connection-status')
        expect(status_el).to_have_text("Reconnecting...", timeout=20000)
        
        # 4. Restart server
        custom_server.start()
        
        # 5. Verify UI auto-reconnects
        expect(status_el).to_have_text("local", timeout=30000)
        
        # 6. Verify it resumed using -r by asking for the value
        # Wait a moment for terminal to settle after reconnect
        time.sleep(2)
        page.locator('.xterm').first.click()
        page.keyboard.type("What is the TEST_VALUE\r")
        
        for _ in range(10):
            term_text = check_text(page)
            if "The TEST_VALUE is AUTO_RESUME_SUCCESS" in term_text:
                break
            time.sleep(0.5)
            
        assert "The TEST_VALUE is AUTO_RESUME_SUCCESS" in term_text, "Failed to auto-resume with -r after server restart"

        context.close()
        browser.close()

@pytest.mark.timeout(60)
def test_no_terminal_clear_on_stolen_session(custom_server, test_data_dir):
    """
    Test that session-stolen event does not clear the terminal buffer or loop.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Browser 1
        context1 = browser.new_context()
        page1 = context1.new_page()
        page1.set_default_timeout(60000)
        page1.goto(custom_server.url)
        expect(page1.get_by_text("Select a Connection").first).to_be_visible(timeout=15000)
        page1.locator('.tab-instance.active button:has-text("Start New")').first.click()
        expect(page1.locator('#active-connection-info')).to_be_visible(timeout=15000)
        page1.locator('.xterm').first.click()
        page1.keyboard.type("Initial buffer state check\r")
        
        def check_text(page):
            return page.evaluate("""() => {
                if (typeof tabs === 'undefined' || typeof activeTabId === 'undefined') return '';
                const tab = tabs.find(t => t.id === activeTabId);
                if (!tab || !tab.term) return '';
                let text = '';
                for (let i = 0; i < tab.term.buffer.active.length; i++) {
                    text += tab.term.buffer.active.getLine(i)?.translateToString(true) || '';
                    text += '\\n';
                }
                return text;
            }""")
            
        # Wait for input to be processed
        for _ in range(10):
            term_text1 = check_text(page1)
            if "Initial buffer state check" in term_text1:
                break
            time.sleep(0.5)
            
        assert "Initial buffer state check" in term_text1
        
        # Simulate session-stolen by dispatching it
        page1.evaluate("""() => {
            const tab = tabs.find(t => t.id === activeTabId);
            tab.socket._callbacks['$session-stolen'][0]({});
        }""")
        
        # Check that 'Reclaim' button appeared
        expect(page1.locator('#reclaim-btn')).to_be_visible(timeout=15000)
        
        # Check that connection status says Stolen
        status_el = page1.locator('#connection-status')
        expect(status_el).to_have_text("Stolen", timeout=15000)
        
        # Buffer should still have initial text
        term_text1_after = check_text(page1)
        assert "Initial buffer state check" in term_text1_after
        assert "Session stolen" in term_text1_after
        
        context1.close()
        browser.close()
