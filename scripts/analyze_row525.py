import json
from pathlib import Path
from PIL import Image
import numpy as np

ROOT = Path("D:/Work/shopify")

p = ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/ready_for_user_qa_388_760_run_20261015_01/8936089503175__G2-0064__row0525-front.png"
if p.exists():
    img = Image.open(p).convert("RGB")
    arr = np.asarray(img)
    print("Row 525 size:", img.size)
    print("Outer borders 255 pure white:", all((arr[0]==255).all(), (arr[-1]==255).all(), (arr[:,0]==255).all(), (arr[:,-1]==255).all()))
    mask = np.any(arr < 250, axis=2)
    y_indices, x_indices = np.where(mask)
    ymin, ymax = y_indices.min(), y_indices.max()
    xmin, xmax = x_indices.min(), x_indices.max()
    print(f"Bbox: [{xmin}, {ymin}, {xmax}, {ymax}] size: {xmax-xmin+1}x{ymax-ymin+1}")
    top_edge = arr[ymin:ymin+5, xmin:xmax+1]
    bottom_edge = arr[ymax-5:ymax+1, xmin:xmax+1]
    left_edge = arr[ymin:ymax+1, xmin:xmin+5]
    right_edge = arr[ymin:ymax+1, xmax-5:xmax+1]
    print("Top edge mean RGB:", top_edge.mean(axis=(0,1)))
    print("Bottom edge mean RGB:", bottom_edge.mean(axis=(0,1)))
    print("Left edge mean RGB:", left_edge.mean(axis=(0,1)))
    print("Right edge mean RGB:", right_edge.mean(axis=(0,1)))
else:
    print("Row 525 NOT FOUND:", p)
