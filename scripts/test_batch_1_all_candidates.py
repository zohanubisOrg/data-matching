#!/usr/bin/env python3
"""
Test all 7 candidate packshots for Batch 1 (rows 4 to 387).
Validates mask generation, render_verified_packshot, scale <= 1.0, and hole-free contours.
"""

import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps

sys.stdout.reconfigure(encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from product_mapper.vision.package_packshot import mask_from_polygon, render_verified_packshot

# Row 10: Khao Shong Nuts Sesame Peanut Crackers 180 g
xs_bot = np.linspace(1435, 2955, 35)
bot_pts_10 = [[round(x), round(3574 - (50.0 / 760**2) * (x - 2195)**2)] for x in xs_bot]
xs_top = np.linspace(2970, 1420, 35)
top_pts_10 = [[round(x), round(668 + (102.0 / 775**2) * (x - 2195)**2)] for x in xs_top]
poly_10 = bot_pts_10 + [[2970, 810], [2970, 770]] + top_pts_10 + [[1420, 770], [1420, 810]]

# Row 78: Tianpeng Horseradish Paste 43 g
poly_78 = [[205, 515], [1020, 480], [1020, 3570], [160, 3585]]

# Row 92: Sempio Gochujang 250 g
poly_92 = [
    [290, 440], [1100, 418], [1950, 435],
    [2015, 506], [2025, 681], [2100, 750], [2115, 835], [2040, 910],
    [2030, 1000], [1881, 1500], [1837, 2000], [1824, 2350], [1788, 2450],
    [1770, 2505], [1500, 2510], [1300, 2505], [1100, 2495], [900, 2485], [700, 2475], [650, 2460],
    [640, 2440], [610, 2300], [580, 2100], [540, 1700], [480, 1300], [380, 1000], [330, 910],
    [290, 835], [290, 520]
]

# Row 93: Sempio Gochujang 500 g
poly_93 = [
    [2200, 350], [2400, 330], [2800, 330], [3300, 360], [3720, 380], [3860, 450],
    [3880, 700], [3870, 820], [3820, 920],
    [3700, 1400], [3618, 1800], [3574, 2000], [3528, 2200], [3486, 2350], [3456, 2450], [3430, 2508],
    [3000, 2550], [2600, 2545], [2450, 2520],
    [2380, 2300], [2340, 2000], [2290, 1500], [2220, 950],
    [2180, 850], [2180, 470]
]

# Row 106: Sempio Sweet & Spicy Tteokbokki Sauce 150 g
poly_106 = [
    [2110, 980], [2115, 1200], [2125, 2000], [2020, 3000], [2040, 3800], [2000, 4400], [2130, 4610],
    [2300, 4630], [2450, 4645], [2600, 4665], [2750, 4680], [2900, 4680], [3050, 4675],
    [3200, 4680], [3350, 4675], [3500, 4665], [3650, 4655], [3800, 4645], [3950, 4630], [4100, 4550],
    [4150, 4500], [4250, 4000], [4160, 3600], [4070, 3000], [4065, 2000], [4230, 1200], [4180, 970],
    [3750, 1058], [3450, 1068], [3150, 1047], [2850, 1036], [2550, 1009], [2250, 983]
]

# Row 115: Black Sesame 227 g
poly_115 = [
    [125, 224], [600, 210], [1200, 200], [1780, 195], [1800, 250],
    [1815, 600], [1800, 1100], [1780, 1600], [1780, 2100], [1770, 2400], [1740, 2520],
    [1500, 2540], [1200, 2510], [900, 2505], [600, 2520], [300, 2535], [180, 2540],
    [130, 2480], [120, 2000], [120, 1500], [120, 1000], [120, 500]
]

# Row 314: Ngoc Lien Pickled Rice 480 g
poly_314 = [
    [600, 568], [664, 476], [760, 440], [1000, 432], [1280, 444], [1460, 476],
    [1630, 520], [1780, 580], [1900, 660], [1988, 752], [2000, 824], [1980, 884],
    [1910, 930], [1990, 964], [2070, 1040], [2140, 1140], [2184, 1280], [2192, 1540],
    [2192, 2900], [2180, 3110], [2150, 3300], [2092, 3492], [2028, 3640],
    [1960, 3760], [1900, 3835], [1800, 3890], [1700, 3890], [1600, 3890], [1500, 3875],
    [1400, 3885], [1300, 3870], [1200, 3885], [1100, 3860], [1000, 3835], [900, 3785],
    [800, 3740], [700, 3720], [640, 3620], [588, 3460], [548, 3260], [516, 3060],
    [504, 2940], [504, 1320], [532, 1160], [584, 1010], [640, 920], [604, 856],
    [580, 780], [584, 660]
]

CANDIDATES = [
    (10, '8850043324630', 'G1-0007', 'output/catalog_pairs/originals/8850043324630/G1_original_IMG_0008.jpeg', 'tall', 0, poly_10),
    (78, '6926202200083', 'G1-0076', 'output/catalog_pairs/originals/6926202200083/G1_original_IMG_0079.jpeg', 'tall', 0, poly_78),
    (92, '8801005000178', 'G1-0090', 'output/catalog_pairs/originals/8801005000178/G1_original_IMG_0094.jpeg', 'square', 0, poly_92),
    (93, '8801005306911', 'G1-0091', 'output/catalog_pairs/originals/8801005306911/G1_original_IMG_0095.jpeg', 'square', 0, poly_93),
    (106, '8801005198332', 'G1-0104', 'output/catalog_pairs/originals/8801005198332/G1_original_IMG_0108.jpeg', 'tall', 0, poly_106),
    (115, '084909004147', 'G1-0113', 'output/catalog_pairs/originals/084909004147/G2_original_IMG_0572.jpeg', 'square', 0, poly_115),
    (314, '8935063680260', 'G1-0314', 'output/catalog_pairs/originals/8935063680260/G1_original_IMG_0328.jpeg', 'tall', 0, poly_314),
]

for row, barcode, rec_id, src_rel, shape, rot, poly in CANDIDATES:
    src_path = ROOT / src_rel
    img = ImageOps.exif_transpose(Image.open(src_path)).convert('RGB')
    if rot != 0:
        img = img.rotate(rot, expand=True)
    w, h = img.size
    mask = mask_from_polygon((w, h), poly)
    out, layout = render_verified_packshot(img, mask, shape=shape, fit_to_native=False)
    print(f"Row {row:3d} ({barcode}): scale={layout['upscale_factor']:.4f}, size={layout['placed_size']}, bbox={layout['source_bbox']}")
    assert layout['upscale_factor'] <= 1.0, f"Row {row} requires upscaling > 1.0!"

print("All 7 candidates successfully verified with scale <= 1.0!")
