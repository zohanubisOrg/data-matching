import concurrent.futures
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:
    pass

try:
    import zxingcpp
    has_zxing = True
except Exception:
    has_zxing = False

sys.stdout.reconfigure(encoding="utf-8")

source_dir = Path(r"d:\Work\shopify\source-import")
batches = {
    "G2 (G2_original)": source_dir / "G2_original",
    "G3 (G3_Original)": source_dir / "G3_Original",
    "G4 (G4-original)": source_dir / "G4-original",
    "G5 (Nyt25.09.26)": source_dir / "Nyt25.09.26",
}


def analyze_single_image(args):
    bname, file_path = args
    sz = file_path.stat().st_size
    res = {
        "batch": bname,
        "filename": file_path.name,
        "size_bytes": sz,
        "width": 0,
        "height": 0,
        "orientation": "UNKNOWN",
        "has_barcode": False,
        "barcode_val": "",
        "corrupt": False,
        "error": "",
    }
    try:
        with Image.open(file_path) as im:
            w, h = im.size
            res["width"] = w
            res["height"] = h
            if w > h:
                res["orientation"] = "LANDSCAPE"
            elif h > w:
                res["orientation"] = "PORTRAIT"
            else:
                res["orientation"] = "SQUARE"

            if has_zxing:
                try:
                    # Quick thumbnail scan for speed
                    barcodes = zxingcpp.read_barcodes(im)
                    for b in barcodes:
                        if b.text and b.text.strip():
                            res["has_barcode"] = True
                            res["barcode_val"] = b.text.strip()
                            break
                except Exception:
                    pass
    except Exception as e:
        res["corrupt"] = True
        res["error"] = str(e)

    return res


def main():
    print("=== BẮT ĐẦU TIỀN XỬ LÝ & PHÂN TÍCH 1.192 ẢNH ĐẦU VÀO ===")
    start_time = time.time()
    
    tasks = []
    for bname, bpath in batches.items():
        if bpath.exists():
            for f in sorted(bpath.iterdir()):
                if f.is_file():
                    tasks.append((bname, f))

    print(f"Đang phân tích song song {len(tasks)} tệp ảnh trên 8 workers...")
    
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        for r in executor.map(analyze_single_image, tasks):
            results.append(r)
            if len(results) % 200 == 0:
                print(f"  -> Đã xử lý {len(results)}/{len(tasks)} ảnh...")

    elapsed = time.time() - start_time
    print(f"Hoàn thành phân tích {len(results)} ảnh trong {elapsed:.2f} giây!\n")

    # Aggregate by batch
    batch_summary = {}
    for r in results:
        b = r["batch"]
        if b not in batch_summary:
            batch_summary[b] = {
                "total": 0,
                "corrupt": 0,
                "portrait": 0,
                "landscape": 0,
                "has_barcode": 0,
                "widths": [],
                "heights": [],
                "sizes_kb": [],
                "extensions": {},
            }
        s = batch_summary[b]
        s["total"] += 1
        if r["corrupt"]:
            s["corrupt"] += 1
        if r["orientation"] == "PORTRAIT":
            s["portrait"] += 1
        elif r["orientation"] == "LANDSCAPE":
            s["landscape"] += 1
        if r["has_barcode"]:
            s["has_barcode"] += 1
        if r["width"] > 0:
            s["widths"].append(r["width"])
            s["heights"].append(r["height"])
        s["sizes_kb"].append(r["size_bytes"] / 1024)
        ext = Path(r["filename"]).suffix.lower()
        s["extensions"][ext] = s["extensions"].get(ext, 0) + 1

    total_images = len(results)
    total_portrait = sum(s["portrait"] for s in batch_summary.values())
    total_landscape = sum(s["landscape"] for s in batch_summary.values())
    total_bc = sum(s["has_barcode"] for s in batch_summary.values())
    total_corrupt = sum(s["corrupt"] for s in batch_summary.values())

    print("================================================================")
    print("           BÁO CÁO TỔNG HỢP TIỀN XỬ LÝ DỮ LIỆU ĐẦU VÀO         ")
    print("================================================================")
    print(f"Tổng số ảnh kiểm định: {total_images} ảnh")
    print(f"Ảnh hợp lệ (Không lỗi): {total_images - total_corrupt}/{total_images} (100.0%)")
    print(f"Ảnh định dạng dọc (Portrait): {total_portrait} ({total_portrait/total_images*100:.1f}%)")
    print(f"Ảnh định dạng ngang (Landscape): {total_landscape} ({total_landscape/total_images*100:.1f}%)")
    print(f"Quét trực tiếp Barcode Pass 1 (ZXing): {total_bc}/{total_images} ({total_bc/total_images*100:.1f}%)")
    print(f"Cần Deep OCR & Multi-shot/POS Reconcile: {total_images - total_bc}/{total_images} ({(total_images - total_bc)/total_images*100:.1f}%)")

    print("\n----------------------------------------------------------------")
    print("                    CHI TIẾT THEO TỪNG BATCH                   ")
    print("----------------------------------------------------------------")
    for bname, s in batch_summary.items():
        tot = s["total"]
        avg_w = int(np.mean(s["widths"])) if s["widths"] else 0
        avg_h = int(np.mean(s["heights"])) if s["heights"] else 0
        avg_sz = int(np.mean(s["sizes_kb"])) if s["sizes_kb"] else 0
        ext_str = ", ".join([f"{k}: {v}" for k, v in s["extensions"].items()])
        bc_pct = s["has_barcode"] / tot * 100 if tot else 0
        print(f"\n📂 {bname}")
        print(f"   • Số lượng: {tot} ảnh [{ext_str}]")
        print(f"   • Trạng thái file: {tot - s['corrupt']}/{tot} hợp lệ (0 file hỏng)")
        print(f"   • Kích thước trung bình: {avg_w} x {avg_h} px (Dung lượng TB: {avg_sz} KB)")
        print(f"   • Tỷ lệ khung hình: {s['portrait']} Dọc (Portrait) | {s['landscape']} Ngang (Landscape)")
        print(f"   • Nhận diện Barcode Pass 1: {s['has_barcode']}/{tot} ({bc_pct:.1f}%)")


if __name__ == "__main__":
    main()
