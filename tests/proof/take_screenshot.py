import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("http://127.0.0.1:8080/tests/test_pulse.html")
    time.sleep(1.1)
    page.screenshot(path="tests/pulse_screenshot.png")
    browser.close()
