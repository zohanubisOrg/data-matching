import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.extend([str(ROOT / "scripts"), str(ROOT / "src")])

from barcode_first_pipeline import load_ground_truth
from retry_g2_missing_barcodes import hard_read

prods = load_ground_truth(ROOT / "source-import/new_source_from_customer/12-10-new-requirment/Rabuta.12.10.2026_original.xlsx")
prod_map = {p["barcode"]: p for p in prods}

items = [
    ("084909006608", ROOT / "source-import/G1_original/IMG_0350.jpeg"),
    ("8720812774334", ROOT / "source-import/G1_original/IMG_0027.jpeg"),
    ("8850060110063", ROOT / "source-import/G4-original/20260916_112840856_iOS.heic"),
    ("8850060110551", ROOT / "source-import/G4-original/20260916_111222616_iOS.heic"),
    ("8850060110834", ROOT / "source-import/G4-original/20260916_111118920_iOS.heic"),
    ("8850060444458", ROOT / "source-import/G4-original/20260916_111329184_iOS.heic"),
    ("8854923313301", ROOT / "source-import/G1_original/IMG_0042.jpeg"),
    ("8938500969928", ROOT / "source-import/G1_original/IMG_0308.jpeg"),
]

for bc, p in items:
    info = prod_map.get(bc, {})
    brand = info.get("brand", "")
    name = info.get("name_en", "")
    print("=" * 60)
    print(f"{bc}: {brand} | {name}")
    hr = hard_read(Path(p))
    if hr:
        c = hr["center"]
        txt = hr["text"]
        print(f"   hard_read: {txt} at center=({c[0]:.1f}, {c[1]:.1f})")
    else:
        print("   hard_read: no barcode found")
