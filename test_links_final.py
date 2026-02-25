from playwright.sync_api import sync_playwright
import time

def run():
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp("http://172.22.0.10:9222")
            page = browser.contexts[0].pages[0]
            
            page.on("console", lambda msg: print(f"Browser console: {msg.text}"))
            
            print("Reloading...")
            page.reload()
            time.sleep(2)
            
            print("Starting session...")
            page.get_by_role("button", name="Start New").first.click()
            time.sleep(2)
            
            print("Hovering over terminal...")
            for y in range(150, 300, 10):
                page.mouse.move(300, y)
                time.sleep(0.05)
            
            browser.close()
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    run()
