import json, sys, os, re
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

with open('output/g1_delivery/g1_deep_scan_65_cache.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Collect all overrides from previous scripts
all_overrides = {}
for py_file in Path('scripts').glob('*.py'):
    text = py_file.read_text(encoding='utf-8', errors='ignore')
    for m in re.finditer(r'\"(IMG_\d+\.jpe?g)\":\s*\{([^}]+)\}', text):
        img_k = m.group(1)
        body = m.group(2)
        bc_m = re.search(r'\"barcode\":\s*\"([^\"]+)\"', body)
        name_m = re.search(r'\"product_name\":\s*\"([^\"]+)\"', body)
        brand_m = re.search(r'\"brand\":\s*\"([^\"]+)\"', body)
        if bc_m:
            if img_k not in all_overrides:
                all_overrides[img_k] = {}
            all_overrides[img_k]['barcode'] = bc_m.group(1)
            if name_m:
                all_overrides[img_k]['product_name'] = name_m.group(1)
            if brand_m:
                all_overrides[img_k]['brand'] = brand_m.group(1)

print(f'Total known ground truth overrides collected: {len(all_overrides)}')

# Load POS Lookup
POS_FILE = Path("Products_imported_to_Shopbox_19_08_26_with_SKU.xlsx")
pos_df = pd.read_excel(POS_FILE)
pos_dict = {}
for _, r in pos_df.iterrows():
    bc = str(r['Bar Code']).strip().replace('.0', '')
    if bc and bc != 'nan':
        pos_dict[bc] = {
            'sku': str(r.get('Sku Code', '')).strip(),
            'name': str(r.get('Product Name ', '')).strip(),
            'official': str(r.get('Oficial Name ', '')).strip(),
        }

print(f'Total POS items: {len(pos_dict)}')

# Analyze why the 50 items were unresolved
categories_of_failure = {
    "GLASS_JAR_CURVED": [],
    "UPC_LEADING_ZERO": [],
    "NATIVE_NON_LATIN_TEXT": [],
    "DIM_OR_GLARE_LABEL": [],
    "NON_FOOD_EXEMPT": [],
}

for fname, item in data.items():
    bc = str(item.get('barcode', ''))
    name = str(item.get('full_name_en', ''))
    
    if bc.startswith('NO_BARCODE') or not bc or bc == 'None':
        # Check if known in overrides
        known = all_overrides.get(fname, {})
        known_bc = known.get('barcode', '')
        known_name = known.get('product_name', '')
        
        if known_bc and known_bc.startswith('0'):
            categories_of_failure["UPC_LEADING_ZERO"].append((fname, known_bc, known_name))
        elif 'Jar' in name or 'Pickled' in name or 'Sauce' in name or 'Oil' in name or 'Paste' in name:
            categories_of_failure["GLASS_JAR_CURVED"].append((fname, known_bc or bc, known_name or name))
        elif any(ord(c) > 1000 for c in name + str(item.get('brand', ''))):
            categories_of_failure["NATIVE_NON_LATIN_TEXT"].append((fname, known_bc or bc, known_name or name))
        else:
            categories_of_failure["DIM_OR_GLARE_LABEL"].append((fname, known_bc or bc, known_name or name))

print('\n=== PHÂN LOẠI CÁC NGUYÊN NHÂN CHÍNH ===')
for cat, items in categories_of_failure.items():
    print(f'\n* Nhóm [{cat}]: {len(items)} sản phẩm')
    for f, b, n in items[:5]:
        print(f'    - {f} -> Barcode: {b} | Tên: {n[:35]}')
