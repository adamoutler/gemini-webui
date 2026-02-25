from playwright.sync_api import sync_playwright
import time

def run():
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp("http://172.22.0.10:9222")
            page = browser.contexts[0].pages[0]
            
            result = page.evaluate("""() => {
                const tab = tabs.find(t => t.state === 'terminal');
                const term = tab.term;
                const lines = [];
                for (let i = 20; i < 50; i++) {
                    const l = term.buffer.active.getLine(i);
                    if (l) lines.push({idx: i, stripped: l.translateToString(true)});
                }
                return lines;
            }""")
            
            for line in result:
                print(f"{line['idx']}: '{line['stripped']}'")
            
            browser.close()
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    run()
