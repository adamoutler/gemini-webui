import subprocess
import time
import os
import sys

LOG_FILE = "zombie_test.log"

def log(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def get_zombies():
    try:
        res = subprocess.check_output("ps -aux | awk '$8==\"Z\" || $8==\"Z+\"'", shell=True, text=True)
        return res.strip()
    except:
        return ""

def run_step(name, cmd):
    log(f"STEP: {name}")
    try:
        # Run command and capture output
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode != 0:
            log(f"  FAILED: {res.stderr}")
            return False
        log(f"  SUCCESS: {res.stdout.strip()[:200]}")
        return True
    except Exception as e:
        log(f"  EXCEPTION: {e}")
        return False

def main():
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
    
    log("=== STARTING ZOMBIE QA TEST ===")
    
    # 1. Clean Slate
    log("1. Cleaning Slate...")
    subprocess.run("docker stop gemini-webui-dev || true", shell=True)
    subprocess.run("docker rm gemini-webui-dev || true", shell=True)
    log("   Waiting 60 seconds for reap...")
    time.sleep(60)
    
    zombies = get_zombies()
    if zombies:
        log(f"   FAIL: Zombies exist on host before test:\n{zombies}")
        # sys.exit(1) # We continue anyway but mark as fail
    else:
        log("   PASS: No zombies on host.")

    # 2. Deploy
    log("2. Deploying test container...")
    deploy_cmd = "docker run -d --name gemini-webui-dev -p 5008:5000 -v tes_gemini-webui-dev-deploy_main_data-dev:/data -e BYPASS_AUTH_FOR_TESTING=true ghcr.io/adamoutler/gemini-webui-dev:latest"
    if not run_step("Docker Run", deploy_cmd):
        sys.exit(1)
    
    log("   Waiting 10 seconds for startup...")
    time.sleep(10)

    # 3. Verify and Trigger
    log("3. Verifying UI and Triggering fetches...")
    trigger_script = """
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    await page.goto('http://127.0.0.1:5008/', { timeout: 30000 });
    await page.waitForSelector('.session-item', { timeout: 15000 });
    console.log("SUCCESS: Session items found");
  } catch(e) {
    console.log("FAIL: " + e.message);
  }
  await browser.close();
})();
"""
    with open("temp_trigger.js", "w") as f:
        f.write(trigger_script)
    
    if not run_step("Playwright Trigger", "node temp_trigger.js"):
        log("   WARNING: Playwright failed to find sessions. This might be part of the bug.")

    # 4. Observe
    log("4. Observing for zombies...")
    log("   Waiting 60 seconds...")
    time.sleep(60)
    
    zombies = get_zombies()
    if zombies:
        log(f"   FAIL: ZOMBIES DETECTED:\n{zombies}")
    else:
        log("   FINAL PASS: ZERO ZOMBIES DETECTED.")
    
    log("=== QA TEST FINISHED ===")

if __name__ == "__main__":
    main()
