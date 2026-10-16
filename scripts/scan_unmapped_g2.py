import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

import sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
import zxingcpp

unmapped_files = [
    'IMG_0433.jpeg', 'IMG_0439.jpeg', 'IMG_0511.jpeg', 'IMG_0513.jpeg',
    'IMG_0520.jpeg', 'IMG_0527.jpeg', 'IMG_0529.jpeg', 'IMG_0569.jpeg',
    'IMG_0570.jpeg', 'IMG_0571.jpeg', 'IMG_0616.jpeg', 'IMG_0640.jpeg',
    'IMG_0684.jpeg', 'IMG_0711.jpeg', 'IMG_0741.jpeg', 'IMG_0768.jpeg',
    'IMG_0801.jpeg', 'IMG_0847.jpeg', 'IMG_0850.jpeg', 'IMG_0858.jpeg',
    'IMG_0865.jpeg', 'IMG_0906.jpeg', 'IMG_0930.jpeg'
]

def scan_multi_pass(img_path: Path):
    with Image.open(img_path) as im:
        im = im.convert("RGB")
        # Ensure reasonable dimension to fit in memory
        if max(im.size) > 2400:
            im.thumbnail((2400, 2400), Image.Resampling.BILINEAR)
        base_arr = np.array(im)

    # Strategies
    # 1. Rotations
    for rot in [0, 90, 180, 270]:
        arr = np.rot90(base_arr, k=rot // 90)
        bcs = zxingcpp.read_barcodes(arr)
        if bcs:
            for b in bcs:
                if b.text and len(b.text.strip()) > 3:
                    return b.text.strip(), f"rot_{rot}"

    # 2. Quadrants (often barcodes are small in one corner)
    h, w, _ = base_arr.shape
    quads = [
        ("top_left", base_arr[0:int(h*0.6), 0:int(w*0.6)]),
        ("top_right", base_arr[0:int(h*0.6), int(w*0.4):w]),
        ("bottom_left", base_arr[int(h*0.4):h, 0:int(w*0.6)]),
        ("bottom_right", base_arr[int(h*0.4):h, int(w*0.4):w]),
        ("center", base_arr[int(h*0.2):int(h*0.8), int(w*0.2):int(w*0.8)])
    ]
    for q_name, q_arr in quads:
        for rot in [0, 90, 180, 270]:
            arr = np.rot90(q_arr, k=rot // 90)
            bcs = zxingcpp.read_barcodes(arr)
            if bcs:
                for b in bcs:
                    if b.text and len(b.text.strip()) > 3:
                        return b.text.strip(), f"quad_{q_name}_rot_{rot}"

    # 3. CLAHE enhancement
    gray = cv2.cvtColor(base_arr, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    for rot in [0, 90, 180, 270]:
        arr = np.rot90(enhanced, k=rot // 90)
        bcs = zxingcpp.read_barcodes(arr)
        if bcs:
            for b in bcs:
                if b.text and len(b.text.strip()) > 3:
                    return b.text.strip(), f"clahe_rot_{rot}"

    # 4. High contrast + Sharpen
    pil_enh = ImageEnhance.Contrast(im).enhance(2.0)
    pil_enh = pil_enh.filter(ImageFilter.SHARPEN)
    sharp_arr = np.array(pil_enh)
    for rot in [0, 90, 180, 270]:
        arr = np.rot90(sharp_arr, k=rot // 90)
        bcs = zxingcpp.read_barcodes(arr)
        if bcs:
            for b in bcs:
                if b.text and len(b.text.strip()) > 3:
                    return b.text.strip(), f"sharp_rot_{rot}"

    return None, None

def main():
    source_dir = Path("source-import/G2_original")
    recovered = {}
    for fn in unmapped_files:
        fp = source_dir / fn
        if not fp.exists():
            continue
        bc, method = scan_multi_pass(fp)
        if bc:
            print(f"[RECOVERED] {fn} -> {bc} via {method}")
            recovered[fn] = bc
        else:
            print(f"[NO BARCODE] {fn}")

    print("\nSummary:")
    print(f"Recovered {len(recovered)} / {len(unmapped_files)} unmapped barcodes.")
    import json
    with open("output/shopify-zohanubis-image/reports/recovered_g2_barcodes.json", "w", encoding="utf-8") as f:
        json.dump(recovered, f, indent=2)

if __name__ == "__main__":
    main()
