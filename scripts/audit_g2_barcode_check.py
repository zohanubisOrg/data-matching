import sys, os, re, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from barcode_first_pipeline import load_ground_truth, truth_lookup
from product_mapper.vision.barcode_validator import get_barcode_lookup_variants

EXCEL_SOURCE = ROOT / "source-import/new_source_from_customer/12-10-new-requirment/Rabuta.12.10.2026_original.xlsx"
gt = load_ground_truth(EXCEL_SOURCE)
lookup = truth_lookup(gt)

bc_to_info = {}
for item in gt:
    b = str(item.get("barcode", "")).strip()
    if b:
        bc_to_info[b] = item

check_dir = ROOT / "output/catalog_pairs/tagged/g2-barcode-check"
files = sorted([f.name for f in check_dir.iterdir() if f.is_file()])

verified_map = {
    "IMG_0443": "4316734096117",
    "IMG_0445": "8936147330170",
    "IMG_0446": "8936147330170",
    "IMG_0447": "8936147330170",
    "IMG_0449": "8853662056296",
    "IMG_0455": "8850213107506",
    "IMG_0470": "8850293200098",
    "IMG_0471": "8850293200098",
    "IMG_0482": "4800110091563",
    "IMG_0487": "8850256620079",
    "IMG_0492": "084909003904",
    "IMG_0518": "8851011124269",
    "IMG_0526": "8850521171312",
    "IMG_0528": "8850521171312",
    "IMG_0532": "8936013740331",
    "IMG_0538": "8850035051001",
    "IMG_0549": "016229000561",
    "IMG_0551": "8938500075070",
    "IMG_0553": "6921379720037",
    "IMG_0554": "6921379720037",
    "IMG_0555": "6921379720037",
    "IMG_0565": "8934734102100",
    "IMG_0573": "084909004147",
    "IMG_0578": "030891054134",
    "IMG_0588": "8850030035082",
    "IMG_0594": "8854334004645",
    "IMG_0603": "8934707027478",
    "IMG_0637": "8801043055659",
    "IMG_0647": "8801073116474",
    "IMG_0654": "8936010681606",
    "IMG_0659": "8850100003713",
    "IMG_0665": "8850987128158",
    "IMG_0679": "8850987141171",
    "IMG_0709": "8801045999906",
    "IMG_0710": "8801045999906",
    "IMG_0772": "8936007820544",
    "IMG_0800": "4806011822688",
    "IMG_0810": "8859745301963",
    "IMG_0825": "8850931040680",
    "IMG_0826": "8850931040680",
    "IMG_0835": "8936062107994",
    "IMG_0839": "8717624005060",
    "IMG_0861": "7350072778967",
    "IMG_0866": "4045198712508",
    "IMG_0912": "7178600000140",
    "IMG_0921": "5013635366101",
    "IMG_0923": "5011308307062",
    "IMG_0924": "5011308307062",
    "IMG_0926": "7178600000201",
}

FRONT_DIR = ROOT / "output/catalog_pairs/tagged/front-v2"
BACK_DIR = ROOT / "output/catalog_pairs/tagged/back-v2"

summary = []
for fname in sorted(files):
    stem = os.path.splitext(fname)[0]
    bc = verified_map.get(stem)
    in_excel = False
    prod_name = ""
    if bc:
        for v in get_barcode_lookup_variants(bc):
            if v in lookup:
                in_excel = True
                canonical = lookup[v]
                prod_name = bc_to_info.get(canonical, {}).get("name_en", "")
                break
    f_exists = (FRONT_DIR / f"{bc}-front.jpg").exists() if bc else False
    b_exists = (BACK_DIR / f"{bc}-back.jpg").exists() if bc else False
    summary.append({
        "file": fname,
        "barcode": bc,
        "in_excel": in_excel,
        "product": prod_name,
        "front_v2_exists": f_exists,
        "back_v2_exists": b_exists
    })

print(f"Total files analyzed: {len(summary)}")
in_excel_count = sum(1 for s in summary if s["in_excel"])
print(f"All files in Excel: {in_excel_count} / {len(summary)}")

need_export = [s for s in summary if not (s["front_v2_exists"] and s["back_v2_exists"])]
print(f"\nFiles needing export (missing front or back in v2): {len(need_export)}")
for item in need_export:
    f_stat = "OK" if item["front_v2_exists"] else "MISSING"
    b_stat = "OK" if item["back_v2_exists"] else "MISSING"
    print(f"  {item['file']} -> {item['barcode']} | Front: {f_stat}, Back: {b_stat} | {item['product']}")
