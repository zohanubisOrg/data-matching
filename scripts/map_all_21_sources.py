import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.extend([str(ROOT / "scripts"), str(ROOT / "src")])

from barcode_first_pipeline import load_ground_truth
from retry_g2_missing_barcodes import hard_read
from product_mapper.vision.barcode_side_splitter import read_retail_barcodes
from product_mapper.ingestion.image_loader import open_image_safely

err_dir = ROOT / "output/catalog_pairs/image-error-resolve-again"
err_files = sorted([p.name for p in err_dir.glob("*.jpg")])
barcodes = [f.replace("-back.jpg", "") for f in err_files]

prods = load_ground_truth(ROOT / "source-import/new_source_from_customer/12-10-new-requirment/Rabuta.12.10.2026_original.xlsx")
prod_map = {p["barcode"]: p for p in prods}

# Look up in all manifests:
manifest_paths = list((ROOT / "output/catalog_pairs").glob("manifest*.json"))
g1_products = json.loads((ROOT / "output/g1_delivery/G1_products.json").read_text(encoding="utf-8"))
g1_map = {str(item.get("barcode")): item for item in g1_products}

sources = {}

for bc in barcodes:
    src = None
    # Check manifests
    for mp in manifest_paths:
        try:
            d = json.loads(mp.read_text(encoding="utf-8"))
            p_dict = d.get("products") or d.get("new_products_exported") or {}
            if bc in p_dict:
                src = p_dict[bc].get("source") or p_dict[bc].get("back_source")
                if src:
                    sources[bc] = (src, mp.name)
                    break
        except Exception:
            pass
    if not src and bc in g1_map:
        orig = g1_map[bc].get("original_image")
        if orig:
            sources[bc] = (str(ROOT / "source-import/G1_original" / orig), "G1_products.json")

print(f"Total error barcodes: {len(barcodes)}")
for bc in barcodes:
    info = prod_map.get(bc, {})
    src_info = sources.get(bc)
    print(f"{bc} | {info.get('brand')} - {info.get('name_en')}")
    print(f"   Source: {src_info}")
