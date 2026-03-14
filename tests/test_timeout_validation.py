import pytest
import time
from playwright.sync_api import sync_playwright

# Method 1: The pytest timeout annotation
@pytest.mark.timeout(2)
def test_pytest_timeout_annotation_works():
    """This test demonstrates that the @pytest.mark.timeout annotation works and halts hanging code."""
    time.sleep(10)

# Method 2: Playwright specific timeout
def test_playwright_internal_timeout():
    """This test demonstrates an internal framework timeout (Playwright) which should fail fast."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(1000)
        
        # This should timeout after 1 second because we use a bogus domain
        try:
            page.goto("http://invalid-domain.local.gemini", timeout=1000)
        except Exception as e:
            assert "Timeout" in str(e) or "ERR_NAME_NOT_RESOLVED" in str(e)
        finally:
            browser.close()
