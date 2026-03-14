import pytest
from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.on("console", lambda msg: print("CONSOLE:", msg.text))
        page.goto("http://127.0.0.1:5002")
        page.wait_for_selector(".tab-instance.active", state="attached")
        print("Tab attached")
        
        page.evaluate("""() => {
            window._testLastActive = 1000;
            const socket = getGlobalSocket();
            const originalEmit = socket.emit.bind(socket);
            socket.emit = (event, ...args) => {
                if (event === 'get_management_sessions') {
                    const callback = args[args.length - 1];
                    if (typeof callback === 'function') {
                        console.log("Mocking get_management_sessions");
                        callback([{
                            "tab_id": "test_tab_1",
                            "title": "Test Session",
                            "is_orphaned": false,
                            "last_active": window._testLastActive,
                            "ssh_dir": "/tmp",
                            "ssh_target": null,
                            "resume": true
                        }]);
                    }
                    return socket;
                }
                return originalEmit(event, ...args);
            };
        }""")
        
        page.evaluate("""() => {
            const activeTab = document.querySelector('.tab-instance.active');
            if (activeTab) {
                const id = activeTab.id.replace('_instance', '');
                console.log("Found active tab:", id);
                refreshBackendSessionsList(id);
            } else {
                console.log("No active tab!");
            }
        }""")
        
        try:
            page.wait_for_selector(".session-item", timeout=5000)
            print("Found session item")
            node = page.locator('[id$="managed-session-tab_1-test_tab_1"] .status-node, [id$="managed-session-local-test_tab_1"] .status-node').first
            print("Node count:", node.count())
            has_flash = 'flash' in node.evaluate("el => el.className")
            print("Has flash:", has_flash)
            
            node.evaluate("el => el.classList.remove('flash')")
            print("Removed flash")
            
            page.evaluate("""() => {
                const activeTab = document.querySelector('.tab-instance.active');
                if (activeTab) {
                    const id = activeTab.id.replace('_instance', '');
                    refreshBackendSessionsList(id);
                }
            }""")
            page.wait_for_timeout(500)
            has_flash2 = 'flash' in node.evaluate("el => el.className")
            print("Has flash 2:", has_flash2)
            
            page.evaluate("window._testLastActive = 2000")
            page.evaluate("""() => {
                const activeTab = document.querySelector('.tab-instance.active');
                if (activeTab) {
                    const id = activeTab.id.replace('_instance', '');
                    refreshBackendSessionsList(id);
                }
            }""")
            page.wait_for_timeout(500)
            has_flash3 = 'flash' in node.evaluate("el => el.className")
            print("Has flash 3:", has_flash3)
        except Exception as e:
            print("Error:", e)
        browser.close()

if __name__ == "__main__":
    import subprocess, time, os
    proc = subprocess.Popen(["python3", "src/app.py"], env=dict(os.environ, PORT="5002", BYPASS_AUTH_FOR_TESTING="true"))
    time.sleep(3)
    try:
        run()
    finally:
        proc.terminate()
