import os
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
import openpyxl

file_path = "source-import/new_source_from_customer/11-10-new-requirment/Esbjerg_Asian_Market_Barcode_Da_Loc.xlsx"
wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)

print(f"Sheets in {os.path.basename(file_path)}:")
for name in wb.sheetnames:
    sheet = wb[name]
    rows = list(sheet.iter_rows(values_only=True))
    print(f"\n==========================================")
    print(f"Sheet '{name}': {len(rows)} total rows")
    if rows:
        # find header row
        for r_idx in range(min(5, len(rows))):
            non_empty = [(idx, val) for idx, val in enumerate(rows[r_idx]) if val is not None]
            if len(non_empty) > 3:
                print(f"  Header candidates at row {r_idx+1} ({len(non_empty)} cols):")
                for c_idx, val in non_empty[:15]:
                    print(f"    Col {c_idx}: {val}")
                break
        
        # print first data row
        sample_row = rows[min(len(rows)-1, 3 if len(rows) > 3 else 1)]
        non_empty_sample = [(idx, val) for idx, val in enumerate(sample_row) if val is not None]
        print(f"  Sample data row:")
        for c_idx, val in non_empty_sample[:10]:
            print(f"    Col {c_idx}: {val}")
