import cv2
import numpy as np
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent

for f in sorted((ROOT / "output/catalog_pairs/image-error-resolve-again").glob("*.jpg")):
    bc = f.name.replace("-back.jpg", "")
    im = Image.open(f)
    print(f"Error back: {f.name}, size: {im.size}")
    # Compare with current front-v2 and back-v2
    cur_f = ROOT / f"output/catalog_pairs/tagged/front-v2/{bc}-front.jpg"
    cur_b = ROOT / f"output/catalog_pairs/tagged/back-v2/{bc}-back.jpg"
    print(f"   front-v2 exists: {cur_f.exists()}, back-v2 exists: {cur_b.exists()}")
    if cur_f.exists():
        im_f = Image.open(cur_f)
        print(f"   front-v2 size: {im_f.size}")
    if cur_b.exists():
        im_b = Image.open(cur_b)
        print(f"   back-v2 size: {im_b.size}")
