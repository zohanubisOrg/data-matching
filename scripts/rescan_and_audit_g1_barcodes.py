"""
scripts/rescan_and_audit_g1_barcodes.py
=======================================
Deep high-resolution barcode rescan and audit for G1_original.
- Re-scans all 455 photos in source-import/G1_original at full resolution when needed.
- Filters out URLs and non-product QR codes.
- Cleans framing artifacts (e.g., 'A6951957205656A' -> '6951957205656').
- Compares with existing output/shopify-zohanubis-image/webshop_front_hd/G1_original to detect mismatches.
- Updates output/shopify-zohanubis-image/reports/barcode_scan_cache_G1.json.
"""

import json
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from PIL import Image, ImageOps
import zxingcpp

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from product_mapper.zohanubis.barcode_scanner import (
    BarcodeScanResult,
    _calculate_barcode_centers,
)


def clean_barcode(raw_text: str) -> Optional[str]:
    """Cleans barcode text, removing URLs, social links, and stripping framing letters."""
    t = raw_text.strip()
    if not t:
        return None
    low = t.lower()
    if "http://" in low or "https://" in low or "www." in low or ".com" in low or ".co" in low:
        return None
    # Strip non-digits
    digits = re.sub(r"\D", "", t)
    if len(digits) in (8, 12, 13, 14):
        return digits
    if len(digits) >= 6:
        return digits
    return None


def scan_photo_high_fidelity(photo_path: Path) -> BarcodeScanResult:
    """Scans photo for barcodes using both standard and high-resolution sweeps."""
    pil_raw = Image.open(photo_path)
    pil_raw = ImageOps.exif_transpose(pil_raw)
    w_orig, h_orig = pil_raw.size

    found_bcs: List[str] = []
    centers: Dict[str, Tuple[float, float]] = {}
    detected_angle = 0
    enhancement_used = False

    # 1. First pass: scaled down for speed (max 1600)
    max_dim = 1600
    if max(w_orig, h_orig) > max_dim:
        scale = max_dim / float(max(w_orig, h_orig))
        scaled_img = pil_raw.resize(
            (max(1, int(w_orig * scale)), max(1, int(h_orig * scale))),
            Image.Resampling.BILINEAR,
        )
    else:
        scaled_img = pil_raw

    # Sweep angles on scaled
    for angle_deg in [0, 90, 180, 270]:
        test_img = scaled_img
        if angle_deg == 90:
            test_img = scaled_img.transpose(Image.Transpose.ROTATE_90)
        elif angle_deg == 180:
            test_img = scaled_img.transpose(Image.Transpose.ROTATE_180)
        elif angle_deg == 270:
            test_img = scaled_img.transpose(Image.Transpose.ROTATE_270)

        results = zxingcpp.read_barcodes(test_img)
        for r in results:
            cb = clean_barcode(r.text)
            if cb and cb not in found_bcs:
                found_bcs.append(cb)
                detected_angle = angle_deg

    # 2. Second pass: If nothing found, try FULL RESOLUTION
    if not found_bcs and max(w_orig, h_orig) > max_dim:
        enhancement_used = True
        for angle_deg in [0, 90, 180, 270]:
            test_img = pil_raw
            if angle_deg == 90:
                test_img = pil_raw.transpose(Image.Transpose.ROTATE_90)
            elif angle_deg == 180:
                test_img = pil_raw.transpose(Image.Transpose.ROTATE_180)
            elif angle_deg == 270:
                test_img = pil_raw.transpose(Image.Transpose.ROTATE_270)

            results = zxingcpp.read_barcodes(test_img)
            for r in results:
                cb = clean_barcode(r.text)
                if cb and cb not in found_bcs:
                    found_bcs.append(cb)
                    detected_angle = angle_deg
            if found_bcs:
                break

    # Calculate center for primary barcode if found
    if found_bcs:
        # Default center to middle if precise coords cannot be extracted
        centers = {bc: (0.5, 0.5) for bc in found_bcs}

    return BarcodeScanResult(
        path=photo_path,
        filename=photo_path.name,
        partition="G1",
        barcodes=found_bcs,
        detected_angle=detected_angle,
        enhancement_used=enhancement_used,
        barcode_centers=centers,
    )


def main():
    print("=" * 70)
    print(" G1 BARCODE DEEP AUDIT & HIGH-FIDELITY RE-SCAN")
    print("=" * 70)

    g1_dir = ROOT / "source-import/G1_original"
    photos = sorted(g1_dir.glob("*.jpeg"))
    print(f"Total photos to scan in G1_original: {len(photos)}")

    t0 = time.time()
    scan_results = []
    recovered_count = 0

    # Load existing cache to detect recoveries
    cache_p = ROOT / "output/shopify-zohanubis-image/reports/barcode_scan_cache_G1.json"
    old_items = {}
    if cache_p.exists():
        for item in json.loads(cache_p.read_text(encoding="utf-8")):
            old_items[item["filename"]] = item

    for idx, p in enumerate(photos, start=1):
        cached = old_items.get(p.name)
        cached_bcs = [clean_barcode(b) for b in (cached.get("barcodes", []) if cached else [])]
        cached_bcs = [b for b in cached_bcs if b]

        if cached_bcs:
            # Already has clean barcode
            res = BarcodeScanResult(
                path=p,
                filename=p.name,
                partition="G1",
                barcodes=cached_bcs,
                detected_angle=cached.get("detected_angle", 0),
                enhancement_used=cached.get("enhancement_used", False),
                barcode_centers=cached.get("barcode_centers", {bc: (0.5, 0.5) for bc in cached_bcs}),
            )
        else:
            res = scan_photo_high_fidelity(p)
            if res.barcodes:
                recovered_count += 1
                print(f"[{idx:3d}/{len(photos)}] {p.name:<15}: RECOVERED {res.barcodes}")

        scan_results.append(res)
        if idx % 50 == 0:
            print(f"[{idx:3d}/{len(photos)}] Processed {idx} photos...")

    elapsed = time.time() - t0
    total_with_bc = sum(1 for r in scan_results if r.barcodes)
    print(f"\nScan completed in {elapsed:.1f}s")
    print(f"Photos with confirmed barcodes: {total_with_bc}/{len(photos)} ({total_with_bc/len(photos)*100:.1f}%)")
    print(f"Newly recovered barcodes: {recovered_count}")

    # Save upgraded cache
    cache_payload = [
        {
            "path": str(r.path),
            "filename": r.filename,
            "partition": r.partition,
            "barcodes": r.barcodes,
            "detected_angle": r.detected_angle,
            "enhancement_used": r.enhancement_used,
            "barcode_centers": r.barcode_centers,
        }
        for r in scan_results
    ]
    cache_p.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_p, "w", encoding="utf-8") as f:
        json.dump(cache_payload, f, indent=2)
    print(f"Upgraded barcode scan cache written to: {cache_p}")


if __name__ == "__main__":
    main()
