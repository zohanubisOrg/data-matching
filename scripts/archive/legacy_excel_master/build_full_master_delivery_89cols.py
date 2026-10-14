# -*- coding: utf-8 -*-
"""
Build Complete Customer Master Delivery Files (89-column standard + Embedded Images)
Conforms 100% to Product_master_25.09.26- til Bao.xlsx + 27.09.26.POS_ACTIVE_FINAL.xlsx
"""

import os
import sys
import re
import csv
import shutil
import unicodedata
from pathlib import Path
from PIL import Image as PILImage
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.drawing.image import Image as OpenpyxlImage
from openpyxl.utils import get_column_letter

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = r"D:\Work\shopify"
SOURCE_DIR = os.path.join(BASE_DIR, r"source-import\new_source_from_customer")
OUTPUT_DIR = os.path.join(BASE_DIR, r"output\shopify_import_final")
IMG_FINAL_DIR = os.path.join(OUTPUT_DIR, "product_images")
THUMBS_DIR = os.path.join(OUTPUT_DIR, "excel_delivery_thumbs")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(IMG_FINAL_DIR, exist_ok=True)
os.makedirs(THUMBS_DIR, exist_ok=True)

# -------------------------------------------------------------
# 1. Load Categories & Online Mapping
# -------------------------------------------------------------
cat_file = os.path.join(SOURCE_DIR, "Ma_nhom_hang_SKU_3digits.xlsx")
wb_cat = openpyxl.load_workbook(cat_file, data_only=True)
ws_cat = wb_cat.active
nhom_map = {}
for r in list(ws_cat.iter_rows(values_only=True))[4:]:
    if r[1]:
        dansk_name = str(r[1]).strip()
        nhom_map[dansk_name] = {
            "code": str(r[2]).strip() if r[2] else "",
            "vi": str(r[3]).strip() if r[3] else "",
            "example_sku": str(r[4]).strip() if r[4] else "",
            "online_col": str(r[5]).strip() if r[5] else "",
            "is_online": str(r[5]).strip().lower() != "nej",
        }

print(f"1. Loaded {len(nhom_map)} categories from Ma_nhom_hang_SKU_3digits.xlsx")

# -------------------------------------------------------------
# 2. Load POS Active File
# -------------------------------------------------------------
pos_file = os.path.join(SOURCE_DIR, "27.09.26.POS_ACTIVE_FINAL.xlsx")
wb_pos = openpyxl.load_workbook(pos_file, data_only=True)
ws_pos = wb_pos.active
pos_rows = list(ws_pos.iter_rows(values_only=True))[1:]

def clean_bc(v):
    s = str(v or "").strip()
    if s.endswith(".0"):
        s = s[:-2]
    return re.sub(r"[^\w]", "", s)

pos_by_bc = {}
pos_by_clean_bc = {}
for r in pos_rows:
    raw_bc = str(r[7] or "").strip()
    c_bc = clean_bc(raw_bc)
    item_info = {
        "pos_category": str(r[0] or "").strip(),
        "product_name": str(r[1] or "").strip(),
        "official_name": str(r[2] or "").strip(),
        "printer_name": str(r[3] or "").strip(),
        "purchase_price": r[4],
        "selling_price": r[5],
        "unit": r[6],
        "raw_barcode": raw_bc,
        "clean_barcode": c_bc,
        "sku": str(r[8] or "").strip(),
        "product_id": str(r[9] or "").strip(),
        "tax_group": r[10],
    }
    if c_bc:
        pos_by_bc[c_bc] = item_info
        pos_by_clean_bc[c_bc.lstrip("0")] = item_info

print(f"2. Loaded {len(pos_rows)} POS items ({len(pos_by_bc)} with valid barcodes)")

# -------------------------------------------------------------
# 3. Load Product Master (89 columns)
# -------------------------------------------------------------
pm_file = [f for f in os.listdir(SOURCE_DIR) if f.startswith("Product_master") and f.endswith(".xlsx") and not f.startswith("~$")][0]
pm_path = os.path.join(SOURCE_DIR, pm_file)
wb_pm = openpyxl.load_workbook(pm_path, read_only=True, data_only=True)
ws_pm = wb_pm.active
pm_all_rows = list(ws_pm.iter_rows(values_only=True))

pm_title_row1 = pm_all_rows[1]
pm_title_row2 = pm_all_rows[2]
pm_title_row3 = pm_all_rows[3]
pm_headers = [str(c).strip() if c is not None else f"col_{i}" for i, c in enumerate(pm_all_rows[4])]
pm_data_rows = pm_all_rows[5:]

print(f"3. Loaded {len(pm_data_rows)} Product Master items with {len(pm_headers)} columns")

# -------------------------------------------------------------
# 4. Build Comprehensive Image Cache
# -------------------------------------------------------------
image_sources = [
    os.path.join(OUTPUT_DIR, "product_images"),
    os.path.join(OUTPUT_DIR, "excel_delivery_thumbs"),
    os.path.join(OUTPUT_DIR, "excel_thumbnails"),
    os.path.join(BASE_DIR, r"output\shopify_import\image_product"),
    os.path.join(BASE_DIR, r"web\public\products\front"),
    os.path.join(BASE_DIR, r"output\shopify_import\front_images_jpg"),
    os.path.join(BASE_DIR, r"output\shopify_import\web_front_images"),
    os.path.join(BASE_DIR, r"output\shopify_import\images"),
    os.path.join(BASE_DIR, r"output\g1_delivery\website_front_images"),
    os.path.join(BASE_DIR, r"G1_original"),
    os.path.join(BASE_DIR, r"source-import\G2_original"),
    os.path.join(BASE_DIR, r"source-import\G3_Original"),
    os.path.join(BASE_DIR, r"source-import\Nyt25.09.26"),
    os.path.join(BASE_DIR, r"output\shopify_import\original_photos"),
]

img_by_stem = {}
img_by_filename = {}
all_img_files = []

for s in image_sources:
    if os.path.exists(s):
        for root, dirs, files in os.walk(s):
            for f in files:
                if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                    stem = Path(f).stem
                    full_p = os.path.join(root, f)
                    all_img_files.append((f, full_p))
                    if stem not in img_by_stem:
                        img_by_stem[stem] = full_p
                    if stem.lstrip("0") not in img_by_stem:
                        img_by_stem[stem.lstrip("0")] = full_p
                    if f.lower() not in img_by_filename:
                        img_by_filename[f.lower()] = full_p

def get_or_create_thumb(img_path, target_stem):
    if not img_path or not os.path.exists(img_path):
        return None
    thumb_p = os.path.join(THUMBS_DIR, f"{target_stem}.jpg")
    if os.path.exists(thumb_p):
        return thumb_p
    try:
        with PILImage.open(img_path) as pimg:
            pimg = pimg.convert("RGB")
            pimg.thumbnail((150, 150), PILImage.Resampling.LANCZOS)
            pimg.save(thumb_p, "JPEG", quality=90)
            return thumb_p
    except Exception:
        return None

def find_image_for_pm(r):
    bc = clean_bc(r[0])
    rec_id = str(r[4] or "").strip()
    sel_front = str(r[65] or "").strip()
    rel_fn = str(r[67] or "").strip()
    src_photos = str(r[64] or "").strip()

    # 1. Barcode
    if bc:
        if bc in img_by_stem: return img_by_stem[bc]
        if bc.lstrip("0") in img_by_stem: return img_by_stem[bc.lstrip("0")]

    # 2. Record ID
    if rec_id and rec_id in img_by_stem:
        return img_by_stem[rec_id]

    # 3. Selected Front
    if sel_front:
        f_stem = Path(sel_front).stem
        if f_stem in img_by_stem: return img_by_stem[f_stem]
        if sel_front.lower() in img_by_filename: return img_by_filename[sel_front.lower()]
        for fn, fp in all_img_files:
            if f_stem.lower() in fn.lower(): return fp

    # 4. Relative filename
    if rel_fn:
        r_stem = Path(rel_fn).stem
        if r_stem in img_by_stem: return img_by_stem[r_stem]
        if rel_fn.lower() in img_by_filename: return img_by_filename[rel_fn.lower()]
        for fn, fp in all_img_files:
            if r_stem.lower() in fn.lower(): return fp

    # 5. Source photos
    if src_photos:
        for p in src_photos.replace(";", ",").split(","):
            p = p.strip()
            if not p: continue
            p_stem = Path(p).stem
            if p_stem in img_by_stem: return img_by_stem[p_stem]
            for fn, fp in all_img_files:
                if p_stem.lower() in fn.lower(): return fp

    return None

# -------------------------------------------------------------
# 5. Generate Master Rows (89 columns + Merge POS & Online status)
# -------------------------------------------------------------
# Columns in PM headers:
# 0: Barcode, 1: Full name (EN), 2: Fuldt navn (DA), 3: Brand, 4: Record ID
# ...
# 75: Ảnh mặt trước (Col 76)
# ...
# 84: Category Name (Col 85)
# 85: Price (Col 86)
# 86: SKU Code (Col 87)
# 87: Product ID (Col 88)
# 88: Update status (Col 89)

# Additional columns to make the delivery 100% crystal clear:
# Add [Ảnh sản phẩm (Thumbnail)] as Column 2 (Right after Barcode)
# Add [Online Status], [Online Category], [Group Code] right after Product ID

delivery_headers = list(pm_headers)
# Insert Image Thumbnail column at Column 2 (Index 1) for best viewing
delivery_headers.insert(1, "Ảnh sản phẩm (Image)")
# Append Online Classification at end
delivery_headers.extend(["Online Status", "Online Category", "Group Code"])

master_online_records = []
master_all_records = []
shopify_export_records = []

def slugify(text):
    text = str(text or "").strip()
    text = text.replace("æ", "ae").replace("Æ", "ae")
    text = text.replace("ø", "oe").replace("Ø", "oe")
    text = text.replace("å", "aa").replace("Å", "aa")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[-\s]+", "-", text).strip("-")
    return text

CATEGORY_TAXONOMY_MAP = {
    "Saucer": ("Food, Beverages & Tobacco > Food Items > Saucer & Sojasauce", "Saucer & Sojasauce"),
    "Nudler": ("Food, Beverages & Tobacco > Food Items > Nudler, Ris & Tørvarer", "Nudler"),
    "Snack": ("Food, Beverages & Tobacco > Food Items > Snack & Slik", "Snack"),
    "Krydderier": ("Food, Beverages & Tobacco > Food Items > Krydderier & Karry", "Krydderier & Karry"),
    "Konserves": ("Food, Beverages & Tobacco > Food Items > Konserves & Kokosmælk", "Konserves & Kokosmælk"),
    "Grøntsager": ("Food, Beverages & Tobacco > Food Items > Grøntsager & Frugt", "Grøntsager"),
    "Drikkevarer": ("Food, Beverages & Tobacco > Food Items > Drikkevarer & Vin", "Drikkevarer & Drikker"),
    "Mel": ("Food, Beverages & Tobacco > Food Items > Mel & Bageartikler", "Mel & Bageartikler"),
    "Frugt": ("Food, Beverages & Tobacco > Food Items > Frugt & Konserves", "Frugt"),
    "Diverse": ("Food, Beverages & Tobacco > Food Items > Asiatiske Specialiteter", "Diverse"),
    "Bønner": ("Food, Beverages & Tobacco > Food Items > Bønner & Tørvarer", "Bønner"),
    "Mælk": ("Food, Beverages & Tobacco > Food Items > Mælk & Drikkevarer", "Mælk"),
}

def safe_str(v):
    if v is None: return ""
    s = str(v).strip()
    return "" if s.lower() in {"none", "nan", "null"} else s

def build_html_body(pm_dict, selling_price):
    brand = safe_str(pm_dict.get("Brand"))
    net_w = safe_str(pm_dict.get("Net quantity"))
    net_u = safe_str(pm_dict.get("Net unit") or "g")
    w_str = f"{net_w} {net_u}".strip() if net_w else ""
    origin = safe_str(pm_dict.get("Country of origin"))

    parts = []
    meta = []
    if brand: meta.append(f"Mærke: {brand}")
    if w_str: meta.append(f"Nettoindhold: {w_str}")
    if origin: meta.append(f"Oprindelsesland: {origin}")
    if meta: parts.append(f"<p>{' · '.join(meta)}</p>")

    ing_da = safe_str(pm_dict.get("Ingredienser (DA)"))
    ing_en = safe_str(pm_dict.get("Ingredients (EN)"))
    ing = ing_da or ing_en
    if ing: parts.append(f"<h3>Ingredienser</h3><p>{ing}</p>")

    all_da = safe_str(pm_dict.get("Allergener (DA)"))
    all_en = safe_str(pm_dict.get("Allergens (EN)"))
    allg = all_da or all_en
    if allg: parts.append(f"<h3>Allergener</h3><p>{allg}</p>")

    has_nutrition = any(
        pm_dict.get(k) is not None and str(pm_dict.get(k)).strip() != ""
        for k in ["Energy (kJ)", "Energy (kcal)", "Fat (g)", "Carbohydrate (g)", "Protein (g)", "Salt (g)"]
    )
    if has_nutrition:
        basis = safe_str(pm_dict.get("Nutrition basis / preparation state")) or "pr. 100 g"
        if not basis.startswith("pr.") and not basis.startswith("per"):
            basis = f"pr. {basis}"
        rows = []
        ekj = pm_dict.get("Energy (kJ)")
        ekcal = pm_dict.get("Energy (kcal)")
        if ekj or ekcal:
            e_str = []
            if ekj and str(ekj).strip(): e_str.append(f"{ekj} kJ")
            if ekcal and str(ekcal).strip(): e_str.append(f"{ekcal} kcal")
            if e_str: rows.append(f"<tr><td>Energi</td><td>{' / '.join(e_str)}</td></tr>")
        if pm_dict.get("Fat (g)"): rows.append(f"<tr><td>Fedt</td><td>{pm_dict.get('Fat (g)')} g</td></tr>")
        if pm_dict.get("Saturates (g)"): rows.append(f"<tr><td>&nbsp;&nbsp;heraf mættede fedtsyrer</td><td>{pm_dict.get('Saturates (g)')} g</td></tr>")
        if pm_dict.get("Carbohydrate (g)"): rows.append(f"<tr><td>Kulhydrat</td><td>{pm_dict.get('Carbohydrate (g)')} g</td></tr>")
        if pm_dict.get("Sugars (g)"): rows.append(f"<tr><td>&nbsp;&nbsp;heraf sukkerarter</td><td>{pm_dict.get('Sugars (g)')} g</td></tr>")
        if pm_dict.get("Protein (g)"): rows.append(f"<tr><td>Protein</td><td>{pm_dict.get('Protein (g)')} g</td></tr>")
        if pm_dict.get("Salt (g)"): rows.append(f"<tr><td>Salt</td><td>{pm_dict.get('Salt (g)')} g</td></tr>")
        if rows:
            parts.append(f"<h3>Næringsindhold {basis}</h3><table>\n" + "\n".join(rows) + "\n</table>")

    prep_da = safe_str(pm_dict.get("Tilberedning (DA)") or pm_dict.get("Preparation (EN)"))
    if prep_da: parts.append(f"<h3>Tilberedning</h3><p>{prep_da}</p>")

    opb_da = safe_str(pm_dict.get("Opbevaring (DA)") or pm_dict.get("Storage (EN)") or "Opbevares tørt og køligt.")
    parts.append(f"<h3>Opbevaring</h3><p>{opb_da}</p>")

    return "".join(parts)

seen_handles = set()
pm_with_img_count = 0
pm_missing_img_list = []

for r in pm_data_rows:
    row_dict = {pm_headers[i]: r[i] for i in range(min(len(pm_headers), len(r)))}
    raw_bc = str(r[0] or "").strip()
    c_bc = clean_bc(raw_bc)
    
    # Merge POS Data
    pos_item = pos_by_bc.get(c_bc) or pos_by_clean_bc.get(c_bc.lstrip("0")) or {}
    
    pos_cat = pos_item.get("pos_category") or str(row_dict.get("Category Name") or "").strip()
    selling_p = pos_item.get("selling_price") if pos_item.get("selling_price") is not None else row_dict.get("Price")
    sku_val = pos_item.get("sku") or row_dict.get("SKU Code") or ""
    prod_id = pos_item.get("product_id") or row_dict.get("Product ID") or ""
    
    # Category rules
    cat_rule = nhom_map.get(pos_cat, {})
    is_online = cat_rule.get("is_online", True) if pos_cat else True
    # If Category is explicitly Nej in nhom_map -> False
    if pos_cat in nhom_map and not nhom_map[pos_cat]["is_online"]:
        is_online = False
        
    online_group_name = cat_rule.get("online_col", pos_cat)
    group_code = cat_rule.get("code", "")
    
    # Find Image
    img_path = find_image_for_pm(r)
    thumb_path = None
    img_filename = f"{c_bc}.jpg" if c_bc else f"{row_dict.get('Record ID')}.jpg"
    
    if img_path:
        pm_with_img_count += 1
        # copy to product_images
        dest_img = os.path.join(IMG_FINAL_DIR, img_filename)
        if not os.path.exists(dest_img) and os.path.exists(img_path):
            try:
                shutil.copy2(img_path, dest_img)
            except Exception: pass
        thumb_path = get_or_create_thumb(img_path, Path(img_filename).stem)
    else:
        pm_missing_img_list.append((raw_bc, row_dict.get("Record ID"), row_dict.get("Full name (EN)")))

    # Update PM dictionary with merged POS & Images
    row_dict["Category Name"] = pos_cat
    row_dict["Price"] = selling_p
    row_dict["SKU Code"] = sku_val
    row_dict["Product ID"] = prod_id
    row_dict["Update status"] = "Đã khớp POS & Master 100%" if pos_item else "Trong Master (Chưa có POS)"
    row_dict["Ảnh mặt trước"] = img_filename if img_path else ""
    
    # Build complete delivery row
    row_vals = []
    for h in pm_headers:
        row_vals.append(row_dict.get(h, ""))
        
    # Insert Thumbnail at Col 2
    row_vals.insert(1, None)
    
    # Append online status cols
    row_vals.append("Online (Duyệt web)" if is_online else "Offline (Nej / Tại quầy)")
    row_vals.append(online_group_name)
    row_vals.append(group_code)
    
    row_meta = {
        "values": row_vals,
        "thumb_path": thumb_path,
        "barcode": c_bc,
        "sku": sku_val,
        "is_online": is_online,
        "title_da": safe_str(row_dict.get("Fuldt navn (DA)")),
        "title_en": safe_str(row_dict.get("Full name (EN)")),
        "brand": safe_str(row_dict.get("Brand")) or "Asiatisk",
        "origin": safe_str(row_dict.get("Country of origin")) or "Asien",
        "net_qty": row_dict.get("Net quantity"),
        "net_unit": row_dict.get("Net unit") or "g",
        "pos_cat": pos_cat,
        "selling_p": selling_p,
        "dict": row_dict,
    }
    
    master_all_records.append(row_meta)
    if is_online:
        master_online_records.append(row_meta)
        
        # Shopify CSV row
        cat_tax, p_type = CATEGORY_TAXONOMY_MAP.get(
            pos_cat,
            ("Food, Beverages & Tobacco > Food Items > Asiatiske Specialiteter", pos_cat or "Diverse")
        )
        title = row_meta["title_da"] or row_meta["title_en"] or "Asiatisk produkt"
        handle = slugify(title)
        if not handle: handle = f"produkt-{c_bc}" if c_bc else f"sku-{sku_val.lower()}"
        
        # Ensure unique handle
        orig_handle = handle
        counter = 1
        while handle in seen_handles:
            counter += 1
            suffix = f"-{sku_val.lower()}" if sku_val and f"-{sku_val.lower()}" not in handle else f"-{counter}"
            handle = f"{orig_handle}{suffix}"
        seen_handles.add(handle)
        
        body_html = build_html_body(row_dict, selling_p)
        tags = f"{p_type}, {row_meta['brand']}, {row_meta['origin']}, online_import_2026"
        img_src = f"https://rabuta.dk/cdn/shop/files/{c_bc}.jpg" if c_bc else ""
        
        shopify_dict = {
            "Handle": handle,
            "Title": title,
            "Body (HTML)": body_html,
            "Vendor": row_meta["brand"],
            "Product Category": cat_tax,
            "Type": p_type,
            "Tags": tags,
            "Published": "TRUE",
            "Option1 Name": "Title",
            "Option1 Value": "Default Title",
            "Variant SKU": sku_val,
            "Variant Grams": int(float(row_meta["net_qty"])) if row_meta["net_qty"] and str(row_meta["net_qty"]).replace(".", "", 1).isdigit() else 100,
            "Variant Inventory Tracker": "shopify",
            "Variant Inventory Qty": 100,
            "Variant Inventory Policy": "deny",
            "Variant Fulfillment Service": "manual",
            "Variant Price": selling_p if selling_p is not None else 25,
            "Variant Compare At Price": "",
            "Variant Requires Shipping": "TRUE",
            "Variant Taxable": "TRUE",
            "Variant Barcode": c_bc,
            "Image Src": img_src,
            "Image Position": 1,
            "Image Alt Text": title,
            "Gift Card": "FALSE",
            "SEO Title": title,
            "SEO Description": f"Køb {title} online hos Rabuta.dk. Hurtig levering i hele Danmark.",
            "Status": "active",
        }
        shopify_export_records.append(shopify_dict)

print(f"Master rows generated: {len(master_all_records)} total, {len(master_online_records)} online")
print(f"Images verified: {pm_with_img_count} / {len(pm_data_rows)} (Missing: {len(pm_missing_img_list)})")

# -------------------------------------------------------------
# 6. Excel Export Engine with Embedded Images
# -------------------------------------------------------------
HEADER_FILL = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
REGULAR_FONT = Font(name="Calibri", size=10)
BORDER_THIN = Side(border_style="thin", color="D9D9D9")
CELL_BORDER = Border(left=BORDER_THIN, right=BORDER_THIN, top=BORDER_THIN, bottom=BORDER_THIN)

def export_excel_with_images(records, file_path, sheet_title, embed_images=True):
    print(f"\nExporting {os.path.basename(file_path)}...")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title
    ws.views.sheetView[0].showGridLines = True
    
    # Headers
    ws.append(delivery_headers)
    ws.row_dimensions[1].height = 28
    for col_num in range(1, len(delivery_headers) + 1):
        cell = ws.cell(1, col_num)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        
    img_col_idx = 2 # Column B: 'Ảnh sản phẩm (Image)'
    img_col_letter = get_column_letter(img_col_idx)
    ws.column_dimensions[img_col_letter].width = 22.0
    
    embedded_images_count = 0
    missing_images_in_file = []
    
    for r_idx, item in enumerate(records, start=2):
        ws.append(item["values"])
        ws.row_dimensions[r_idx].height = 100.0 if embed_images else 20.0
        
        for c_idx in range(1, len(delivery_headers) + 1):
            c = ws.cell(r_idx, c_idx)
            c.font = REGULAR_FONT
            c.border = CELL_BORDER
            c.alignment = Alignment(vertical="center")
            
        # Center Barcode, Image, SKU, Price, ID
        ws.cell(r_idx, 1).alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(r_idx, img_col_idx).alignment = Alignment(horizontal="center", vertical="center")
        
        # Embed Image
        if embed_images:
            thumb_p = item["thumb_path"]
            if thumb_p and os.path.exists(thumb_p):
                try:
                    with PILImage.open(thumb_p) as pimg:
                        pw, ph = pimg.size
                    scale = min(120.0 / pw, 120.0 / ph)
                    tw = max(30, int(pw * scale))
                    th = max(30, int(ph * scale))
                    
                    xl_img = OpenpyxlImage(thumb_p)
                    xl_img.width = tw
                    xl_img.height = th
                    xl_img.anchor = f"{img_col_letter}{r_idx}"
                    ws.add_image(xl_img)
                    embedded_images_count += 1
                except Exception:
                    missing_images_in_file.append((r_idx, item["barcode"], item["sku"], item["title_da"]))
            else:
                missing_images_in_file.append((r_idx, item["barcode"], item["sku"], item["title_da"]))

    # Auto-adjust column widths
    for col_idx, col_name in enumerate(delivery_headers, start=1):
        if col_idx == img_col_idx:
            continue
        col_letter = get_column_letter(col_idx)
        max_len = len(str(col_name))
        for r in range(2, min(len(records) + 2, 40)):
            v = ws.cell(r, col_idx).value
            if v: max_len = max(max_len, min(len(str(v)), 40))
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)
        
    try:
        wb.save(file_path)
        print(f"Saved: {file_path} ({len(records)} rows, {embedded_images_count} embedded images)")
    except PermissionError:
        base, ext = os.path.splitext(file_path)
        fallback = f"{base}_v2{ext}"
        wb.save(fallback)
        print(f"File locked by Excel, saved fallback: {fallback} ({len(records)} rows, {embedded_images_count} embedded images)")

    return embedded_images_count, missing_images_in_file

# -------------------------------------------------------------
# 7. Execute Exports
# -------------------------------------------------------------
# 1. Master Online Delivery With Images (1,091 products, 89+ columns)
f_master_online_img = os.path.join(OUTPUT_DIR, "Master_Online_Delivery_With_Images.xlsx")
emb_online, miss_online = export_excel_with_images(master_online_records, f_master_online_img, "Online Products Master", embed_images=True)

# 2. Master Online Products Consolidated (Text / data)
f_master_online_text = os.path.join(OUTPUT_DIR, "Master_Online_Products_Consolidated.xlsx")
export_excel_with_images(master_online_records, f_master_online_text, "Online Products Master", embed_images=False)

# 3. All Master Delivery With Images (1,351 products, 89+ columns)
f_master_all_img = os.path.join(OUTPUT_DIR, "Master_All_Products_89cols_With_Images.xlsx")
emb_all, miss_all = export_excel_with_images(master_all_records, f_master_all_img, "All Products Master", embed_images=True)

# 4. Export Shopify CSV
f_shopify_csv = os.path.join(OUTPUT_DIR, "Shopify_Import_Online_Products.csv")
with open(f_shopify_csv, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(shopify_export_records[0].keys()))
    w.writeheader()
    w.writerows(shopify_export_records)
print(f"Exported Shopify CSV: {f_shopify_csv} ({len(shopify_export_records)} products)")

print("\n=== PIPELINE EXECUTION SUMMARY ===")
print(f"Total Master items processed: {len(master_all_records)}")
print(f"Online Master items (approved): {len(master_online_records)}")
print(f"Online embedded images: {emb_online} / {len(master_online_records)}")
print(f"All Master embedded images: {emb_all} / {len(master_all_records)}")
if miss_online:
    print(f"Missing images in Online delivery: {len(miss_online)}")
    for m in miss_online: print("  Online missing:", m)
if miss_all:
    print(f"Missing images in All delivery: {len(miss_all)}")
    for m in miss_all: print("  All missing:", m)
