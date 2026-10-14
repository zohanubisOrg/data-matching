import os
import sys
import json
import time
import requests
import base64
from playwright.sync_api import sync_playwright

COOKIE_FILE = "output/google_cookies.json"
OUT_IMG = "output/barcode_google_hd_images/4901313938669.jpg"

def extract_google_image():
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

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
        page.goto("https://www.google.com/search?q=4901313938669&udm=2&hl=vi", timeout=20000)
        page.wait_for_timeout(2000)

        # In Google Images udm=2, the visible product images in grid:
        grid_imgs = page.locator("div#rso img, div#search img").all()
        print(f"Grid images count: {len(grid_imgs)}")

        saved = False
        for idx, img in enumerate(grid_imgs):
            if not img.is_visible():
                continue
            
            src = img.get_attribute("src") or ""
            print(f"Img {idx}: src starts with {src[:40]}")
            
            # Click the image card
            try:
                img.click(timeout=3000)
                page.wait_for_timeout(1500)
                
                # Check for high-res preview panel
                side_imgs = page.locator("div[role='dialog'] img[src^='http'], div[jsname] img[src^='http']").all()
                for s_img in side_imgs:
                    s_src = s_img.get_attribute("src") or ""
                    if "gstatic" not in s_src and "google" not in s_src and any(ext in s_src for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                        print(f"  Found full-res preview image URL: {s_src}")
                        try:
                            r = requests.get(s_src, headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
                            if r.status_code == 200 and len(r.content) > 5000:
                                with open(OUT_IMG, "wb") as f:
                                    f.write(r.content)
                                print(f"[+] Downloaded full-res {len(r.content)} bytes to {OUT_IMG}!")
                                saved = True
                                break
                        except Exception:
                            pass
            except Exception as e:
                print(f"Click error: {e}")

            if saved:
                break

            # Fallback: if data url or thumbnail, screenshot the visible element
            if not saved:
                img.screenshot(path=OUT_IMG)
                print(f"[+] Saved high quality element screenshot to {OUT_IMG}!")
                saved = True
                break

        browser.close()

if __name__ == "__main__":
    extract_google_image()
