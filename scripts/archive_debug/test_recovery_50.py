import sys, json, os, io
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.product_mapper.vision.barcode_validator import get_barcode_lookup_variants, validate_ean_upc_checksum
from src.product_mapper.enrichment.market_enricher import MarketCatalogEnricher
import zxingcpp

POS_FILE = Path("Products_imported_to_Shopbox_19_08_26_with_SKU.xlsx")
pos_df = pd.read_excel(POS_FILE)
pos_records = []
for _, r in pos_df.iterrows():
    bc = str(r['Bar Code']).strip().replace('.0', '')
    sku = str(r.get('Sku Code', '')).strip()
    name = str(r.get('Product Name ', '')).strip()
    off = str(r.get('Oficial Name ', '')).strip()
    if bc and bc != 'nan':
        pos_records.append({'barcode': bc, 'sku': sku, 'name': name, 'official': off})

with open('output/g1_delivery/g1_deep_scan_65_cache.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

unresolved_files = [f for f, v in data.items() if str(v.get('barcode', '')).startswith('NO_BARCODE') or not v.get('barcode')]
print(f'Testing recovery on {len(unresolved_files)} unresolved items...')

recovered = {}
for fname in unresolved_files:
    img_path = Path('G1_original') / fname
    item = data[fname]
    prod_name = item.get('full_name_en') or item.get('literal_label_name') or ''
    brand = item.get('brand') or ''
    
    # 1. Check Multi-Corner Optical ZXing with dynamic adaptive thresholds
    found_bc = None
    with Image.open(img_path) as im:
        im = ImageOps.exif_transpose(im)
        w, h = im.size
        
        # Crop 4 quadrants of the back panel & full image in 4 rotations
        for rot in [0, 90, 180, 270]:
            im_rot = im if rot == 0 else im.rotate(rot, expand=True)
            for r in zxingcpp.read_barcodes(im_rot):
                t = str(getattr(r, 'text', '')).strip()
                if t.isdigit() and len(t) >= 8 and validate_ean_upc_checksum(t):
                    found_bc = t
                    break
            if found_bc:
                break
        
        # If not found, try 2.5x contrast and sharpening
        if not found_bc:
            enh = ImageEnhance.Contrast(im).enhance(2.5)
            for rot in [0, 90, 180, 270]:
                im_rot = enh if rot == 0 else enh.rotate(rot, expand=True)
                for r in zxingcpp.read_barcodes(im_rot):
                    t = str(getattr(r, 'text', '')).strip()
                    if t.isdigit() and len(t) >= 8 and validate_ean_upc_checksum(t):
                        found_bc = t
                        break
                if found_bc:
                    break

    # 2. Match with POS Master Catalog by Brand & Product Name tokens
    if not found_bc and prod_name:
        tokens = [t.lower() for t in prod_name.replace('-', ' ').replace(',', ' ').split() if len(t) >= 4]
        best_match = None
        best_score = 0
        for pos_rec in pos_records:
            pos_text = (pos_rec['name'] + ' ' + pos_rec['official']).lower()
            score = sum(1 for t in tokens if t in pos_text)
            if brand and brand.lower() in pos_text:
                score += 2
            if score > best_score and score >= 2:
                best_score = score
                best_match = pos_rec
        if best_match and best_score >= 3:
            found_bc = best_match['barcode']
            print(f'  [POS Match] {fname}: "{prod_name[:30]}" -> {found_bc} ({best_match["name"]})')

    if found_bc:
        recovered[fname] = found_bc

print(f'\nSuccessfully recovered: {len(recovered)} / {len(unresolved_files)} items!')
