import os
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
import openpyxl
sys.path.insert(0, ".")
from scripts.hd_studio_crop_pipeline import build_raw_file_index

raw_index = build_raw_file_index()
print(f"Raw index count: {len(raw_index)}")

wb = openpyxl.load_workbook("source-import/new_source_from_customer/11-10-new-requirment/Esbjerg_Asian_Market_Master_1659_updated.xlsx", data_only=True, read_only=True)
sheet = wb.active

test_bcs = {"8934563709150", "8934563107161", "6926410320160", "8850157516457", "8809705070521"}

for r in list(sheet.iter_rows(values_only=True))[3:]:
    stt = r[0]
    bc = str(r[2] or "").strip()
    if bc in test_bcs:
        src_photos = r[66]
        selected_front = r[67]
        fname = os.path.basename(str(selected_front or "")).lower()
        fpath = raw_index.get(fname)
        print(f"\n--- STT {stt} | BC: {bc} | {r[3]} ---")
        print(f"  Col 66 (Source photos):  {src_photos}")
        print(f"  Col 67 (Selected front): {selected_front}")
        print(f"  Found file path:         {fpath}")
