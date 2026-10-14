import os
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
import re
import json
import requests
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}

def fetch_by_barcode(bc, expected_name=""):
    print(f"\n==========================================")
    print(f"Barcode: {bc} | Hint: {expected_name}")
    
    found_images = []
    found_title = ""
    
    # 1. Try OpenFoodFacts API
    try:
        url = f"https://world.openfoodfacts.org/api/v2/product/{bc}.json"
        r = requests.get(url, headers={'User-Agent': 'RabutaApp/1.0 (contact@rabuta.dk)'}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == 1:
                p = data.get("product", {})
                title = p.get("product_name_en") or p.get("product_name")
                img = p.get("image_front_url") or p.get("image_url")
                if title:
                    found_title = title
                if img:
                    found_images.append(("OpenFoodFacts", img))
    except Exception as e:
        pass

    # 2. Try Google Search (Direct query with barcode + ean)
    try:
        search_url = f"https://www.google.com/search?q={bc}+{expected_name.split()[0] if expected_name else ''}&tbm=isch&hl=en"
        r = requests.get(search_url, headers=HEADERS, timeout=8)
        if r.status_code == 200:
            # Google images HTML contains thumbnails and some direct image sources
            urls = re.findall(r'https://[^"\'\s<>]+?\.(?:jpg|jpeg|png|webp)', r.text)
            clean_urls = [u for u in urls if 'gstatic.com' not in u and 'google.com' not in u and 'wikimedia' not in u]
            for u in clean_urls[:3]:
                found_images.append(("Google_Image", u))
    except Exception as e:
        pass

    # 3. Try Bing / DuckDuckGo if needed
    try:
        ddg_url = f"https://html.duckduckgo.com/html/?q={bc}"
        r = requests.get(ddg_url, headers=HEADERS, timeout=5)
        soup = BeautifulSoup(r.text, 'html.parser')
        snippets = [a.get_text() for a in soup.find_all('a', class_='result__snippet')]
        if snippets and not found_title:
            found_title = snippets[0][:80]
    except Exception:
        pass

    print(f"  Result Title: {found_title or 'N/A'}")
    print(f"  Images Found: {len(found_images)}")
    for src, img_url in found_images[:3]:
        print(f"    [{src}] {img_url}")

if __name__ == "__main__":
    test_samples = [
        ('8850157516457', 'Lotus Dorkbua Stick Biscuits'),
        ('4901313938669', 'Kameda no Kakinotane Rice Snack'),
        ('8850043330273', 'Khao Shong Wasabi Coated Green Peas'),
        ('8852023664248', 'Koh-Kae Coconut Cream Coated Peanuts'),
        ('8851101992822', 'Pickled Mango')
    ]
    for bc, name in test_samples:
        fetch_by_barcode(bc, name)
