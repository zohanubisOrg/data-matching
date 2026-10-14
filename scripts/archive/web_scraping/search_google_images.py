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
import time
import requests
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO

SESSION = requests.Session()
SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,da;q=0.8',
})

def search_openfoodfacts(barcode):
    url = f"https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
    try:
        r = SESSION.get(url, headers={'User-Agent': 'RabutaApp/1.0 (contact@rabuta.dk)'}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == 1:
                p = data.get("product", {})
                title = p.get("product_name_en") or p.get("product_name")
                img = p.get("image_front_url") or p.get("image_url")
                if img:
                    return {"source": "OpenFoodFacts", "title": title, "image_url": img}
    except Exception:
        pass
    return None

def search_google_shopping_images(barcode, brand_hint=""):
    query = f"{barcode} {brand_hint}".strip()
    url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&tbm=isch&hl=en"
    try:
        r = SESSION.get(url, timeout=7)
        if r.status_code == 200:
            # Extract image URLs
            urls = re.findall(r'\["(https://[^"]+?\.(?:jpg|jpeg|png|webp))",\d+,\d+\]', r.text)
            clean_urls = [u for u in urls if 'gstatic' not in u and 'google' not in u and 'wikimedia' not in u]
            if clean_urls:
                return {"source": "Google_Images", "image_url": clean_urls[0]}
    except Exception:
        pass
    return None

import urllib.parse

def test_items():
    items = [
        ('8850157516457', 'Lotus Dorkbua'),
        ('4901313938669', 'Kameda'),
        ('8850043330273', 'Khao Shong'),
        ('8852023664248', 'Koh-Kae'),
        ('8851101992822', 'Pickled Mango')
    ]
    for bc, brand in items:
        res = search_openfoodfacts(bc)
        if not res:
            res = search_google_shopping_images(bc, brand)
        print(f"Barcode {bc} ({brand}): {res}")

if __name__ == "__main__":
    test_items()
