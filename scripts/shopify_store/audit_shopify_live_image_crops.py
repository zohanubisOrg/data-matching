import os
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from pathlib import Path
import json
import pandas as pd
import openpyxl

# 1. Load combined verified cache
g1_cache = {}
if os.path.exists("output/g1_delivery/front_layout_boxes.json"):
    with open("output/g1_delivery/front_layout_boxes.json", "r", encoding="utf-8") as f:
        g1_cache = json.load(f)

g2_g5_cache = {}
if os.path.exists("output/shopify_import/g2_g5_front_boxes.json"):
    with open("output/shopify_import/g2_g5_front_boxes.json", "r", encoding="utf-8") as f:
        g2_g5_cache = json.load(f)

verified_cache = {}
for k, v in g1_cache.items():
    verified_cache[k.lower()] = {
        "box": v.get("front_box_2d"),
        "rot": v.get("front_rotation", 0),
        "pos": v.get("front_side_position", "unknown")
    }
for k, v in g2_g5_cache.items():
    verified_cache[k.lower()] = {
        "box": v.get("front_box_2d"),
        "rot": v.get("front_rotation_to_upright", 0),
        "pos": v.get("front_position", "unknown")
    }

# 2. Load Master mapping
sys.path.insert(0, ".")
from scripts.hd_studio_crop_pipeline import build_raw_file_index
from scripts.cv_front_detector import detect_front_box_cv

raw_index = build_raw_file_index()

wb = openpyxl.load_workbook("source-import/new_source_from_customer/11-10-new-requirment/Esbjerg_Asian_Market_Master_1659_updated.xlsx", data_only=True, read_only=True)
sheet = wb.active

master_dict = {} # barcode -> item info
for r in list(sheet.iter_rows(values_only=True))[3:]:
    stt = r[0]
    bc = str(r[2] or "").strip()
    name = str(r[3] or "").strip()
    selected_front = str(r[67] or "").strip()
    fname = os.path.basename(selected_front).lower()
    fpath = raw_index.get(fname)
    master_dict[bc] = {
        "stt": stt,
        "name": name,
        "selected_front": selected_front,
        "fname": fname,
        "fpath": fpath
    }

# 3. Load Shopify Live Audit
df_live = pd.read_excel("output/reconciliation/Shopify_Live_Catalog_Full_Audit.xlsx")
print(f"Total live products on Shopify: {len(df_live)}")

audit_results = []
severe_back_side_count = 0
severe_dual_panel_unsplit_count = 0
accurate_count = 0

for idx, r in df_live.iterrows():
    raw_bc = str(r.get("Variant_Barcode", "")).strip()
    if raw_bc.endswith(".0"):
        raw_bc = raw_bc[:-2]
    
    m_info = master_dict.get(raw_bc)
    if not m_info or not m_info["fpath"]:
        continue
    
    fname = m_info["fname"]
    fpath = Path(m_info["fpath"])
    v_data = verified_cache.get(fname)
    if not v_data or not v_data["box"]:
        continue
    
    v_box = v_data["box"]
    v_pos = v_data["pos"]
    
    # Run CV detector
    cv_box, _, cv_label = detect_front_box_cv(fpath)
    
    # Analyze error category
    v_ymin, v_xmin, v_ymax, v_xmax = v_box
    c_ymin, c_xmin, c_ymax, c_xmax = cv_box
    
    error_type = "ACCURATE"
    
    # Check if raw photo had dual panels (left vs right or top vs bottom)
    is_dual = v_pos in ("left", "right", "top", "bottom")
    
    if is_dual:
        # Check if CV took opposite side (e.g. front was left, but CV took right -> BACK SIDE!)
        if v_pos == "left" and c_xmin > 400:
            error_type = "WRONG_SIDE_TAKEN_BACK (Front is Left, CV picked Right/Back)"
            severe_back_side_count += 1
        elif v_pos == "right" and c_xmax < 600:
            error_type = "WRONG_SIDE_TAKEN_BACK (Front is Right, CV picked Left/Back)"
            severe_back_side_count += 1
        elif v_pos == "bottom" and c_ymax < 600:
            error_type = "WRONG_SIDE_TAKEN_BACK (Front is Bottom, CV picked Top/Back)"
            severe_back_side_count += 1
        elif v_pos == "top" and c_ymin > 400:
            error_type = "WRONG_SIDE_TAKEN_BACK (Front is Top, CV picked Bottom/Back)"
            severe_back_side_count += 1
        # Check if CV took full photo merging front and back
        elif (v_pos in ("left", "right") and (c_xmax - c_xmin) > 750):
            error_type = "DUAL_PANEL_NOT_SPLIT (Merged Front & Back together in 1 image)"
            severe_dual_panel_unsplit_count += 1
        elif (v_pos in ("top", "bottom") and (c_ymax - c_ymin) > 750):
            error_type = "DUAL_PANEL_NOT_SPLIT (Merged Front & Back vertically in 1 image)"
            severe_dual_panel_unsplit_count += 1
        else:
            diff = abs(c_xmin - v_xmin) + abs(c_xmax - v_xmax) + abs(c_ymin - v_ymin) + abs(c_ymax - v_ymax)
            if diff > 400:
                error_type = "IMPRECISE_CROP (Packaging cut or offset)"
            else:
                accurate_count += 1
    else:
        diff = abs(c_xmin - v_xmin) + abs(c_xmax - v_xmax) + abs(c_ymin - v_ymin) + abs(c_ymax - v_ymax)
        if diff > 500:
            error_type = "IMPRECISE_CROP (Full contour misaligned)"
        else:
            accurate_count += 1

    audit_results.append({
        "Product_ID": r.get("Product_ID"),
        "Barcode": raw_bc,
        "Title": r.get("Title"),
        "Primary_Image_URL": r.get("Primary_Image_URL"),
        "Raw_File": fname,
        "Front_Position": v_pos,
        "Verified_Box": v_box,
        "Flawed_CV_Box": cv_box,
        "CV_Label": cv_label,
        "Error_Classification": error_type
    })

df_res = pd.DataFrame(audit_results)
os.makedirs("output/audit", exist_ok=True)
audit_path_xlsx = "output/audit/Shopify_Live_Image_Crop_Audit.xlsx"
df_res.to_excel(audit_path_xlsx, index=False)

print("\n========================================================")
print("       📸 SHOPIFY LIVE IMAGE CROP AUDIT RESULTS          ")
print("========================================================")
print(f"Total Live Products Audited:         {len(df_res):>6}")
print(f"--------------------------------------------------------")
print(f"❌ 1. WRONG SIDE (TAKEN BACK SIDE):  {severe_back_side_count:>6} ({severe_back_side_count/len(df_res)*100:.1f}%)")
print(f"⚠️  2. DUAL PANEL NOT SPLIT (BOTH):   {severe_dual_panel_unsplit_count:>6} ({severe_dual_panel_unsplit_count/len(df_res)*100:.1f}%)")
other_imprecise = len(df_res[df_res['Error_Classification'].str.contains('IMPRECISE')])
print(f"⚠️  3. IMPRECISE / SEVERED CROPS:     {other_imprecise:>6} ({other_imprecise/len(df_res)*100:.1f}%)")
print(f"✅ 4. CLEAN & ACCURATE CROPS:        {accurate_count:>6} ({accurate_count/len(df_res)*100:.1f}%)")
total_flawed = severe_back_side_count + severe_dual_panel_unsplit_count + other_imprecise
print(f"--------------------------------------------------------")
print(f"🚨 TOTAL FLAWED CROPS ON LIVE STORE: {total_flawed:>6} ({total_flawed/len(df_res)*100:.1f}%)")
print("========================================================")
print(f"[+] Full audit report saved to: {audit_path_xlsx}")
