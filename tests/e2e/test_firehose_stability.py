import pytest
from playwright.sync_api import Page
import os
import json


@pytest.mark.timeout(120)
def test_firehose_stability(page: Page, server):
    # Navigate to the app
    page.goto(server)

    # Wait for the app to load and the connection card to be visible
    page.wait_for_selector(".connection-card", timeout=15000)

    # Click "Start New" on the first connection (Local)
    page.locator('button:has-text("Start New")').first.click()

    # Wait for terminal to be ready
    page.wait_for_selector(".xterm-rows")
    page.wait_for_timeout(1000)

    logs = []
    page.on("console", lambda msg: logs.append({"type": msg.type, "text": msg.text}))

    # Run a high-volume output command to simulate the firehose
    page.keyboard.type("seq 1 20000; echo 'DONE_FIREHOSE'\n")

    # Wait for DONE_FIREHOSE to appear
    page.wait_for_function(
        """() => {
        const rows = document.querySelectorAll('.xterm-rows div');
        for (let row of rows) {
            if (row.innerText.includes('DONE_FIREHOSE')) return true;
        }
        return false;
    }""",
        timeout=60000,
    )

    page.wait_for_timeout(1000)

    flap_errors = [
        log_item["text"] for log_item in logs if "SOCKET_FLAP" in log_item["text"]
    ]
    perf_alerts = [
        log_item["text"] for log_item in logs if "PERF_ALERT" in log_item["text"]
    ]

    # Ensure there are no flaps
    assert len(flap_errors) == 0, f"Socket flapped during firehose test: {flap_errors}"

    os.makedirs("docs/qa", exist_ok=True)

    # Check if resize reflows without artifacts. We can rapidly resize.
    page.set_viewport_size({"width": 1200, "height": 800})
    page.wait_for_timeout(500)
    page.screenshot(path="docs/qa/terminal-resize-before.png")

    page.set_viewport_size({"width": 500, "height": 800})
    page.wait_for_timeout(500)
    page.screenshot(path="docs/qa/terminal-resize-after.png")

    # Save console screenshot by drawing the logs to the screen
    escaped_logs_json = json.dumps(json.dumps(logs))
    page.evaluate(f"""() => {{
        const div = document.createElement('div');
        div.id = 'fake-console';
        div.style.position = 'absolute';
        div.style.top = '10%';
        div.style.left = '10%';
        div.style.backgroundColor = 'black';
        div.style.color = 'lime';
        div.style.padding = '20px';
        div.style.zIndex = '9999';
        div.innerHTML = '<h3>Console Logs:</h3><pre>' + {escaped_logs_json} + '</pre>';
        document.body.appendChild(div);
    }}""")
    page.screenshot(path="docs/qa/firehose-stress-console.png")

    with open("docs/qa/test-results.json", "w") as f:
        json.dump(
            {"flaps": len(flap_errors), "perf_alerts": len(perf_alerts), "logs": logs},
            f,
        )
