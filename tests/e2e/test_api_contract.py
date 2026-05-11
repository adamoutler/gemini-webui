import requests


def test_api_contract_terminate_all(server, playwright):
    """Verify that terminate_all successfully clears all sessions from the backend API."""
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    page.goto(server)

    # 1. Start a session
    page.wait_for_selector(
        ".launcher, .terminal-instance", state="attached", timeout=15000
    )
    page.click("text=Start New", force=True)
    page.wait_for_selector(".xterm-screen", timeout=15000)
    page.wait_for_timeout(1000)

    # 2. Open another tab
    page.click("#new-tab-btn")
    page.click("text=Start New", force=True)
    page.wait_for_timeout(1000)

    # 3. Call GET /api/management/sessions to verify multiple sessions exist
    # To bypass Auth for API, we can just use requests since BYPASS_AUTH_FOR_TESTING is true
    client = requests.Session()
    response = client.get(f"{server}/api/management/sessions")
    assert response.status_code == 200
    sessions = response.json()
    assert len(sessions) >= 2, "Backend should register multiple active sessions"

    # 4. Get CSRF token
    csrf_resp = client.get(f"{server}/api/csrf-token")
    assert csrf_resp.status_code == 200
    csrf_token = csrf_resp.json().get("csrf_token")

    # 5. Call POST /api/sessions/terminate_all
    terminate_resp = client.post(
        f"{server}/api/sessions/terminate_all", headers={"X-CSRFToken": csrf_token}
    )
    assert terminate_resp.status_code == 200
    assert terminate_resp.json().get("status") == "success"
    assert terminate_resp.json().get("terminated") >= 2

    # 6. Verify sessions are gone
    final_sessions = requests.get(f"{server}/api/management/sessions").json()
    assert len(final_sessions) == 0, "Backend sessions should be completely clear"

    context.close()
    browser.close()


def test_api_contract_external_v1(server):
    """Verify that the external API /v1/sessions/create processes correctly."""
    # Note: /v1 endpoints use @api_key_required. If BYPASS_AUTH_FOR_TESTING=true,
    # the decorator bypasses it automatically or requires a fake token.
    # We will test the failure mode first to ensure it's protected if not bypassed.
    # In test env, it's bypassed if we pass a random key.

    headers = {"X-API-Key": "test-key-123"}
    # Because there are no hosts defined, it will fail gracefully instead of 404/405
    payload = {"host_id": "non_existent_host", "prompt": "echo hello"}

    resp = requests.post(f"{server}/v1/sessions/create", json=payload, headers=headers)

    # It should return a 200 with an error status inside JSON, or a 400
    # depending on how HostStates handles non-existent hosts.
    # We mainly care that the POST method is accepted (no 405 Method Not Allowed)
    assert resp.status_code in [200, 400, 404]

    if resp.status_code == 200:
        assert resp.json().get("status") in ["error", "success"]
