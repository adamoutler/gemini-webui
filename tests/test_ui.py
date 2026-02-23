import os
import time
import random
import subprocess
import pytest
import json
from playwright.sync_api import sync_playwright, expect

@pytest.fixture(scope="session")
def server(tmp_path_factory):
    # Create a temporary data directory
    data_dir = tmp_path_factory.mktemp("data")
    
    # Start the Flask app
    env = os.environ.copy()
    env["BYPASS_AUTH_FOR_TESTING"] = "true"
    env["SECRET_KEY"] = "testsecret"
    env["PORT"] = "5005"
    env["DATA_DIR"] = str(data_dir)
    env["DEFAULT_SSH_TARGET"] = ""
    mock_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock")
    env["PATH"] = f"{mock_dir}:{env.get('PATH', '')}"
    
    # We use a random port to avoid conflicts
    port = "5005"
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    python_bin = os.path.join(project_root, ".venv", "bin", "python")
    process = subprocess.Popen(
        [python_bin, "src/app.py"],
        env=env,
        cwd=project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Wait for server to start and check if it's still running
    time.sleep(5)
    if process.poll() is not None:
        stdout, stderr = process.communicate()
        print(f"Server failed to start. STDOUT: {stdout} STDERR: {stderr}")
        pytest.fail("Server failed to start")
    
    yield f"http://127.0.0.1:{port}"
    
    # Teardown
    process.terminate()
    process.wait()

def test_gemini_webui_flow(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        # 1. Start the web interface with login bypass
        page.goto(server)
        
        # Wait for terminal to connect
        page.wait_for_timeout(2000)
        
        # 2. Tell it to remember TEST_VALUE
        test_value = str(random.randint(1000, 9999))
        
        # Type into the xterm.js terminal (simulating keyboard input)
        page.locator('.xterm-helper-textarea').click(force=True)
        page.keyboard.type(f"Remember this TEST_VALUE: {test_value}\r", delay=50)
        
        # Wait for Gemini to process and respond
        page.wait_for_timeout(3000) 
        
        # 3. Ask it to recall
        page.keyboard.type("What is the TEST_VALUE I just told you?\r", delay=50)
        page.wait_for_timeout(3000)
        
        # Validate response
        terminal_content = page.locator('.xterm-rows').inner_text()
        assert test_value in terminal_content, f"Expected {test_value} to be in terminal output."
        
        # 4. Refresh page, resume conversation
        page.reload()
        page.wait_for_timeout(2000)
        
        # Ensure Resume is checked
        page.locator('#resume-toggle').set_checked(True)
        
        # Click "Restart Local"
        page.get_by_text("Restart Local").click()
        page.wait_for_timeout(3000)
        
        # 5. Verify conversation resumes
        page.locator('.xterm-helper-textarea').click(force=True)
        page.keyboard.type("Do you still remember the TEST_VALUE?\r", delay=50)
        page.wait_for_timeout(3000)
        
        terminal_content_resumed = page.locator('.xterm-rows').inner_text()
        assert test_value in terminal_content_resumed, "Gemini did not remember the value after resume."
        
        # 6. Uncheck Resume and restart
        page.locator('#resume-toggle').set_checked(False)
        page.get_by_text("Restart Local").click()
        page.wait_for_timeout(3000)
        
        # 7. Ask if it remembers
        page.locator('.xterm-helper-textarea').click(force=True)
        page.keyboard.type("What was the TEST_VALUE?\r", delay=50)
        page.wait_for_timeout(3000)
        
        terminal_content_fresh = page.locator('.xterm-rows').inner_text()
        assert test_value not in terminal_content_fresh, "Gemini incorrectly remembered the value after a fresh restart."
        
        browser.close()
