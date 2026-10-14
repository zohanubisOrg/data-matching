import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import requests
import json

headers = {'User-Agent': 'RabutaCatalogSuite/2.0 (contact@rabuta.dk)'}
barcodes = ['8850157516457', '8850043330273', '8852023664248', '8851101993812']

for bc in barcodes:
    url = f'https://world.openfoodfacts.org/api/v2/product/{bc}?fields=code,product_name,selected_images,images'
    r = requests.get(url, headers=headers, timeout=10)
    print(f"\n=== Barcode: {bc} (Status {r.status_code}) ===")
    if r.status_code == 200:
        data = r.json()
        p = data.get('product', {})
        print('  Product name:', p.get('product_name'))
        sel = p.get('selected_images', {})
        print('  Selected images categories:', list(sel.keys()))
        for cat, v in sel.items():
            print(f"    Category [{cat}]:")
            for lang, sizes in v.items():
                if isinstance(sizes, dict):
                    full_url = sizes.get('full')
                    display_url = sizes.get('display')
                    print(f"      Lang {lang} -> full: {full_url}")
                    
        # Check raw images keys
        raw_imgs = p.get('images', {})
        print(f"  Raw images count: {len(raw_imgs)}")
        numbered = [k for k in raw_imgs.keys() if k.isdigit()]
        print(f"  Original photo upload IDs: {numbered}")
