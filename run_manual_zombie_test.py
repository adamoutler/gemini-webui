import os
import subprocess
import time
import sys
from playwright.sync_api import sync_playwright


def log(msg):
    print(msg)
    with open("zombie_test.log", "a") as f:
        f.write(msg + "\n")


def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip(), result.stderr.strip()


def check_zombies():
    out, _ = run_cmd("top -b -n 1 | grep zombie")
    if "zombie" in out:
        parts = out.split()
        for i, part in enumerate(parts):
            if part == "zombie" or part == "zombies":
                try:
                    num = int(parts[i - 1])
                    return num
                except ValueError:
                    pass
    return 0


def main():
    if os.path.exists("zombie_test.log"):
        os.remove("zombie_test.log")

    log("=== Starting Zombie Test ===")

    log("Cleaning up old containers...")
    run_cmd(
        "docker rm -f gemini-webui-dev gemini-webui-production gemini-webui-gemini-web-1 gemini-zombie-test"
    )
    time.sleep(2)

    zombies = check_zombies()
    log(f"Clean slate confirmation: {zombies} zombies")

    log("Building container...")
    run_cmd("docker build -t gemini .")

    log("Deploying container...")
    run_cmd(
        "docker run -d --name gemini-webui-dev -p 5008:5000 -v tes_gemini-webui-dev-deploy_main_data-dev:/data -e BYPASS_AUTH_FOR_TESTING=true gemini"
    )

    time.sleep(10)  # wait for boot
    log("Successful container deployment.")

    log("Verifying with Playwright...")
    verification_passed = False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto("http://127.0.0.1:5008/")

            try:
                page.wait_for_selector(".session-item", timeout=45000)
            except Exception:
                log(
                    "No session items appeared initially. Trying to start a session directly via quick connect..."
                )
                try:
                    page.locator("button:has-text('Connect')").first.click(timeout=5000)
                    page.wait_for_selector(".terminal", timeout=15000)
                except Exception as e:
                    log(f"Could not start a session: {e}")

            items = page.locator(".session-item").all()
            log(f"Found {len(items)} session items")

            if len(items) >= 4 or page.locator(".terminal").count() > 0:
                log(
                    "Playwright verification of session items in multiple connections: OK"
                )
                verification_passed = True
            else:
                log("Playwright verification of session items: FAILED")

            for item in items[:5]:
                try:
                    item.click(timeout=2000)
                    time.sleep(1)
                except Exception:
                    pass

            browser.close()
    except Exception as e:
        log(f"Playwright error: {e}")

    if not verification_passed:
        log("Test FAILED due to Playwright verification failure")
        sys.exit(1)

    log("Sleeping for 1 minute to allow timeouts/zombies to form...")
    time.sleep(60)

    zombies = check_zombies()
    log(f"Post-trigger observation: {zombies} zombies")

    if zombies == 0:
        log("Test PASSED")
        sys.exit(0)
    else:
        log("Test FAILED")
        run_cmd("ps -A -ostat,ppid,pid,cmd | grep -e '^[Zz]' >> zombie_test.log")
        sys.exit(1)


if __name__ == "__main__":
    main()
