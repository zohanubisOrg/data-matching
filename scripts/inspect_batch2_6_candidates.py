import json
import hashlib
from pathlib import Path
from PIL import Image
import numpy as np

ROOT = Path("D:/Work/shopify")

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

manifest_path = ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/subagent_batch_388_760/candidate_manifest.jsonl"
items = [json.loads(l) for l in manifest_path.read_text(encoding="utf-8").split("\n") if l.strip()]

print(f"Total candidates in Batch 2 manifest: {len(items)}\n")

results = []

for item in items:
    row = item["excel_row"]
    barcode = item["barcode"]
    name = item["product_name_en"]
    out_p = Path(item["output_path"])
    mask_p = Path(item["mask_path"])
    src_p = Path(item["source_path"])
    overlay_p = Path(item["overlay_path"])

    print(f"==================== Row {row} | Barcode {barcode} | {name} ====================")
    
    # 1. SHA256 integrity check
    src_sha = sha256_file(src_p)
    mask_sha = sha256_file(mask_p)
    out_sha = sha256_file(out_p)
    overlay_sha = sha256_file(overlay_p)

    src_ok = (src_sha == item["source_sha256"])
    mask_ok = (mask_sha == item["mask_sha256"])
    out_ok = (out_sha == item["output_sha256"])
    overlay_ok = (overlay_sha == item["overlay_sha256"])

    print(f"SHA-256 checks:")
    print(f"  Source : {src_sha[:16]}... [Match: {src_ok}]")
    print(f"  Mask   : {mask_sha[:16]}... [Match: {mask_ok}]")
    print(f"  Output : {out_sha[:16]}... [Match: {out_ok}]")
    print(f"  Overlay: {overlay_sha[:16]}... [Match: {overlay_ok}]")

    # 2. Canvas & Border check
    with Image.open(out_p) as img:
        size = img.size
        arr = np.asarray(img.convert("RGB"))

    is_2400 = (size == (2400, 2400))
    top_clean = (arr[0] == 255).all()
    bot_clean = (arr[-1] == 255).all()
    left_clean = (arr[:, 0] == 255).all()
    right_clean = (arr[:, -1] == 255).all()
    border_pure_white = all([top_clean, bot_clean, left_clean, right_clean])

    # 3. Product Bounding box & Placement
    non_white = np.where(np.any(arr < 250, axis=2))
    ymin, ymax = int(non_white[0].min()), int(non_white[0].max())
    xmin, xmax = int(non_white[1].min()), int(non_white[1].max())
    w, h = xmax - xmin + 1, ymax - ymin + 1

    # 4. Upscale check
    scale = float(item.get("layout_upscale_factor", 1.0))
    no_upscale = (scale <= 1.0)

    # 5. Border fringe / Halo color check
    top_edge = arr[ymin:ymin+4, xmin:xmax+1]
    bot_edge = arr[ymax-3:ymax+1, xmin:xmax+1]
    left_edge = arr[ymin:ymax+1, xmin:xmin+4]
    right_edge = arr[ymin:ymax+1, xmax-3:xmax+1]

    print(f"Canvas Checks:")
    print(f"  Size: {size} (Is 2400x2400: {is_2400})")
    print(f"  Border pure white #FFFFFF: {border_pure_white}")
    print(f"  Product bbox: [{xmin}, {ymin}, {xmax}, {ymax}] dims: {w}x{h}")
    print(f"  Upscale factor: {scale:.4f} (<= 1.0: {no_upscale})")
    print(f"  Mean color top edge    : {top_edge.mean(axis=(0,1)).round(1)}")
    print(f"  Mean color bottom edge : {bot_edge.mean(axis=(0,1)).round(1)}")
    print(f"  Mean color left edge   : {left_edge.mean(axis=(0,1)).round(1)}")
    print(f"  Mean color right edge  : {right_edge.mean(axis=(0,1)).round(1)}")
    print(f"  Visual Evidence stated: {item.get('visual_evidence')[:120]}...")
    print()

    results.append({
        "row": row,
        "barcode": barcode,
        "name": name,
        "is_2400": is_2400,
        "border_pure_white": border_pure_white,
        "no_upscale": no_upscale,
        "scale": scale,
        "bbox": [xmin, ymin, xmax, ymax],
        "size_placed": [w, h],
        "hashes_ok": all([src_ok, mask_ok, out_ok, overlay_ok])
    })

print("Summary of automated checks:")
for r in results:
    print(f"Row {r['row']} ({r['barcode']}): Canvas 2400={r['is_2400']}, WhiteBorder={r['border_pure_white']}, NoUpscale={r['no_upscale']} (scale={r['scale']:.3f}), HashesOK={r['hashes_ok']}")
