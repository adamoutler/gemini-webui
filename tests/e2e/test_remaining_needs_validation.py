import pytest
import os
import stat
import time
from playwright.sync_api import Page, expect


@pytest.fixture(scope="function")
def page(server, playwright):
    from playwright.sync_api import sync_playwright

    p = playwright
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    page.set_default_timeout(60000)
    page.goto(server)
    yield page
    context.close()
    browser.close()


def test_app_install_indicator_visibility(page, server, playwright):
    # Load page in standard browser mode (not standalone)
    page.goto(f"{server}/")

    # The banner should be visible initially
    # Wait for the checkInstallationStatus logic to run
    banner = page.locator("#install-banner")
    expect(banner).to_be_visible(timeout=10000)
    expect(banner).to_contain_text("Organize your sessions! Install GemWebUI as an app")

    # Dismiss the banner
    close_btn = banner.locator("button")
    close_btn.click()
    expect(banner).not_to_be_visible()

    # Reload page - should stay hidden due to localStorage
    page.reload()
    expect(page.locator("#install-banner")).not_to_be_visible()


def test_ssh_socket_hardening(playwright):
    # This check runs on the host
    # We need to trigger an SSH connection first to ensure the directory exists
    # But we can also just check the process_manager logic via a unit test if needed.
    # Here we'll check if the directory mentioned in the codebase exists with correct permissions

    uid = os.getuid()
    # Priority paths from investigation: XDG_RUNTIME_DIR or /run/user/$UID
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime_dir:
        runtime_dir = f"/run/user/{uid}"

    base_socket_dir = os.path.join(runtime_dir, "gemini_ssh_mux")

    # If it doesn't exist, we'll try to find it in /tmp as a fallback (though the fix should avoid /tmp)
    if not os.path.exists(base_socket_dir):
        base_socket_dir = "/tmp/gemini_ssh_mux"

    if os.path.exists(base_socket_dir):
        mode = os.stat(base_socket_dir).st_mode
        # Check for 0700 (drwx------)
        assert stat.S_IMODE(mode) == 0o700
        print(f"Verified permissions for {base_socket_dir}: {oct(stat.S_IMODE(mode))}")
    else:
        pytest.skip(
            f"SSH socket directory {base_socket_dir} not found. Trigger an SSH connection to test."
        )
