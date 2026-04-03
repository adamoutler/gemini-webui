import pytest
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="function")
def page(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        page = context.new_page()
        page.set_default_timeout(60000)
        page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
        page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
        page.goto(server, timeout=15000)
        page.wait_for_selector(
            ".launcher, .terminal-instance", state="attached", timeout=15000
        )
        yield page
        context.close()
        browser.close()


@pytest.mark.prone_to_timeout
@pytest.mark.timeout(60)
def test_ui_add_host_with_env_vars(page, server):
    """Verify that a user can add a host with environment variables and they are loaded when editing."""
    expect(page.get_by_text("Select a Connection").first).to_be_visible(timeout=15000)

    # Open Settings
    page.locator('button[onclick="openSettings()"]').click()
    expect(page.locator("#settings-modal")).to_be_visible(timeout=15000)

    # Ensure add mode
    page.locator("#add-mode-btn").click()
    page.evaluate("clearHostForm()")

    # Fill in the new host details
    page.locator("#new-host-label").fill("Env Var Host")
    page.locator("#new-host-target").fill("user@127.0.0.1")

    # Add an environment variable
    page.locator("#add-env-var-btn").click()

    # Fill in the environment variable details
    # The newly added inputs should be the last ones in the container
    env_keys = page.locator("#env-vars-list input[placeholder*='Key']")
    env_vals = page.locator("#env-vars-list input[placeholder='Value']")

    env_keys.last.fill("MY_ENV_VAR")
    env_vals.last.fill("MY_VAL")

    # Click Add Host
    with page.expect_response("**/api/hosts") as response_info:
        page.locator("#add-host-btn").click()

    response = response_info.value
    assert response.status == 200, f"Failed to add host, status {response.status}"

    # Verify the host was added to the list in Settings
    expect(page.locator("#hosts-list")).to_contain_text("Env Var Host", timeout=15000)

    # Now let's click it to edit and verify env vars are populated
    page.locator("#hosts-list .session-item").filter(has_text="Env Var Host").click()

    # Verify it entered edit mode
    expect(page.locator("#add-host-btn")).to_have_text(
        import_re := __import__("re").compile(r"Update Host.*")
    )

    # Verify the env var is populated
    expect(
        page.locator("#env-vars-list input[placeholder*='Key']").first
    ).to_have_value("MY_ENV_VAR")
    expect(
        page.locator("#env-vars-list input[placeholder='Value']").first
    ).to_have_value("MY_VAL")

    # Remove the variable
    page.locator("#env-vars-list button.danger").first.click()
    expect(page.locator("#env-vars-list input")).to_have_count(0)

    # Update host
    with page.expect_response("**/api/hosts") as response_info:
        page.locator("#add-host-btn").click()

    response = response_info.value
    assert response.status == 200, f"Failed to update host, status {response.status}"

    # Verify empty env vars on edit
    page.locator("#hosts-list .session-item").filter(has_text="Env Var Host").click()
    expect(page.locator("#env-vars-list input")).to_have_count(0)

    # Clean up
    page.evaluate("closeSettings()")
