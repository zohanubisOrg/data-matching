import sys, os, json
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import zxingcpp
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

ITEMS = [
    "IMG_0230.jpeg", "IMG_0231.jpeg", "IMG_0242.jpeg", "IMG_0260.jpeg",
    "IMG_0273.jpeg", "IMG_0275.jpeg", "IMG_0278.jpeg", "IMG_0279.jpeg",
    "IMG_0289.jpeg", "IMG_0299.jpeg", "IMG_0304.jpeg", "IMG_0308.jpeg",
    "IMG_0319.jpeg", "IMG_0320.jpeg", "IMG_0325.jpeg", "IMG_0330.jpeg",
    "IMG_0334.jpeg", "IMG_0335.jpeg", "IMG_0336.jpeg", "IMG_0353.jpeg",
    "IMG_0368.jpeg"
]

def validate_ean_upc_checksum(digits: str) -> bool:
    if not digits.isdigit() or len(digits) not in (8, 12, 13, 14):
        return False
    check_digit = int(digits[-1])
    payload = digits[:-1]
    if len(digits) == 8:
        weights = [3, 1] * 3 + [3]
    elif len(digits) == 12:
        weights = [3, 1] * 5 + [3]
    elif len(digits) == 13:
        weights = [1, 3] * 6
    elif len(digits) == 14:
        weights = [3, 1] * 6 + [3]
    else:
        return False
    calc_sum = sum(int(d) * w for d, w in zip(payload, weights))
    calc_check = (10 - (calc_sum % 10)) % 10
    return calc_check == check_digit

def scan_barcodes_multi_angle(im):
    found = set()
    for rot in [0, 90, 180, 270]:
        im_rot = im if rot == 0 else im.rotate(rot, expand=True)
        for r in zxingcpp.read_barcodes(im_rot):
            t = str(r.text).strip()
            if t.isdigit() and validate_ean_upc_checksum(t):
                found.add(t)
        # Try enhance
        enh = ImageEnhance.Contrast(im_rot).enhance(1.8)
        for r in zxingcpp.read_barcodes(enh):
            t = str(r.text).strip()
            if t.isdigit() and validate_ean_upc_checksum(t):
                found.add(t)
    return list(found)

def main():
    pos_df = None
    for p in ["docs/G1_pos.csv", "data/pos.csv", "docs/pos_master.xlsx"]:
        if os.path.exists(p):
            if p.endswith('.csv'):
                pos_df = pd.read_csv(p)
            else:
                pos_df = pd.read_excel(p)
            break

    print(f"--- ANALYZING {len(ITEMS)} TARGET IMAGES ---")
    results = {}
    for fname in ITEMS:
        path = os.path.join("G1_original", fname)
        if not os.path.exists(path):
            print(f"{fname}: FILE NOT FOUND")
            continue
        
        with Image.open(path) as im:
            im_t = ImageOps.exif_transpose(im)
            bcs_raw = scan_barcodes_multi_angle(im)
            bcs_t = scan_barcodes_multi_angle(im_t)
            all_bcs = list(set(bcs_raw + bcs_t))
            
            # Quadrants scan
            w, h = im_t.size
            quads = [
                im_t.crop((0, 0, w//2, h//2)),
                im_t.crop((w//2, 0, w, h//2)),
                im_t.crop((0, h//2, w//2, h)),
                im_t.crop((w//2, h//2, w, h)),
                im_t.crop((0, 0, w//2, h)),
                im_t.crop((w//2, 0, w, h)),
            ]
            for q in quads:
                q_bcs = scan_barcodes_multi_angle(q)
                for b in q_bcs:
                    if b not in all_bcs:
                        all_bcs.append(b)
            
            results[fname] = all_bcs
            print(f"{fname} -> Barcodes found: {all_bcs}")

    print("\nSummary results:")
    print(json.dumps(results, indent=2))

if __name__ == '__main__':
    main()
