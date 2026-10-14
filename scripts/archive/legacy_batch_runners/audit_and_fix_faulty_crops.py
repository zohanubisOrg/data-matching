from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image
from src.product_mapper.ingestion.image_loader import open_image_safely, save_image_high_quality

OUTPUT_BASE = Path("output/shopify_import")
IMAGES_DIR = OUTPUT_BASE / "images"


def audit_and_repair_crops(batch_folders: dict[str, Path]):
    """Scans all generated front crops, detects faulty/clipped crops, and repairs them automatically."""
    print("==========================================")
    print("🔍 Starting Automated Crop Quality Acceptance Audit")
    print("==========================================")

    manifest_file = Path("output/g2_g5_manifest.json")
    if not manifest_file.exists():
        print("Manifest not found! Run scripts/build_manifest.py first.")
        return

    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # Build filename to path map
    raw_images_map: dict[str, Path] = {}
    for b_name, b_data in manifest.get("batches", {}).items():
        for f_entry in b_data.get("files", []):
            raw_images_map[f_entry["filename"]] = Path(f_entry["relative_path"])

    # Load cache files
    cache_map: dict[str, Any] = {}
    for cache_file in OUTPUT_BASE.glob("*_vision_cache.json"):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                c_data = json.load(f)
                cache_map.update(c_data)
        except Exception:
            pass

    total_checked = 0
    repaired_count = 0

    for crop_path in IMAGES_DIR.glob("*.jpg"):
        total_checked += 1
        stem = crop_path.stem
        
        try:
            with Image.open(crop_path) as im:
                w, h = im.size
                ratio = h / w if w > 0 else 0
                
                # Check 1: Horizontal crop (H < W) -> Needs rotation or re-crop
                # Check 2: Unusually low aspect ratio for packaging (ratio < 0.85)
                needs_repair = False
                repair_reason = ""
                
                if ratio < 0.95:
                    needs_repair = True
                    repair_reason = f"Aspect ratio too wide ({w}x{h}, ratio={ratio:.2f})"
                elif w < 250 or h < 350:
                    needs_repair = True
                    repair_reason = f"Dimensions too small ({w}x{h})"

                if needs_repair:
                    # Find original image and vision result
                    # Look for raw image that maps to this barcode
                    found_raw = None
                    v_res = None
                    for raw_fname, raw_path in raw_images_map.items():
                        c_entry = cache_map.get(raw_fname)
                        if c_entry and c_entry.get("barcode") == stem:
                            found_raw = raw_path
                            v_res = c_entry
                            break
                    
                    if found_raw and found_raw.exists():
                        raw_im = open_image_safely(found_raw)
                        orig_w, orig_h = raw_im.size
                        box = v_res.get("front_box_2d") if v_res else None
                        
                        if box and len(box) == 4:
                            ymin, xmin, ymax, xmax = box
                            # Expand margin to 8% to prevent clipping
                            pad_w = int((xmax - xmin) * 0.08)
                            pad_h = int((ymax - ymin) * 0.08)
                            left = max(0, int((xmin - pad_w) * orig_w / 1000))
                            top = max(0, int((ymin - pad_h) * orig_h / 1000))
                            right = min(orig_w, int((xmax + pad_w) * orig_w / 1000))
                            bottom = min(orig_h, int((ymax + pad_h) * orig_h / 1000))
                            new_crop = raw_im.crop((left, top, right, bottom))
                        else:
                            new_crop = raw_im.crop((0, 0, int(orig_w * 0.52), orig_h))
                            
                        rot = int(v_res.get("front_rotation", 0) or 0) if v_res else 0
                        if rot != 0:
                            new_crop = new_crop.rotate(-rot, expand=True)
                            
                        if new_crop.height < new_crop.width:
                            new_crop = new_crop.rotate(270, expand=True)
                            
                        save_image_high_quality(new_crop, crop_path, quality=95, save_webp=True)
                        repaired_count += 1
                        print(f"🔧 Repaired crop {crop_path.name}: {repair_reason} -> New size: {new_crop.size}")
        except Exception as e:
            print(f"Error checking {crop_path}: {e}")

    print(f"\nAudit complete: Checked {total_checked} crops. Repaired {repaired_count} faulty images.")


if __name__ == "__main__":
    batch_folders = {
        "G2": Path("source-import/G2_original"),
        "G3": Path("source-import/G3_Original"),
        "G4": Path("source-import/G4-original"),
        "G5": Path("source-import/Nyt25.09.26"),
    }
    audit_and_repair_crops(batch_folders)
