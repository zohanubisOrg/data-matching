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

multi_photos = []
g_counts = {}
sample_rows = []

for r in list(sheet.iter_rows(values_only=True))[3:]:
    stt = r[0]
    bc = r[2]
    name = r[3]
    src_photos = str(r[66] or "").strip()
    selected_front = str(r[67] or "").strip()
    
    # check group prefix
    group = selected_front.split("/")[0] if "/" in selected_front else "unknown"
    g_counts[group] = g_counts.get(group, 0) + 1
    
    # check multiple photos listed
    parts = [p for p in src_photos.replace(",", " ").split() if "." in p]
    if len(parts) > 1:
        multi_photos.append((stt, bc, name, src_photos, selected_front))

print(f"Total rows inspected. Group distribution:")
for g, cnt in g_counts.items():
    print(f"  - {g}: {cnt} items")

print(f"\nItems with multiple source photos listed: {len(multi_photos)}")
for m in multi_photos[:15]:
    print(f"  STT {m[0]} | BC: {m[1]} | {m[2][:40]}")
    print(f"    Photos:   {m[3]}")
    print(f"    Selected: {m[4]}")
