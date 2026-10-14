import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
import openpyxl

wb = openpyxl.load_workbook('source-import/new_source_from_customer/11-10-new-requirment/Esbjerg_Asian_Market_Master_1659_updated.xlsx', data_only=True, read_only=True)
sheet = wb.active

for r_idx, row in enumerate(sheet.iter_rows(values_only=True, max_row=5)):
    non_empty = [(c_idx, val) for c_idx, val in enumerate(row) if val is not None]
    print(f"Row {r_idx}: {len(non_empty)} non-empty cells")
    for c_idx, val in non_empty:
        val_str = str(val).strip()
        if any(k in val_str.lower() for k in ['image', 'photo', 'anh', 'ảnh', 'front', 'back', 'hình', 'barcode', 'sku', 'stt']):
            print(f"  Col {c_idx}: {val_str}")
    if r_idx == 2:
        break
