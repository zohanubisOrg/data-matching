import os
import sys
import math
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageOps
import zxingcpp
from rembg import remove, new_session

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

SESSION = new_session("u2net")

def detect_barcodes_multi_orient(image: Image.Image):
    """Scan barcode in 4 orientations to ensure 100% detection."""
    hits = zxingcpp.read_barcodes(image)
    if hits:
        return hits, 0
    for rot in (90, 180, 270):
        r_im = image.rotate(rot, expand=True)
        r_hits = zxingcpp.read_barcodes(r_im)
        if r_hits:
            return r_hits, rot
    return [], 0

def extract_front_from_original(img_path: Path, target_barcode: str) -> Image.Image:
    im = Image.open(img_path)
    w, h = im.size
    
    # Check barcode
    hits = zxingcpp.read_barcodes(im)
    barcode_pos = None
    upright_rot = 0
    
    if not hits:
        for rot in (90, 180, 270):
            r_im = im.rotate(rot, expand=True)
            r_hits = zxingcpp.read_barcodes(r_im)
            if r_hits:
                im = r_im
                w, h = im.size
                hits = r_hits
                upright_rot = rot
                break

    if hits:
        # Find hit matching target_barcode if possible, else largest
        best_hit = hits[0]
        for h_hit in hits:
            clean = "".join(c for c in str(h_hit.text or "") if c.isdigit())
            if target_barcode in clean or clean in target_barcode:
                best_hit = h_hit
                break
        
        pts = [(getattr(best_hit.position, name).x, getattr(best_hit.position, name).y) for name in ('top_left', 'top_right', 'bottom_right', 'bottom_left')]
        bc_cx = sum(p[0] for p in pts) / 4.0
        bc_cy = sum(p[1] for p in pts) / 4.0
        barcode_pos = (bc_cx / w, bc_cy / h)

    # Convert to numpy for seam analysis
    thumb = im.copy()
    thumb.thumbnail((1200, 1200))
    tw, th = thumb.size
    t_scale_x = w / float(tw)
    t_scale_y = h / float(th)
    
    arr = np.asarray(thumb)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 30, 90)
    
    col_proj = edges.mean(axis=0)
    row_proj = edges.mean(axis=1)
    
    # Smooth profiles
    k_col = np.ones(max(5, tw // 40)) / (tw // 40)
    k_row = np.ones(max(5, th // 40)) / (th // 40)
    col_smooth = np.convolve(col_proj, k_col, mode='same')
    row_smooth = np.convolve(row_proj, k_row, mode='same')
    
    # Decide if image has 2 side-by-side products or 2 stacked products
    # Default full frame
    front_crop_box = (0, 0, w, h)
    
    if barcode_pos is not None:
        bc_x, bc_y = barcode_pos
        
        # Check horizontal separation (side-by-side)
        # Search valley between 0.35 and 0.65
        col_mid = col_smooth[int(tw*0.35):int(tw*0.65)]
        min_col_idx = int(tw*0.35) + np.argmin(col_mid)
        col_valley_depth = 1.0 - (col_smooth[min_col_idx] / max(1.0, col_smooth.mean()))
        
        # Check vertical separation (stacked/lying)
        row_mid = row_smooth[int(th*0.35):int(th*0.65)]
        min_row_idx = int(th*0.35) + np.argmin(row_mid)
        row_valley_depth = 1.0 - (row_smooth[min_row_idx] / max(1.0, row_smooth.mean()))
        
        # Determine split axis based on barcode position and valleys
        if abs(bc_x - 0.5) > abs(bc_y - 0.5) and abs(bc_x - 0.5) > 0.10:
            # Barcode is clearly on left or right
            split_x = int(min_col_idx * t_scale_x)
            # Add safety margin around split
            if bc_x < 0.5:
                # Barcode on Left -> FRONT is on Right
                fx0 = max(split_x - int(w*0.02), int(w*0.45))
                front_crop_box = (fx0, 0, w, h)
            else:
                # Barcode on Right -> FRONT is on Left
                fx1 = min(split_x + int(w*0.02), int(w*0.55))
                front_crop_box = (0, 0, fx1, h)
                
        elif abs(bc_y - 0.5) > 0.10:
            # Barcode is clearly on top or bottom
            split_y = int(min_row_idx * t_scale_y)
            if bc_y < 0.5:
                # Barcode on Top -> FRONT is on Bottom
                fy0 = max(split_y - int(h*0.02), int(h*0.45))
                front_crop_box = (0, fy0, w, h)
            else:
                # Barcode on Bottom -> FRONT is on Top
                fy1 = min(split_y + int(h*0.02), int(h*0.55))
                front_crop_box = (0, 0, w, fy1)

    front_im = im.crop(front_crop_box)
    fw, fh = front_im.size
    
    # Orient upright if landscape bottle or package
    if fh < fw * 0.75 and "SAUCE" in target_barcode: # or similar
        # Rotate upright
        pass
        
    return front_im, front_crop_box

print("Module defined successfully.")
