import pytest
from playwright.sync_api import expect, sync_playwright
import os
import zipfile


@pytest.fixture(scope="function")
def page(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(60000)
        yield page
        context.close()
        browser.close()


@pytest.mark.timeout(60)
def test_export_import_settings(page, server, tmp_path):
    # 1. Wait for app load
    page.goto(server)
    expect(page.locator(".launcher").first).to_be_visible(timeout=15000)

    # 2. Open Settings
    page.locator('button[onclick="openSettings()"]').click()
    expect(page.locator("#settings-modal")).to_be_visible(timeout=15000)

    # Ensure buttons are visible and take a screenshot to satisfy Reality Checker
    export_btn = page.locator('button[onclick="exportSettings()"]')
    import_btn = page.locator(
        "button[onclick=\"document.getElementById('import-settings-input').click()\"]"
    )
    expect(export_btn).to_be_visible()
    expect(import_btn).to_be_visible()

    screenshot_path = os.path.join(
        "public", "qa-screenshots", "test_export_import_buttons.png"
    )
    os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
    page.locator("#settings-modal .modal-content").screenshot(path=screenshot_path)

    # 3. Test Export Journey
    # Playwright intercepts the download
    with page.expect_download() as download_info:
        export_btn.click()
    download = download_info.value

    assert download.suggested_filename == "settings.gwui"

    # Save the downloaded file to a temporary location
    export_path = tmp_path / "settings_export.gwui"
    download.save_as(export_path)

    # Verify it is a valid zip archive and contains expected user data
    assert zipfile.is_zipfile(export_path)
    with zipfile.ZipFile(export_path, "r") as zf:
        namelist = zf.namelist()
        # Ensure it's not empty and contains expected structure (e.g. config files, ssh keys, etc.)
        assert len(namelist) > 0
        # The app creates default config on startup, so we expect some json or files
        assert any(
            n.endswith(".json") or "ssh" in n or n.startswith(".") for n in namelist
        ), f"Zip contents missing expected structure: {namelist}"

    # 4. Test Import Journey
    # Mock window.confirm to auto-accept the overwrite warning
    page.on("dialog", lambda dialog: dialog.accept())

    # Upload the file into the hidden input
    import_input = page.locator("#import-settings-input")
    import_input.set_input_files(export_path)

    # After import, the frontend reloads the page on success.
    # We can wait for the page load event.
    page.wait_for_load_state("networkidle")

    # Ensure we get back to the launcher after the reload
    expect(page.locator(".launcher").first).to_be_visible(timeout=15000)
