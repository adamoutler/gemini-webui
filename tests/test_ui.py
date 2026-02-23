import pytest
from playwright.sync_api import sync_playwright, expect

@pytest.mark.timeout(20)
def test_gemini_ui_basic_interaction(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        try:
            # 1. Start the web interface
            page.goto(server)
            
            # 2. Verify connection status eventually shows 'local'
            status = page.locator('#connection-status')
            expect(status).to_have_text('local', timeout=10000)
            
            # 3. Open Settings
            settings_btn = page.locator('button:has-text("Settings")')
            settings_btn.click()
            expect(page.locator('#settings-modal')).to_be_visible()
            
            # 4. Update SSH target in settings
            page.locator('#config-target').fill('testuser@testhost')
            
            # Set up dialog handler BEFORE clicking save
            page.once("dialog", lambda dialog: dialog.accept())
            page.get_by_text("Save Config").click()
            
            # 5. Close settings
            page.locator('#settings-modal span').click()
            expect(page.locator('#settings-modal')).not_to_be_visible()
            
            # 6. Verify main UI target input was updated
            expect(page.locator('#ssh-target')).to_have_value('testuser@testhost')
        finally:
            context.close()
            browser.close()
