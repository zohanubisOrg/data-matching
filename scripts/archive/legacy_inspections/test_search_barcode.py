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

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}

def test_barcode(bc):
    print(f"\n==========================================")
    print(f"Testing Barcode: {bc}")
    
    # 1. OpenFoodFacts
    off_url = f"https://world.openfoodfacts.org/api/v2/product/{bc}.json"
    try:
        r = requests.get(off_url, headers={'User-Agent': 'RabutaApp/1.0 (contact@rabuta.dk)'}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == 1:
                p = data.get("product", {})
                name = p.get("product_name") or p.get("product_name_en")
                img = p.get("image_front_url") or p.get("image_url")
                print(f"  [OpenFoodFacts] Name: {name} | Image: {img}")
    except Exception as e:
        print(f"  [OpenFoodFacts error]: {e}")

    # 2. Google Search (Web title + snippet)
    google_url = f"https://www.google.com/search?q={bc}&hl=en"
    try:
        r = requests.get(google_url, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(r.text, 'html.parser')
        titles = [h3.get_text() for h3 in soup.find_all('h3')][:3]
        print(f"  [Google Web Results Titles]:")
        for t in titles:
            print(f"    - {t}")
    except Exception as e:
        print(f"  [Google Web error]: {e}")

    # 3. Google Images Search
    google_img_url = f"https://www.google.com/search?q={bc}&tbm=isch&hl=en"
    try:
        r = requests.get(google_img_url, headers=HEADERS, timeout=8)
        # Google images script data contains original image urls
        img_urls = re.findall(r'\["(https://[^"]+?\.(?:jpg|jpeg|png|webp))",\d+,\d+\]', r.text)
        print(f"  [Google Images Full-Res URLs Found: {len(img_urls)}]")
        for u in img_urls[:3]:
            print(f"    - {u}")
    except Exception as e:
        print(f"  [Google Images error]: {e}")

if __name__ == "__main__":
    barcodes = ['8850157516457', '4901313938669', '8850043330273', '8851101992822']
    for bc in barcodes:
        test_barcode(bc)
