from playwright.sync_api import sync_playwright
import time

def run():
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp("http://172.22.0.10:9222")
            page = browser.contexts[0].pages[0]
            
            print("Reloading...")
            page.reload()
            time.sleep(2)
            
            print("Starting session...")
            page.get_by_role("button", name="Start New").first.click()
            time.sleep(3)
            
            result = page.evaluate("""() => {
                const tab = tabs.find(t => t.state === 'terminal');
                const lines = [];
                for (let i = 0; i < 50; i++) {
                    const l = tab.term.buffer.active.getLine(i);
                    if (l) lines.push(l.translateToString(true));
                }
                return lines.join('\\n');
            }""")
            print("--- Terminal Content ---")
            print(result)
            print("--- End ---")
            
            browser.close()
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    run()
