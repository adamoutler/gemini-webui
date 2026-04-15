import pytest
import os
import subprocess
import time
import random
from playwright.sync_api import sync_playwright, expect


@pytest.fixture(scope="session")
def ssh_target_container(test_data_dir):
    # Wait for the server to generate the key
    ssh_dir = os.path.join(str(test_data_dir), ".ssh")
    pub_key_path = os.path.join(ssh_dir, "id_ed25519.pub")

    # Generate SSH key manually for test so we don't depend on server startup race
    os.makedirs(ssh_dir, exist_ok=True)
    key_path = os.path.join(ssh_dir, "id_ed25519")
    if not os.path.exists(key_path):
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", key_path, "-C", "test-key"],
            check=True,
        )

    with open(pub_key_path, "r") as f:
        pub_key = f.read().strip()

    container_name = "test-gemini-ssh-target"
    subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)

    port = str(random.randint(2200, 2500))

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

    # Wait for container ssh to be ready
    for _ in range(30):
        try:
            result = subprocess.run(
                ["docker", "exec", container_name, "bash", "-c", "echo ready"],
                capture_output=True,
                text=True,
            )
            if "ready" in result.stdout:
                time.sleep(2)  # Wait for sshd to initialize
                break
        except Exception:
            pass
        time.sleep(1)

    # Install python3 and copy app
    subprocess.run(
        [
            "docker",
            "exec",
            container_name,
            "apk",
            "add",
            "--no-cache",
            "python3",
            "bash",
        ],
        check=True,
    )

    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    src_path = os.path.join(project_root, "src")

    # Put src dir at /app/src
    subprocess.run(
        ["docker", "exec", container_name, "mkdir", "-p", "/app"], check=True
    )
    subprocess.run(["docker", "cp", src_path, f"{container_name}:/app/src"], check=True)

    # Create the gemini executable wrapper
    script = '#!/bin/bash\\nPYTHONPATH=/app python3 /app/src/mock_gemini_cli.py "$@"'
    subprocess.run(
        [
            "docker",
            "exec",
            container_name,
            "bash",
            "-c",
            f"echo -e '{script}' > /usr/local/bin/gemini && chmod +x /usr/local/bin/gemini",
        ],
        check=True,
    )

    yield port

    # Teardown
    subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)


@pytest.fixture(scope="function")
def page(server, playwright):
    p = playwright
    if True:
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
def test_ssh_drag_and_drop_upload(page, test_data_dir, ssh_target_container):
    # Set up the SSH connection in the UI
    # First we need to make sure we are on the launcher or settings
    expect(page.locator(".launcher").first).to_be_visible(timeout=15000)

    # Open settings modal to add host
    page.locator('button[data-onclick="openSettings()"]').click()
    expect(page.locator("#settings-modal")).to_be_visible(timeout=15000)

    # Fill out the form
    page.locator("#new-host-label").fill("E2E SSH Test")

    # We use localhost but docker host gateway could also be used depending on network.
    # Since port is mapped on host, 'localhost' should work from the app container.
    # Actually, Playwright is running on the host, and the server fixture runs the Flask app on the host too!
    # Wait, the Flask app is running as a subprocess on the host (where pytest runs).
    # So the Flask app can connect to '127.0.0.1:{port}' or 'localhost:{port}' for ssh!
    ssh_port = ssh_target_container
    page.locator("#new-host-target").fill(f"testuser@127.0.0.1:{ssh_port}")
    page.locator("#new-host-dir").fill("/config/remote_workspace")

    # Save host
    page.locator("#add-host-btn").click()

    # Close settings modal
    page.evaluate("closeSettings()")

    # Connect using the new host by clicking 'Start New'
    card = page.locator(".connection-card").filter(has_text="E2E SSH Test").first
    card.locator("button", has_text="Start New").click()

    # Wait for the terminal to appear and connect
    expect(page.locator("#active-connection-info")).to_be_visible(timeout=15000)

    page.wait_for_timeout(3000)

    # Check dropzone became active
    page.evaluate("""() => {
        const dragEvent = new DragEvent('dragover', { bubbles: true, cancelable: true });
        document.dispatchEvent(dragEvent);
    }""")
    expect(page.locator(".drop-zone")).to_have_class("drop-zone active")

    # Trigger drop
    page.evaluate("""() => {
        const file = new File(["ssh dropped content e2e"], "e2e_ssh_upload.txt", { type: 'text/plain' });

        const dropEvent = new Event('drop', { bubbles: true, cancelable: true });
        dropEvent.dataTransfer = {
            items: [
                {
                    webkitGetAsEntry: () => ({
                        isFile: true,
                        isDirectory: false,
                        name: 'e2e_ssh_upload.txt',
                        file: (cb) => cb(file)
                    })
                }
            ],
            files: [file]
        };
        document.dispatchEvent(dropEvent);
    }""")

    # Check dropzone inactive
    expect(page.locator(".drop-zone")).not_to_have_class("drop-zone active")

    # Wait for upload to complete
    page.wait_for_timeout(3000)

    # The CRITICAL ASSERTION
    # Run docker exec to verify the file is there!
    container_name = "test-gemini-ssh-target"

    # Wait until file exists (up to 10 seconds, though it should be instant if not buffered)
    for _ in range(10):
        # We check /config/remote_workspace/e2e_ssh_upload.txt
        result = subprocess.run(
            [
                "docker",
                "exec",
                container_name,
                "cat",
                "/config/remote_workspace/e2e_ssh_upload.txt",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            assert result.stdout == "ssh dropped content e2e"
            break
        time.sleep(1)
    else:
        # If loop exhausts, fail with the last error
        pytest.fail(
            f"File not found in SSH container or content mismatch. Last output: {result.stderr}"
        )
