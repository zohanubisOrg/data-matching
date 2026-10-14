import os
import sys
import json
from pathlib import Path
import pandas as pd
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from product_mapper.ingestion.image_loader import open_image_safely

excel_path = PROJECT_ROOT / "output/shopify_import/Master_G2_G5_Consolidated.xlsx"
df = pd.read_excel(excel_path)

no_bc = df[df['barcode'].astype(str).str.contains('NO_BARCODE|nan|^$', case=False, na=True)]
print(f"Total NO_BARCODE rows: {len(no_bc)}")

# Locate the original image path for each row
source_dirs = [
    PROJECT_ROOT / "source-import/G2_original",
    PROJECT_ROOT / "source-import/G3_Original",
    PROJECT_ROOT / "source-import/G4-original",
    PROJECT_ROOT / "source-import/Nyt25.09.26"
]

records = []
for idx, r in no_bc.iterrows():
    photo_name = str(r.get('source_photo', '')).strip()
    batch = str(r.get('batch', '')).strip()
    
    found_path = None
    for sdir in source_dirs:
        p = sdir / photo_name
        if p.exists():
            found_path = p
            break
        # Also check case-insensitive match
        for f in sdir.iterdir():
            if f.name.lower() == photo_name.lower():
                found_path = f
                break
        if found_path:
            break
            
    records.append({
        "index": idx,
        "batch": batch,
        "source_photo": photo_name,
        "found_path": str(found_path) if found_path else None,
        "current_name": r.get('product_name'),
        "front_box_2d": r.get('front_box_2d')
    })

print(json.dumps(records, indent=2, ensure_ascii=False))
