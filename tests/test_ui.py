import pytest
import time
from playwright.sync_api import sync_playwright, expect

# =====================================================================================
# MANDATORY TIMEOUT GUARDRAILS
# =====================================================================================
# Individual test execution MUST NOT exceed 20 seconds.
# =====================================================================================

MAX_TEST_TIME = 20.0

@pytest.mark.prone_to_timeout
@pytest.mark.timeout(20)
def test_gemini_ui_final(server):
    start_time = time.time()
    
    def log_progress(step_name):
        elapsed = time.time() - start_time
        print(f"[TEST PROGRESS] {step_name} at {elapsed:.2f}s")
        if elapsed > MAX_TEST_TIME:
            pytest.fail(f"HARD TIMEOUT EXCEEDED: '{step_name}' took {elapsed:.2f}s!")
            
    log_progress("Starting final regression test")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        try:
            # 1. Start and verify launcher or auto-resume
            log_progress("Navigating to server")
            page.goto(server, timeout=10000)
            page.wait_for_load_state("networkidle")
            
            # Open new tab to ensure we see the launcher
            log_progress("Opening new tab for launcher verification")
            page.locator('#new-tab-btn').click()
            expect(page.get_by_text("Select a Connection").last).to_be_visible(timeout=5000)
            
            # 2. Verify pre-loaded sessions (mock should have 1)
            log_progress("Checking for pre-loaded mock sessions")
            expect(page.get_by_text("Mock Session").last).to_be_visible(timeout=10000)
            
            # 3. Verify local protection
            log_progress("Checking local protection in settings")
            page.locator('button:has-text("Settings")').click()
            expect(page.locator('#hosts-list')).to_contain_text("local")
            # Delete button should NOT exist for local
            import re
            local_host_item = page.locator("#hosts-list .session-item").filter(has=page.locator("span", has_text=re.compile(r"^local$"))).first
            expect(local_host_item.locator("button:has-text('Delete')")).to_have_count(0)
            
            # Close settings
            page.locator('#settings-modal span').first.click()
            
            # 4. Verify Toolbar and Input Removal
            log_progress("Verifying toolbar state and input removal")
            # Click "Start New" on local (first card) in the ACTIVE tab
            btns = page.locator('.tab-instance.active button:has-text("Start New")')
            expect(btns.first).to_be_visible(timeout=5000)
            
            log_progress("Attempting to click Start New in active tab")
            btns.first.click(timeout=5000)
            log_progress("Clicked Start New, waiting for terminal initialization")
            # Wait for terminal to appear (indicated by active-connection-info being visible)
            expect(page.locator('#active-connection-info')).to_be_visible(timeout=5000)
            log_progress("Toolbar is visible, checking inputs")
            # Verify Restart button is there
            expect(page.locator('button:has-text("Restart")')).to_be_visible()
            # Verify ssh-target and ssh-dir are NOT there
            expect(page.locator('#ssh-target')).to_have_count(0)
            expect(page.locator('#ssh-dir')).to_have_count(0)
            log_progress("Toolbar verification successful")

            # 5. Verify Tab Closing
            log_progress("Verifying tab closing works")
            initial_tabs = page.locator('.tab').count()
            page.locator('.tab-close').last.click()
            expect(page.locator('.tab')).to_have_count(initial_tabs - 1)
            
            log_progress("Test completed successfully")
        except Exception as e:
            page.screenshot(path="failure_screenshot.png")
            raise e
        finally:
            context.close()
            browser.close()
