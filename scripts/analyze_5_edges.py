import json
from pathlib import Path
from PIL import Image
import numpy as np

ROOT = Path("D:/Work/shopify")

def inspect_edge_and_content(cand_path, name):
    print(f"\n=================== Detailed QA Analysis: {name} ===================")
    img = Image.open(cand_path).convert("RGB")
    arr = np.asarray(img)
    
    # Check non-white pixels
    mask = np.any(arr < 250, axis=2)
    y_indices, x_indices = np.where(mask)
    if len(y_indices) == 0:
        print("ERROR: Image is empty!")
        return
    
    ymin, ymax = y_indices.min(), y_indices.max()
    xmin, xmax = x_indices.min(), x_indices.max()
    print(f"Bounding Box: [{xmin}, {ymin}, {xmax}, {ymax}] size: {xmax-xmin+1}x{ymax-ymin+1}")
    
    # Check 1-pixel outer border
    top_edge = arr[ymin:ymin+5, xmin:xmax+1]
    bottom_edge = arr[ymax-5:ymax+1, xmin:xmax+1]
    left_edge = arr[ymin:ymax+1, xmin:xmin+5]
    right_edge = arr[ymin:ymax+1, xmax-5:xmax+1]
    
    print(f"Top edge mean color: {top_edge.mean(axis=(0,1))}")
    print(f"Bottom edge mean color: {bottom_edge.mean(axis=(0,1))}")
    print(f"Left edge mean color: {left_edge.mean(axis=(0,1))}")
    print(f"Right edge mean color: {right_edge.mean(axis=(0,1))}")

inspect_edge_and_content(
    ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/render_native_scale_refined_850_886_894_v2/4045198753174__G2-0401__row0850-front.png",
    "Row 850 - 4045198753174 Fried Red Onion"
)
inspect_edge_and_content(
    ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/render_native_scale_refined_850_886_894_v2/7178600000140__G2-0437__row0886-front.png",
    "Row 886 - 7178600000140 PASCO Mild Curry"
)
inspect_edge_and_content(
    ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/render_native_scale_refined_850_886_894_v2/5017689097905__G2-0445__row0894-front.png",
    "Row 894 - 5017689097905 TRS Boiled Chickpeas"
)
inspect_edge_and_content(
    ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/render_native_scale_scan_926_970_v2/6922163623848__G3-0025__row0926-front.png",
    "Row 926 - 6922163623848 Oolong Tea"
)
inspect_edge_and_content(
    ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/render_native_scale_scan_926_970_v2/8855790000028__G3-0080__row0970-front.png",
    "Row 970 - 8855790000028 Carabao Energy Drink"
)
