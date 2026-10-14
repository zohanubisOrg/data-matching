# -*- coding: utf-8 -*-
"""
Standard Image Preprocessor for all 1,659 photos across G1, G2, G3, G4, Nyt25.09.26.
Features:
- Decodes JPEG, JPG, PNG, and HEIC via pillow_heif.
- Normalizes EXIF orientation.
- Applies Front Face Bounding Box cropping & Upright Rotation.
- Creates clean square / aspect ratio padded e-commerce images (JPEG 95% + WebP 85%).
- Generates high quality thumbnails (150x150) for direct Excel embedding.
"""

import os
import sys
import json
import time
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance
import pillow_heif

pillow_heif.register_heif_opener()
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = r"D:\Work\shopify"
SOURCE_DIR = os.path.join(BASE_DIR, "source-import")
OUTPUT_DIR = os.path.join(BASE_DIR, r"output\shopify_import_final")
IMG_OUT_DIR = os.path.join(OUTPUT_DIR, "product_images")
THUMB_OUT_DIR = os.path.join(OUTPUT_DIR, "excel_delivery_thumbs")

os.makedirs(IMG_OUT_DIR, exist_ok=True)
os.makedirs(THUMB_OUT_DIR, exist_ok=True)

# 1. Load All Front Box Caches
box_cache = {}
# G1 boxes
g1_boxes_path = os.path.join(BASE_DIR, r"output\g1_delivery\front_layout_boxes.json")
if os.path.exists(g1_boxes_path):
    with open(g1_boxes_path, "r", encoding="utf-8") as f:
        g1_b = json.load(f)
        for k, v in g1_b.items():
            box_cache[k] = v

# G2-G5 boxes
g2_g5_boxes_path = os.path.join(BASE_DIR, r"output\shopify_import\g2_g5_front_boxes.json")
if os.path.exists(g2_g5_boxes_path):
    with open(g2_g5_boxes_path, "r", encoding="utf-8") as f:
        g2_b = json.load(f)
        for k, v in g2_b.items():
            box_cache[k] = v

print(f"Loaded {len(box_cache)} front box entries from cache.")

# Source Folders
src_folders = {
    "G1": os.path.join(SOURCE_DIR, "G1_original"),
    "G2": os.path.join(SOURCE_DIR, "G2_original"),
    "G3": os.path.join(SOURCE_DIR, "G3_Original"),
    "G4": os.path.join(SOURCE_DIR, "G4-original"),
    "G5": os.path.join(SOURCE_DIR, "Nyt25.09.26"),
}

def crop_and_process_image(src_path, fname):
    """
    Open image, apply EXIF, crop front face, rotate upright, create clean padded image & thumbnail.
    """
    try:
        with Image.open(src_path) as raw_img:
            img = ImageOps.exif_transpose(raw_img)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            
            orig_w, orig_h = img.size
            
            # Lookup box
            box_info = box_cache.get(fname, {})
            box = box_info.get("front_box_2d")
            rot = box_info.get("front_rotation_to_upright", 0) or box_info.get("front_rotation", 0) or 0
            
            if box and len(box) == 4:
                ymin, xmin, ymax, xmax = box
                # Normalize if 0-1000 or absolute
                if max(box) <= 1000:
                    left = max(0, int(xmin * orig_w / 1000))
                    top = max(0, int(ymin * orig_h / 1000))
                    right = min(orig_w, int(xmax * orig_w / 1000))
                    bottom = min(orig_h, int(ymax * orig_h / 1000))
                else:
                    left, top, right, bottom = int(xmin), int(ymin), int(xmax), int(ymax)
                
                # Check valid crop box
                if (right - left) >= 30 and (bottom - top) >= 30:
                    img = img.crop((left, top, right, bottom))
            
            # Apply rotation
            if rot in [90, 180, 270]:
                # rotate clockwise -> PIL rotate with counter-clockwise angle
                img = img.rotate(360 - rot, expand=True)
            
            # Create e-commerce canvas (clean padding with subtle white margin)
            w, h = img.size
            # Max dimension 1600px for web performance
            max_dim = 1600
            if max(w, h) > max_dim:
                scale = max_dim / max(w, h)
                new_w = max(1, int(w * scale))
                new_h = max(1, int(h * scale))
                img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            else:
                img_resized = img
            
            # Generate thumbnail (150x150 square canvas with white background)
            thumb_size = 150
            thumb_copy = img_resized.copy()
            thumb_copy.thumbnail((thumb_size, thumb_size), Image.Resampling.LANCZOS)
            
            # Paste thumbnail on white square canvas
            thumb_canvas = Image.new("RGB", (thumb_size, thumb_size), (255, 255, 255))
            paste_x = (thumb_size - thumb_copy.width) // 2
            paste_y = (thumb_size - thumb_copy.height) // 2
            if thumb_copy.mode == "RGBA":
                thumb_canvas.paste(thumb_copy, (paste_x, paste_y), thumb_copy)
            else:
                thumb_canvas.paste(thumb_copy, (paste_x, paste_y))
            
            return img_resized, thumb_canvas
    except Exception as e:
        print(f"Error processing {fname}: {e}")
        return None, None

def run_all():
    print("Starting preprocessing for all 1,659 images...")
    processed_count = 0
    errors = 0
    start_t = time.time()
    
    for batch_name, folder in src_folders.items():
        if not os.path.exists(folder):
            print(f"Folder not found: {folder}")
            continue
        
        files = [f for f in os.listdir(folder) if os.path.splitext(f)[1].lower() in ['.jpg', '.jpeg', '.png', '.webp', '.heic']]
        print(f"\nProcessing batch {batch_name}: {len(files)} images in {folder}...")
        
        for f in files:
            src_path = os.path.join(folder, f)
            stem = Path(f).stem
            
            # Process image
            full_img, thumb_img = crop_and_process_image(src_path, f)
            if full_img and thumb_img:
                # Save processed master images
                # 1. By original stem in product_images
                jpg_path = os.path.join(IMG_OUT_DIR, f"{stem}.jpg")
                webp_path = os.path.join(IMG_OUT_DIR, f"{stem}.webp")
                
                if full_img.mode == "RGBA":
                    rgb_img = Image.new("RGB", full_img.size, (255, 255, 255))
                    rgb_img.paste(full_img, mask=full_img.split()[3])
                    rgb_img.save(jpg_path, "JPEG", quality=95)
                else:
                    full_img.save(jpg_path, "JPEG", quality=95)
                
                full_img.save(webp_path, "WEBP", quality=85)
                
                # 2. Save thumbnail
                thumb_path = os.path.join(THUMB_OUT_DIR, f"{stem}.jpg")
                thumb_img.save(thumb_path, "JPEG", quality=90)
                
                processed_count += 1
            else:
                errors += 1
    
    elapsed = time.time() - start_t
    print(f"\n==========================================")
    print(f"Preprocessing completed in {elapsed:.2f}s")
    print(f"Successfully processed: {processed_count} / 1659 images")
    print(f"Errors: {errors}")
    print(f"==========================================")

if __name__ == "__main__":
    run_all()
