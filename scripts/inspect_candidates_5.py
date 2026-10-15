import json
import os
import sys
import hashlib
from pathlib import Path
import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path("D:/Work/shopify")

def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

files_to_inspect = [
    ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/candidates/user_qa_pending_850_886_894.jsonl",
    ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/candidates/user_qa_pending_926_970.jsonl",
]

for jpath in files_to_inspect:
    print(f"\n================ Inspecting {jpath.name} ================")
    with open(jpath, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            item = json.loads(line)
            row = item.get("excel_row")
            barcode = item.get("barcode")
            rec_id = item.get("record_id")
            out_p = Path(item.get("output_path"))
            mask_p = Path(item.get("mask_path"))
            src_p = Path(item.get("source_path"))
            
            print(f"\n--- Row {row} | Barcode {barcode} | SKU {rec_id} ---")
            print(f"Status in record: {item.get('status')}")
            print(f"Reason: {item.get('reason')}")
            
            # Check source
            if src_p.exists():
                src_hash = sha256_file(src_p)
                print(f"Source: {src_p.name} (SHA256: {src_hash[:16]}..., match: {src_hash == item.get('source_sha256')})")
            else:
                print(f"Source NOT FOUND: {src_p}")

            # Check mask
            if mask_p.exists():
                mask_hash = sha256_file(mask_p)
                with Image.open(mask_p) as mimg:
                    msize = mimg.size
                print(f"Mask: {mask_p.name} size {msize} (SHA256: {mask_hash[:16]}..., match: {mask_hash == item.get('mask_sha256')})")
            else:
                print(f"Mask NOT FOUND: {mask_p}")

            # Check output
            if out_p.exists():
                out_hash = sha256_file(out_p)
                with Image.open(out_p) as oimg:
                    osize = oimg.size
                    oarr = np.asarray(oimg.convert("RGB"))
                
                # Check borders
                top = oarr[0]
                bottom = oarr[-1]
                left = oarr[:, 0]
                right = oarr[:, -1]
                pure_white = all((edge == 255).all() for edge in (top, bottom, left, right))
                
                # Non-white bbox
                non_white = np.where(np.any(oarr < 250, axis=2))
                if len(non_white[0]) > 0:
                    ymin, ymax = non_white[0].min(), non_white[0].max()
                    xmin, xmax = non_white[1].min(), non_white[1].max()
                    prod_w = xmax - xmin + 1
                    prod_h = ymax - ymin + 1
                else:
                    ymin, ymax, xmin, xmax = 0, 0, 0, 0
                    prod_w, prod_h = 0, 0

                print(f"Output: {out_p.name} size {osize} (SHA256: {out_hash[:16]}..., match: {out_hash == item.get('output_sha256')})")
                print(f"  Canvas check 2400x2400: {osize == (2400, 2400)}")
                print(f"  Pure white outer borders: {pure_white}")
                print(f"  Product bbox in canvas: [{xmin}, {ymin}, {xmax}, {ymax}], dims: {prod_w}x{prod_h}")
                print(f"  Upscale factor: {item.get('layout', {}).get('upscale_factor')}")
                print(f"  Scale limited to native: {item.get('layout', {}).get('scale_limited_to_native')}")
            else:
                print(f"Output NOT FOUND: {out_p}")
