import pytest
import os
import subprocess
import time
import random
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="session")
def ssh_target_container_no_gemini(test_data_dir, playwright):
    ssh_dir = os.path.join(str(test_data_dir), ".ssh")
    pub_key_path = os.path.join(ssh_dir, "id_ed25519.pub")

    os.makedirs(ssh_dir, exist_ok=True)
    key_path = os.path.join(ssh_dir, "id_ed25519")
    if not os.path.exists(key_path):
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", key_path, "-C", "test-key"],
            check=True,
        )

    with open(pub_key_path, "r") as f:
        pub_key = f.read().strip()

    container_name = "test-ssh-env-vars"
    subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)

    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = str(s.getsockname()[1])

    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "-p",
            f"{port}:2222",
            "-e",
            f"PUBLIC_KEY={pub_key}",
            "-e",
            "USER_PASSWORD=password",
            "-e",
            "USER_NAME=testuser",
            "lscr.io/linuxserver/openssh-server:latest",
        ],
        check=True,
    )

    ready = False
    for _ in range(90):
        try:
            result = subprocess.run(
                [
                    "ssh",
                    "-i",
                    key_path,
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "UserKnownHostsFile=/dev/null",
                    "-p",
                    str(port),
                    "testuser@127.0.0.1",
                    "echo ready",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if "ready" in result.stdout:
                ready = True
                break
        except Exception:
            pass
        time.sleep(1)

    if not ready:
        err = result.stderr if "result" in locals() else "No result"
        raise Exception(
            f"Docker container {container_name} failed to become ready in time. stderr: {err}"
        )

    subprocess.run(
        ["docker", "exec", container_name, "apk", "add", "--no-cache", "bash"],
        check=True,
    )

    yield port

    subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)


@pytest.fixture(scope="function")
def page(server, playwright):
    p = playwright
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    page.set_default_timeout(60000)
    page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
    page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
    page.goto(server)
    page.wait_for_selector(".launcher, .terminal-instance", state="attached")
    yield page
    context.close()
    browser.close()


@pytest.mark.prone_to_timeout
@pytest.mark.timeout(120)
def test_e2e_session_env_vars_injected(
    page, tmp_path, ssh_target_container_no_gemini, playwright
):
    page.locator("#new-tab-btn").click()
    expect(page.locator(".launcher").first).to_be_visible(timeout=15000)

    page.locator('button[data-onclick="openSettings()"]').click()
    expect(page.locator("#settings-modal")).to_be_visible(timeout=15000)

    page.locator("#new-host-label").fill("Env Var SSH Test")
    ssh_port = ssh_target_container_no_gemini
    page.locator("#new-host-target").fill(f"testuser@127.0.0.1:{ssh_port}")
    page.locator("#new-host-dir").fill("/config")

    page.locator("#add-env-var-btn").click()
    env_keys = page.locator("#env-vars-list input[placeholder*='Key']")
    env_vals = page.locator("#env-vars-list input[placeholder='Value']")
    env_keys.last.fill("MY_TEST_VAR")
    env_vals.last.fill("INJECTED_VALUE_123")

    page.locator("#add-host-btn").click()
    page.evaluate("closeSettings()")

    card = page.locator(".connection-card").filter(has_text="Env Var SSH Test").first
    card.locator("button", has_text="Start New").click()

    expect(page.locator("#active-connection-info")).to_be_visible(timeout=15000)
    page.wait_for_timeout(3000)

    # We drop into bash because gemini is not found.
    # We should wait for bash prompt.
    page.wait_for_timeout(8000)
    page.screenshot(path="terminal_before_typing.png")
    page.locator(".tab-instance.active .xterm").first.click()
    page.keyboard.type("echo EXPECTED_${MY_TEST_VAR}_END", delay=50)
    page.keyboard.press("Enter")

    # Print terminal output to help debug
    term_output = page.evaluate(
        """() => {
        const tab = tabs.find(t => t.id === activeTabId);
        if (tab && tab.term) {
            let out = "";
            for (let i = 0; i < tab.term.buffer.active.length; i++) {
                const line = tab.term.buffer.active.getLine(i);
                if (line) out += line.translateToString() + "\\n";
            }
            return out;
        }
        return "No terminal";
    }"""
    )
    print("TERMINAL OUTPUT:")
    print(term_output)

    # Check the terminal output via xterm.js API
    page.wait_for_function(
        """() => {
        if (typeof tabs === 'undefined' || typeof activeTabId === 'undefined') return false;
        const tab = tabs.find(t => t.id === activeTabId);
        if (tab && tab.term) {
            let out = "";
            for (let i = 0; i < Math.min(50, tab.term.buffer.active.length); i++) {
                const line = tab.term.buffer.active.getLine(i);
                if (line) out += line.translateToString();
            }
            return out.includes("EXPECTED_INJECTED_VALUE_123_END");
        }
        return false;
    }""",
        timeout=15000,
    )


@pytest.mark.prone_to_timeout
@pytest.mark.timeout(120)
def test_e2e_local_session_env_vars_injected(page, tmp_path, playwright):
    page.locator("#new-tab-btn").click()
    expect(page.locator(".launcher").first).to_be_visible(timeout=15000)

    page.locator('button[data-onclick="openSettings()"]').click()
    expect(page.locator("#settings-modal")).to_be_visible(timeout=15000)

    # Edit Local host
    page.locator("#hosts-list .session-item").filter(has_text="Local").click()

    page.locator("#add-env-var-btn").click()
    env_keys = page.locator("#env-vars-list input[placeholder*='Key']")
    env_vals = page.locator("#env-vars-list input[placeholder='Value']")
    env_keys.last.fill("LOCAL_TEST_VAR")
    env_vals.last.fill("LOCAL_VAL_999")

    with page.expect_response("**/api/hosts") as response_info:
        page.locator("#add-host-btn").click()
    assert response_info.value.status == 200

    page.evaluate("closeSettings()")

    card = page.locator(".connection-card").filter(has_text="Local").first
    card.locator("button", has_text="Start New").click()

    expect(page.locator("#active-connection-info")).to_be_visible(timeout=15000)
    page.wait_for_timeout(3000)

    # We should wait for bash prompt.
    page.wait_for_timeout(8000)
    page.locator(".tab-instance.active .xterm").first.click()

    # Print terminal output to help debug
    term_output = page.evaluate(
        """() => {
        const tab = tabs.find(t => t.id === activeTabId);
        if (tab && tab.term) {
            let out = "";
            for (let i = 0; i < tab.term.buffer.active.length; i++) {
                const line = tab.term.buffer.active.getLine(i);
                if (line) out += line.translateToString() + "\\n";
            }
            return out;
        }
        return "No terminal";
    }"""
    )
    print("TERMINAL OUTPUT:")
    print(term_output)

    # Check the terminal output via xterm.js API
    page.wait_for_function(
        """() => {
        if (typeof tabs === 'undefined' || typeof activeTabId === 'undefined') return false;
        const tab = tabs.find(t => t.id === activeTabId);
        if (tab && tab.term) {
            let out = "";
            for (let i = 0; i < Math.min(50, tab.term.buffer.active.length); i++) {
                const line = tab.term.buffer.active.getLine(i);
                if (line) out += line.translateToString();
            }
            return out.includes("EXPECTED_LOCAL_VAL_999_END");
        }
        return false;
    }""",
        timeout=15000,
    )
