import json
from pathlib import Path
from PIL import Image, ImageOps
import sys
import cv2
import numpy as np

sys.path.insert(0, 'src')
sys.path.insert(0, 'scripts')
from barcode_first_pipeline import load_ground_truth, truth_lookup
from product_mapper.vision.barcode_side_splitter import scan_file, read_retail_barcodes

error_dir = Path('output/catalog_pairs/image-error-resolve-again')
manifests = {}
for m_path in Path('output/catalog_pairs').glob('manifest*.json'):
    try:
        data = json.loads(m_path.read_text(encoding='utf-8'))
        manifests.update(data.get('products', {}))
    except Exception:
        pass

error_files = sorted(list(error_dir.glob('*-back.jpg')))

report = []
for ef in error_files:
    bc = ef.name.replace('-back.jpg', '')
    info = manifests.get(bc, {})
    src = info.get('source', '')
    if not src or not Path(src).exists():
        # search across G1, G2, G3, G4
        for folder in ['G1_original', 'G2_original', 'G3_Original', 'G4-original']:
            for ext in ['.jpeg', '.jpg', '.png', '.HEIC']:
                cand = Path(f'source-import/{folder}')
                # we don't know filename, keep as is
    
    if src and Path(src).exists():
        src_path = Path(src)
        try:
            img = ImageOps.exif_transpose(Image.open(src_path))
            w, h = img.size
            # scan barcode
            scan = scan_file(src_path, {bc})
            bc_center = scan.get('center')
            report.append({
                'barcode': bc,
                'source': str(src_path),
                'name': info.get('name_en', ''),
                'width': w,
                'height': h,
                'aspect': round(w / h, 2),
                'old_mode': info.get('mode', ''),
                'bc_found': scan.get('barcode'),
                'bc_center': bc_center,
            })
        except Exception as e:
            report.append({'barcode': bc, 'source': str(src_path), 'error': str(e)})
    else:
        report.append({'barcode': bc, 'source': 'NOT_FOUND'})

Path('output/catalog_pairs/review/errors_39_analysis.json').write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8'
)
print(f"Analyzed {len(report)} files. Saved to errors_39_analysis.json")
for r in report[:10]:
    print(r['barcode'], f"w={r.get('width')} h={r.get('height')}", f"mode={r.get('old_mode')}", f"bc={r.get('bc_found')}", f"center={r.get('bc_center')}")
