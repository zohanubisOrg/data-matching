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

rows = list(sheet.iter_rows(values_only=True, max_row=15))[3:]

for r in rows:
    stt = r[0]
    bc = r[2]
    name = r[3]
    src_photos = r[66]
    selected_front = r[67]
    front_rel = r[69]
    front_line = r[76]
    front_pic = r[77]
    cdn_link = r[93] if len(r) > 93 else None
    print(f"--- STT {stt} | BC: {bc} | {name} ---")
    print(f"  Col 66 (Source photos):       {src_photos}")
    print(f"  Col 67 (Selected front):      {selected_front}")
    print(f"  Col 69 (Front rel filename):  {front_rel}")
    print(f"  Col 76 (Dòng nguồn mặt trước):{front_line}")
    print(f"  Col 77 (Ảnh mặt trước):       {front_pic}")
    print(f"  Col 93 (Link CDN):            {cdn_link}")
