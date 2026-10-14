import os
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

COOKIE_FILE = "output/google_cookies.json"
OUTPUT_DIR = "output/barcode_google_hd_images"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(os.path.dirname(COOKIE_FILE), exist_ok=True)

def open_browser_and_bypass():
    print("\n========================================================")
    print("[*] ĐANG MỞ TRÌNH DUYỆT ĐỂ BẠN GIẢI CAPTCHA GOOGLE...")
    print("[*] Vui lòng nhìn lên màn hình: Trình duyệt Google sẽ mở ra.")
    print("[*] Bạn chỉ cần tích chọn 'I am not a robot' trên màn hình.")
    print("========================================================\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--start-maximized'
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            viewport=None
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        page = context.new_page()
        page.goto("https://www.google.com/search?q=4901313938669&udm=2&hl=vi")

        print("[*] Chờ bạn giải captcha (hoặc nếu trang kết quả đã hiện ra)...")
        # Polling wait until user bypasses captcha (URL does not contain 'sorry' and search results load)
        max_wait = 180 # 3 minutes
        start_time = time.time()
        bypassed = False

        while time.time() - start_time < max_wait:
            curr_url = page.url
            if "sorry" not in curr_url and ("google.com/search" in curr_url or "udm=2" in curr_url):
                # Verify that images or content loaded
                try:
                    if page.locator("div[data-ved] img, div#search img, div#rso img").count() > 0:
                        bypassed = True
                        break
                except Exception:
                    pass
            time.sleep(2)

        if bypassed:
            print("\n[+] ĐÃ BYPASS THÀNH CÔNG! Đang lưu cookie phiên làm việc...")
            cookies = context.cookies()
            with open(COOKIE_FILE, "w", encoding="utf-8") as f:
                json.dump(cookies, f, indent=2)
            print(f"[+] Đã lưu {len(cookies)} cookies vào: {COOKIE_FILE}")
            
            # Chờ thêm 2s để trang render đầy đủ
            page.wait_for_timeout(2000)
            page.screenshot(path="output/bypassed_success.png")
            print("[+] Đã chụp màn hình kết quả tại: output/bypassed_success.png")
        else:
            print("[!] Hết thời gian chờ giải captcha. Vui lòng thử lại.")

        browser.close()
        return bypassed

if __name__ == "__main__":
    open_browser_and_bypass()
