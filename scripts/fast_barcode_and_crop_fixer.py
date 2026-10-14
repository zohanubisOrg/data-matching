import sys
import os
import json
from pathlib import Path
import cv2
import numpy as np
import zxingcpp
from PIL import Image, ImageOps
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from product_mapper.ingestion.image_loader import open_image_safely
from scripts.deep_inspect_no_barcode import records

def scan_barcode_multi_technique(img_path: Path) -> tuple[str | None, list[int] | None]:
    try:
        pil_im = open_image_safely(img_path)
        orig_w, orig_h = pil_im.size
        cv_img = cv2.cvtColor(np.array(pil_im), cv2.COLOR_RGB2BGR)
    except Exception as e:
        return None, None

    # 1. Direct & Rotated ZXing
    for angle in [0, 90, 180, 270]:
        if angle == 0:
            cur_img = cv_img
        elif angle == 90:
            cur_img = cv2.rotate(cv_img, cv2.ROTATE_90_CLOCKWISE)
        elif angle == 180:
            cur_img = cv2.rotate(cv_img, cv2.ROTATE_180)
        elif angle == 270:
            cur_img = cv2.rotate(cv_img, cv2.ROTATE_90_COUNTERCLOCKWISE)

        results = zxingcpp.read_barcodes(cur_img)
        for r in results:
            text = r.text.strip()
            if text.isdigit() and len(text) in [8, 12, 13, 14]:
                pos = r.position
                # calculate normalized box if possible
                return text, [0, 0, 1000, 1000]

    # 2. Contrast Enhancement (CLAHE + Grayscale)
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    enhanced = clahe.apply(gray)
    for angle in [0, 90, 180, 270]:
        if angle == 0:
            cur_img = enhanced
        elif angle == 90:
            cur_img = cv2.rotate(enhanced, cv2.ROTATE_90_CLOCKWISE)
        elif angle == 180:
            cur_img = cv2.rotate(enhanced, cv2.ROTATE_180)
        elif angle == 270:
            cur_img = cv2.rotate(enhanced, cv2.ROTATE_90_COUNTERCLOCKWISE)

        results = zxingcpp.read_barcodes(cur_img)
        for r in results:
            text = r.text.strip()
            if text.isdigit() and len(text) in [8, 12, 13, 14]:
                return text, [0, 0, 1000, 1000]

    # 3. Morphological localization & High-res crop scan
    gradX = cv2.Sobel(gray, ddepth=cv2.CV_32F, dx=1, dy=0, ksize=-1)
    gradY = cv2.Sobel(gray, ddepth=cv2.CV_32F, dx=0, dy=1, ksize=-1)
    gradient = cv2.subtract(gradX, gradY)
    gradient = cv2.convertScaleAbs(gradient)
    blurred = cv2.blur(gradient, (9, 9))
    _, thresh = cv2.threshold(blurred, 220, 255, cv2.THRESH_BINARY)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 7))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    closed = cv2.erode(closed, None, iterations=4)
    closed = cv2.dilate(closed, None, iterations=4)

    contours, _ = cv2.findContours(closed.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in contours:
        if cv2.contourArea(c) > 500:
            x, y, w, h = cv2.boundingRect(c)
            # Add padding
            pad_w, pad_h = int(w * 0.3), int(h * 0.3)
            x0, y0 = max(0, x - pad_w), max(0, y - pad_h)
            x1, y1 = min(orig_w, x + w + pad_w), min(orig_h, y + h + pad_h)
            crop = cv_img[y0:y1, x0:x1]
            if crop.size > 0:
                for angle in [0, 90, 180, 270]:
                    if angle == 0:
                        c_rot = crop
                    elif angle == 90:
                        c_rot = cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE)
                    elif angle == 180:
                        c_rot = cv2.rotate(crop, cv2.ROTATE_180)
                    elif angle == 270:
                        c_rot = cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE)
                    
                    results = zxingcpp.read_barcodes(c_rot)
                    for r in results:
                        text = r.text.strip()
                        if text.isdigit() and len(text) in [8, 12, 13, 14]:
                            return text, [0, 0, 1000, 1000]

    return None, None

if __name__ == "__main__":
    print(f"Testing zxingcpp multi-technique on {len(records)} NO_BARCODE items...")
    found_count = 0
    for r in records:
        path_str = r.get("found_path")
        if path_str and Path(path_str).exists():
            code, _ = scan_barcode_multi_technique(Path(path_str))
            if code:
                found_count += 1
                print(f"[FOUND] {r['source_photo']} ({r['batch']}): Barcode = {code}")
            else:
                print(f"[NOT FOUND] {r['source_photo']} ({r['batch']})")
        else:
            print(f"[NO FILE] {r['source_photo']}")

    print(f"\nTotal Barcodes Decoded: {found_count} / {len(records)}")
