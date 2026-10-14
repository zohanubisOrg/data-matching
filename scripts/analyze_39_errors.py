import json
from pathlib import Path
from PIL import Image, ImageOps
import sys
sys.path.insert(0, 'src')
sys.path.insert(0, 'scripts')
from barcode_first_pipeline import load_ground_truth, truth_lookup
from product_mapper.vision.barcode_side_splitter import scan_file

error_dir = Path('output/catalog_pairs/image-error-resolve-again')
manifests = {}
for m_path in Path('output/catalog_pairs').glob('manifest*.json'):
    try:
        data = json.loads(m_path.read_text(encoding='utf-8'))
        manifests.update(data.get('products', {}))
    except Exception:
        pass

results = []
for ef in sorted(error_dir.glob('*-back.jpg')):
    bc = ef.name.replace('-back.jpg', '')
    info = manifests.get(bc, {})
    src = info.get('source', '')
    mode = info.get('mode', '')
    name = info.get('name_en', '')
    src_name = Path(src).name if src else 'NO_SRC'
    results.append({'barcode': bc, 'source': src, 'src_name': src_name, 'mode': mode, 'name': name})

print(f"Total: {len(results)}")
by_mode = {}
for r in results:
    m = r['mode'] or 'unknown'
    by_mode[m] = by_mode.get(m, 0) + 1
print("By mode:", by_mode)

for r in results:
    print(f"{r['barcode']} | mode={r['mode']:<12} | {r['src_name']:<15} | {r['name'][:35]}")
