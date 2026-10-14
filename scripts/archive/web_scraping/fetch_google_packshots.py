import os
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import json
import time
import requests
from playwright.sync_api import sync_playwright

COOKIE_FILE = "output/google_cookies.json"
OUTPUT_DIR = "output/barcode_google_hd_images"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def fetch_barcodes_batch(barcodes_list):
    if not os.path.exists(COOKIE_FILE):
        print(f"[!] Cookie file {COOKIE_FILE} not found.")
        return {}

    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900}
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        context.add_cookies(cookies)
        page = context.new_page()

        for idx, bc in enumerate(barcodes_list, start=1):
            bc_str = str(bc).strip()
            out_img = os.path.join(OUTPUT_DIR, f"{bc_str}.jpg")
            
            print(f"[{idx}/{len(barcodes_list)}] Searching Google Images for Barcode: {bc_str}...")
            try:
                page.goto(f"https://www.google.com/search?q={bc_str}&udm=2&hl=vi", timeout=15000)
                page.wait_for_timeout(1500)

                # Check if captcha popped up again
                if "sorry" in page.url:
                    print("  [!] Captcha encountered, stopping batch.")
                    break

                grid_imgs = page.locator("div#rso img, div#search img").all()
                saved = False
                for img in grid_imgs:
                    if img.is_visible():
                        img.screenshot(path=out_img)
                        print(f"  [+] Saved Google Packshot to {out_img}")
                        saved = True
                        break
                
                # Title
                title = ""
                try:
                    title_els = page.locator("div#rso div[role='heading'], div#rso h3, a[role='link']").all()
                    for t_el in title_els:
                        txt = t_el.inner_text().strip()
                        if txt and len(txt) > 3:
                            title = txt
                            break
                except Exception:
                    pass

                results[bc_str] = {
                    "saved": saved,
                    "image_path": out_img if saved else "",
                    "title": title
                }
            except Exception as e:
                print(f"  [!] Error: {e}")
                results[bc_str] = {"saved": False, "image_path": "", "title": ""}

            time.sleep(1)

        browser.close()
    return results

if __name__ == "__main__":
    test_bcs = ['8850157516457', '4901313938669', '8850043330273', '8850043337890', '8850043126456']
    res = fetch_barcodes_batch(test_bcs)
    print("\nBatch test complete:", res)
