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
            
            # 3. Verify Local Box protection
            log_progress("Checking Local Box protection in settings")
            page.locator('button:has-text("Settings")').click()
            expect(page.locator('#hosts-list')).to_contain_text("Local Box")
            # Delete button should NOT exist for Local Box
            local_box_delete = page.locator("#hosts-list .session-item:has-text('Local Box')").last.locator("button:has-text('Delete')")
            expect(local_box_delete).to_have_count(0)
            
            # 4. Verify Tab Closing
            log_progress("Verifying tab closing works")
            page.locator('#settings-modal span').first.click() # close settings
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
