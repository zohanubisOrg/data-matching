import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from pathlib import Path
import json
import time
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import openpyxl
from PIL import Image, ImageOps
import pillow_heif
import numpy as np

# Register HEIF opener
pillow_heif.register_heif_opener()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.cv_front_detector import detect_front_box_cv

OUTPUT_DIR = Path("output/shopify_import_final/HD_Studio_Front_Images")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Also maintain canonical upload dirs
CANONICAL_DIRS = [
    Path("output/shopify_import_final/Shopify_Upload_Images_Online_Active"),
    Path("output/shopify_import_final/product_images_barcode_only")
]
for d in CANONICAL_DIRS:
    d.mkdir(parents=True, exist_ok=True)

def open_image_exif_normalized(img_path: Path) -> Image.Image:
    im = Image.open(img_path)
    im = ImageOps.exif_transpose(im)
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGB")
    return im

def crop_and_place_on_studio_canvas(
    orig_im: Image.Image,
    box: list[int],
    safe_margin_ratio: float = 0.07,
    canvas_w: int = 1600,
    canvas_h: int = 1600
) -> Image.Image:
    w, h = orig_im.size
    ymin, xmin, ymax, xmax = box

    # Symmetrical safe margin expansion
    box_w = xmax - xmin
    box_h = ymax - ymin
    pad_x = int(box_w * safe_margin_ratio)
    pad_y = int(box_h * safe_margin_ratio)

    exp_xmin = max(0, xmin - pad_x)
    exp_ymin = max(0, ymin - pad_y)
    exp_xmax = min(1000, xmax + pad_x)
    exp_ymax = min(1000, ymax + pad_y)

    left = int(exp_xmin * w / 1000.0)
    top = int(exp_ymin * h / 1000.0)
    right = int(exp_xmax * w / 1000.0)
    bottom = int(exp_ymax * h / 1000.0)

    if right <= left or bottom <= top:
        cropped = orig_im.copy()
    else:
        cropped = orig_im.crop((left, top, right, bottom))

    # Resize to fit within canvas with 60px outer breathing room
    max_inner_w = canvas_w - 120
    max_inner_h = canvas_h - 120
    cw, ch = cropped.size

    scale = min(max_inner_w / cw, max_inner_h / ch)
    new_w = max(10, int(cw * scale))
    new_h = max(10, int(ch * scale))

    resample_filter = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
    cropped_resized = cropped.resize((new_w, new_h), resample_filter)

    # Pure white studio canvas
    canvas = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    paste_x = (canvas_w - new_w) // 2
    paste_y = (canvas_h - new_h) // 2

    if cropped_resized.mode == "RGBA":
        canvas.paste(cropped_resized, (paste_x, paste_y), mask=cropped_resized.split()[3])
    else:
        canvas.paste(cropped_resized, (paste_x, paste_y))

    return canvas

def qc_check_image(img_path: Path) -> tuple[bool, str]:
    if not img_path.exists():
        return False, "File not found"
    size_bytes = img_path.stat().st_size
    if size_bytes < 15000:
        return False, f"File too small ({size_bytes} bytes)"

    try:
        with Image.open(img_path) as im:
            w, h = im.size
            if w < 1200 or h < 1200:
                return False, f"Resolution too low ({w}x{h})"
            # Check not flat white
            arr = np.array(im)
            std = float(np.std(arr))
            if std < 5.0:
                return False, f"Image is blank/monochrome (std={std:.1f})"
            return True, "Pass"
    except Exception as e:
        return False, f"Corrupted image: {e}"

def process_single_item(item: dict) -> dict:
    stt = item["stt"]
    barcode = item["barcode"]
    sku = item["sku"]
    raw_path = Path(item["raw_path"])
    
    out_filename = f"{barcode}.jpg" if barcode else f"SKU_{sku}.jpg"
    out_filepath = OUTPUT_DIR / out_filename

    try:
        box, rot, label = detect_front_box_cv(raw_path)
        orig_im = open_image_exif_normalized(raw_path)
        studio_im = crop_and_place_on_studio_canvas(orig_im, box, safe_margin_ratio=0.07)
        studio_im.save(out_filepath, "JPEG", quality=94, optimize=True)

        # Also copy to canonical folders
        for cdir in CANONICAL_DIRS:
            cpath = cdir / out_filename
            studio_im.save(cpath, "JPEG", quality=94, optimize=True)

        qc_ok, qc_msg = qc_check_image(out_filepath)
        return {
            "stt": stt,
            "barcode": barcode,
            "sku": sku,
            "success": True,
            "qc_ok": qc_ok,
            "qc_msg": qc_msg,
            "out_file": str(out_filepath),
            "label": label
        }
    except Exception as e:
        return {
            "stt": stt,
            "barcode": barcode,
            "sku": sku,
            "success": False,
            "qc_ok": False,
            "qc_msg": str(e),
            "out_file": "",
            "label": "error"
        }

def build_raw_file_index() -> dict[str, str]:
    raw_index = {}
    for root, _, files in os.walk("source-import"):
        for f in files:
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".heic")):
                raw_index[f.lower()] = os.path.join(root, f)
    return raw_index

def load_master_items(limit: int = 0) -> list[dict]:
    clean_master = "output/reconciliation/Master_1659_Reconciled_Clean.xlsx"
    raw_index = build_raw_file_index()

    wb = openpyxl.load_workbook(clean_master, data_only=True)
    sheet = wb.active
    rows = list(sheet.iter_rows(values_only=True))[3:]

    items = []
    for r in rows:
        stt = r[0]
        bc = str(r[2] or "").strip()
        sku = str(r[88] or "").strip()
        src_front = str(r[67] or "").strip()
        src_photos = str(r[66] or "").strip()

        fname = os.path.basename(src_front).lower()
        fpath = raw_index.get(fname)
        if not fpath:
            for part in src_photos.replace(",", " ").split():
                p_clean = os.path.basename(part).lower()
                if p_clean in raw_index:
                    fpath = raw_index[p_clean]
                    break

        if fpath:
            items.append({
                "stt": stt,
                "barcode": bc,
                "sku": sku,
                "raw_path": fpath
            })
            if 0 < limit <= len(items):
                break
    return items

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Limit number of items to process")
    parser.add_argument("--workers", type=int, default=6, help="Worker processes")
    args = parser.parse_args()

    items = load_master_items(args.limit)
    print(f"[*] Starting HD Studio Crop Pipeline for {len(items)} items using {args.workers} workers...")
    t0 = time.time()

    results = []
    passed_qc = 0

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_single_item, item): item for item in items}
        for i, future in enumerate(as_completed(futures), 1):
            res = future.result()
            results.append(res)
            if res.get("qc_ok"):
                passed_qc += 1
            if i % 100 == 0 or i == len(items):
                elapsed = time.time() - t0
                print(f"    Progress: {i}/{len(items)} items processed ({passed_qc} passed QC) in {elapsed:.1f}s")

    elapsed = time.time() - t0
    qc_rate = (passed_qc / len(items) * 100) if items else 0.0
    print("\n=======================================================")
    print(f"🎉 HD Studio Crop Pipeline Finished in {elapsed:.1f}s")
    print(f"    Total Processed: {len(results)}")
    print(f"    Passed QC:        {passed_qc}/{len(results)} ({qc_rate:.1f}%)")
    print(f"    Output Folder:    {OUTPUT_DIR}")
    print("=======================================================")

    # Write summary log
    summary_path = "output/reconciliation/HD_Studio_Crop_QC_Summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "total": len(results),
            "passed_qc": passed_qc,
            "qc_rate": qc_rate,
            "elapsed_seconds": elapsed,
            "results": results[:50] # sample
        }, f, indent=2)

if __name__ == "__main__":
    main()
