import time
from playwright.sync_api import sync_playwright

def test():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage'
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            locale="en-US"
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = context.new_page()
        page.goto("https://www.google.com/search?q=4901313938669&udm=2&hl=en", timeout=20000)
        page.wait_for_timeout(3000)
        print("Page Title:", page.title())
        print("Page URL:", page.url)
        page.screenshot(path="scripts/stealth_google.png")
        browser.close()

if __name__ == "__main__":
    test()
