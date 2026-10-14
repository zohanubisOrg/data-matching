import os
import sys
import time
import requests
from playwright.sync_api import sync_playwright

def test_fetch_google_images(barcode):
    print(f"\n==========================================")
    print(f"Testing Barcode on Google Images: {barcode}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()
        
        url = f"https://www.google.com/search?q={barcode}&tbm=isch&hl=en"
        page.goto(url, timeout=20000)
        page.wait_for_timeout(2000)
        
        # Check if consent dialog exists
        try:
            accept_btn = page.locator("button:has-text('Accept all'), button:has-text('I agree'), button:has-text('Accept')")
            if accept_btn.count() > 0:
                accept_btn.first.click()
                page.wait_for_timeout(1000)
        except Exception:
            pass

        # Find first image results
        # In Google Images (udm=2), thumbnails are inside divs or img tags
        img_elements = page.locator("div[data-ved] img, div#search img")
        count = img_elements.count()
        print(f"Found {count} img elements on page")
        
        # Click the first image result to open the full-res preview panel!
        found_full_img = None
        found_title = ""
        
        for idx in range(min(5, count)):
            el = img_elements.nth(idx)
            src = el.get_attribute("src") or el.get_attribute("data-src") or ""
            if not src.startswith("http") and not src.startswith("data:image"):
                continue
            
            try:
                el.click(timeout=3000)
                page.wait_for_timeout(1500)
                
                # In Google Images, clicking opens a side/preview panel with the full image
                preview_imgs = page.locator("div[jsname] img[src^='http']")
                for p_idx in range(preview_imgs.count()):
                    p_src = preview_imgs.nth(p_idx).get_attribute("src") or ""
                    if p_src and not "gstatic" in p_src and not "google" in p_src and ("jpg" in p_src or "jpeg" in p_src or "png" in p_src or "webp" in p_src):
                        found_full_img = p_src
                        break
            except Exception as e:
                pass
            
            if found_full_img:
                break
                
        # Also grab title / source
        try:
            title_el = page.locator("h3, a[data-navigation] div, div[data-attrid] div")
            if title_el.count() > 0:
                found_title = title_el.first.inner_text()
        except Exception:
            pass

        print(f"Result for {barcode}:")
        print(f"  Title: {found_title}")
        print(f"  Full Image URL: {found_full_img}")
        
        browser.close()
        return found_full_img

if __name__ == "__main__":
    test_fetch_google_images("4901313938669")
