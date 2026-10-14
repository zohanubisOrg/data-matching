import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.extend([str(ROOT / "scripts"), str(ROOT / "src")])

from product_mapper.vision.barcode_side_splitter import scan_file, read_retail_barcodes
from product_mapper.ingestion.image_loader import open_image_safely

error_dir = ROOT / "output/catalog_pairs/image-error-resolve-again"
error_files = sorted([p.name for p in error_dir.glob("*.jpg")])

manifest_paths = list((ROOT / "output/catalog_pairs").glob("manifest*.json"))

print(f"Total error files: {len(error_files)}")

for ef in error_files:
    bc = ef.replace("-back.jpg", "")
    info = None
    manifest_name = None
    for mp in manifest_paths:
        try:
            data = json.loads(mp.read_text(encoding="utf-8"))
            prods = data.get("products") or data.get("new_products_exported") or {}
            if bc in prods:
                info = prods[bc]
                manifest_name = mp.name
                break
        except Exception:
            pass
    
    print("=" * 60)
    print(f"BARCODE: {bc} ({ef})")
    print(f"Manifest: {manifest_name}")
    if info:
        source = info.get("source") or info.get("back_source") or ""
        mode = info.get("mode")
        print(f"Source file: {source}")
        print(f"Split mode: {mode}")
        if source and Path(source).exists():
            im = open_image_safely(source)
            hits = read_retail_barcodes(im)
            print(f"Source dimensions: {im.size}")
            for h in hits:
                print(f"  Detected barcode in source: {h.text} at center=({h.center_x:.1f}, {h.center_y:.1f}), quad={h.quad}")
            im.close()
    
    err_back = error_dir / ef
    if err_back.exists():
        im_err = open_image_safely(err_back)
        err_hits = read_retail_barcodes(im_err)
        print(f"Error back dimensions: {im_err.size}")
        print(f"Barcodes in error back image: {[h.text for h in err_hits]}")
        im_err.close()

    # Also check current front-v2 and back-v2
    cur_front = ROOT / f"output/catalog_pairs/tagged/front-v2/{bc}-front.jpg"
    cur_back = ROOT / f"output/catalog_pairs/tagged/back-v2/{bc}-back.jpg"
    print(f"Current front-v2 exists: {cur_front.exists()}, back-v2 exists: {cur_back.exists()}")
