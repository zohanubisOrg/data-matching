import json
import sys
from pathlib import Path
from PIL import Image, ImageOps
import pillow_heif
pillow_heif.register_heif_opener()

ROOT = Path(__file__).resolve().parent.parent
sys.path.extend([str(ROOT / "scripts"), str(ROOT / "src")])

from product_mapper.vision.barcode_side_splitter import read_retail_barcodes, split_sides
from product_mapper.ingestion.image_loader import open_image_safely
from retry_g2_missing_barcodes import hard_read

items = [
    ("084909006608", ROOT / "source-import/G1_original/IMG_0350.jpeg"),
    ("4016337982502", ROOT / "source-import/G3_Original/IMG_1437.jpeg"),
    ("4045198857032", ROOT / "source-import/G3_Original/IMG_1298.jpeg"),
    ("4045198908116", ROOT / "source-import/G3_Original/IMG_1380.jpeg"),
    ("4045198925151", ROOT / "source-import/G3_Original/IMG_5172.HEIC"),
    ("4316734061498", ROOT / "source-import/G3_Original/IMG_1319.jpeg"),
    ("4897068793861", ROOT / "source-import/G4-original/20260916_112652662_iOS.heic"),
    ("6924200920156", ROOT / "source-import/G1_original/IMG_0173.jpeg"),
    ("6944546168333", ROOT / "source-import/G4-original/20260916_111748748_iOS.heic"),
    ("8445198964000", ROOT / "source-import/G3_Original/IMG_5128.HEIC"),
    ("8713913003304", ROOT / "source-import/G3_Original/IMG_5090.HEIC"),
    ("8720812774334", ROOT / "source-import/G1_original/IMG_0027.jpeg"),
    ("8850060110063", ROOT / "source-import/G4-original/20260916_112840856_iOS.heic"),
    ("8850060110551", ROOT / "source-import/G4-original/20260916_111222616_iOS.heic"),
    ("8850060110834", ROOT / "source-import/G4-original/20260916_111118920_iOS.heic"),
    ("8850060444458", ROOT / "source-import/G4-original/20260916_111329184_iOS.heic"),
    ("8850987131240", ROOT / "source-import/G2_original/IMG_0735.jpeg"),
    ("8853662056029", ROOT / "source-import/G1_original/IMG_0383.jpeg"),
    ("8854923313301", ROOT / "source-import/G1_original/IMG_0042.jpeg"),
    ("8936014316658", ROOT / "source-import/G1_original/IMG_9947.jpeg"),
    ("8938500969928", ROOT / "source-import/G1_original/IMG_0308.jpeg"),
]

report = []

for bc, p in items:
    img = open_image_safely(p)
    w, h = img.size
    hits = read_retail_barcodes(img)
    bc_pos = None
    if hits:
        best_hit = max(hits, key=lambda x: x.area)
        bc_pos = {
            "text": best_hit.text,
            "cx_pct": round(best_hit.center_x / w, 3),
            "cy_pct": round(best_hit.center_y / h, 3),
            "angle": best_hit.angle
        }
    else:
        hr = hard_read(p)
        if hr:
            bc_pos = {
                "text": hr["text"],
                "cx_pct": round(hr["center"][0] / w, 3),
                "cy_pct": round(hr["center"][1] / h, 3),
                "angle": "hard_read"
            }
    
    # Check current error image in image-error-resolve-again
    err_p = ROOT / f"output/catalog_pairs/image-error-resolve-again/{bc}-back.jpg"
    err_w, err_h = 0, 0
    err_has_bc = False
    if err_p.exists():
        e_img = open_image_safely(err_p)
        err_w, err_h = e_img.size
        e_hits = read_retail_barcodes(e_img)
        err_has_bc = len(e_hits) > 0
        e_img.close()

    # Split sides default
    cx = (bc_pos["cx_pct"] * w) if bc_pos else w / 2
    cy = (bc_pos["cy_pct"] * h) if bc_pos else h / 2
    sides = split_sides(img, cx, cy, 0)

    report.append({
        "barcode": bc,
        "source_file": p.name,
        "img_size": [w, h],
        "barcode_detected": bc_pos,
        "err_back_size": [err_w, err_h],
        "err_back_has_bc": err_has_bc,
        "split_mode": sides.mode,
        "default_back_pct": [round(sides.back[0]/w, 3), round(sides.back[1]/h, 3), round(sides.back[2]/w, 3), round(sides.back[3]/h, 3)],
        "default_front_pct": [round(sides.front[0]/w, 3), round(sides.front[1]/h, 3), round(sides.front[2]/w, 3), round(sides.front[3]/h, 3)] if sides.front else None,
    })
    img.close()

(ROOT / "output/catalog_pairs/review/analysis_21_errors.json").write_text(
    json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
)
print("Analysis saved to analysis_21_errors.json")
