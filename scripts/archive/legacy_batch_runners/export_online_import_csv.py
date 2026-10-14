import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import openpyxl
import pandas as pd
import csv
import re

def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[æ]', 'ae', text)
    text = re.sub(r'[ø]', 'oe', text)
    text = re.sub(r'[å]', 'aa', text)
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return text

def build_nutrition_table(r) -> str:
    # Nutrition fields: 41: basis, 42: energy_kj, 43: energy_kcal, 44: fat, 45: sat_fat, 46: carbs, 47: sugar, 48: fiber, 49: protein, 50: salt
    energy_kj = r[41]
    energy_kcal = r[42]
    fat = r[43]
    sat_fat = r[44]
    carbs = r[45]
    sugar = r[46]
    protein = r[48]
    salt = r[49]

    has_nutrition = any([energy_kj, energy_kcal, fat, carbs, protein, salt])
    if not has_nutrition:
        return ""

    rows_html = []
    if energy_kj or energy_kcal:
        val = f"{energy_kj} kJ / {energy_kcal} kcal" if energy_kj and energy_kcal else f"{energy_kcal} kcal" if energy_kcal else f"{energy_kj} kJ"
        rows_html.append(f'<tr><td style="border:1px solid #ddd; padding:4px;">Energi</td><td style="border:1px solid #ddd; padding:4px;">{val}</td></tr>')
    if fat is not None:
        rows_html.append(f'<tr><td style="border:1px solid #ddd; padding:4px;">Fedt</td><td style="border:1px solid #ddd; padding:4px;">{fat} g</td></tr>')
    if sat_fat is not None:
        rows_html.append(f'<tr><td style="border:1px solid #ddd; padding:4px; padding-left:15px;">- heraf mættede fedtsyrer</td><td style="border:1px solid #ddd; padding:4px;">{sat_fat} g</td></tr>')
    if carbs is not None:
        rows_html.append(f'<tr><td style="border:1px solid #ddd; padding:4px;">Kulhydrat</td><td style="border:1px solid #ddd; padding:4px;">{carbs} g</td></tr>')
    if sugar is not None:
        rows_html.append(f'<tr><td style="border:1px solid #ddd; padding:4px; padding-left:15px;">- heraf sukkerarter</td><td style="border:1px solid #ddd; padding:4px;">{sugar} g</td></tr>')
    if protein is not None:
        rows_html.append(f'<tr><td style="border:1px solid #ddd; padding:4px;">Protein</td><td style="border:1px solid #ddd; padding:4px;">{protein} g</td></tr>')
    if salt is not None:
        rows_html.append(f'<tr><td style="border:1px solid #ddd; padding:4px;">Salt</td><td style="border:1px solid #ddd; padding:4px;">{salt} g</td></tr>')

    if not rows_html:
        return ""

    table_html = (
        '<table class="nutrition-table" style="width:100%; border-collapse:collapse; margin-top:10px;">'
        '<thead><tr style="background:#f4f4f4;"><th style="border:1px solid #ddd; padding:6px;">Næringsdeklaration</th>'
        '<th style="border:1px solid #ddd; padding:6px;">pr. 100g</th></tr></thead>'
        f'<tbody>{"".join(rows_html)}</tbody></table>'
    )
    return table_html

def build_body_html(r) -> str:
    ing = str(r[34] or "").strip() # Ingredienser (DA)
    allg = str(r[38] or "").strip() # Allergener (DA)
    stor = str(r[56] or "").strip() # Opbevaring (DA)
    prep = str(r[53] or "").strip() # Tilberedning (DA)
    
    parts = ['<div class="product-description">']
    if ing:
        parts.append(f'<p><strong>Ingredienser:</strong> {ing}</p>')
    if allg:
        parts.append(f'<p><strong>Allergener:</strong> {allg}</p>')
    if stor:
        parts.append(f'<p><strong>Opbevaring:</strong> {stor}</p>')
    if prep:
        parts.append(f'<p><strong>Tilberedning:</strong> {prep}</p>')
    
    nut_table = build_nutrition_table(r)
    if nut_table:
        parts.append(nut_table)
        
    parts.append('</div>')
    return "".join(parts)

def export_online_import_csv():
    clean_master_path = "output/reconciliation/Master_1659_Reconciled_Clean.xlsx"
    out_csv = "output/shopify_import_final/Shopify_Import_Online_Products_v2.csv"
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)

    print(f"[*] Reading Clean Master: {clean_master_path}")
    wb = openpyxl.load_workbook(clean_master_path, data_only=True)
    sheet = wb.active
    rows = list(sheet.iter_rows(values_only=True))[3:] # skip header rows

    # Columns index mapping (0-based)
    c_stt = 0
    c_bc = 2
    c_en = 3
    c_da = 4
    c_brand = 5
    c_origin = 27
    c_qty = 15
    c_cat_pos = 86
    c_price = 87
    c_sku = 88
    c_online = 91
    c_code3 = 92
    c_img_cdn = 93
    c_l1 = 96
    c_l2 = 97

    online_records = []
    offline_records = []

    for r in rows:
        online_status = str(r[c_online] or "").strip()
        is_online = (online_status == "Online")

        barcode = str(r[c_bc] or "").strip()
        title_da = str(r[c_da] or "").strip() or str(r[c_en] or "").strip() or f"Specialty Product {r[c_sku]}"
        brand = str(r[c_brand] or "").strip()
        origin = str(r[c_origin] or "").strip()
        l1 = str(r[c_l1] or "").strip() or "Diverse"
        l2 = str(r[c_l2] or "").strip() or f"Other {l1}"
        sku = str(r[c_sku] or "").strip()
        code3 = str(r[c_code3] or "").strip()
        price = r[c_price] if r[c_price] is not None else 25

        # Handle
        handle_base = slugify(title_da)
        if barcode:
            handle = f"{handle_base}-{barcode}"
        else:
            handle = f"{handle_base}-{sku}" if sku else handle_base

        # Weight in grams
        raw_qty = r[c_qty]
        grams = 500
        if raw_qty:
            try:
                grams = int(float(raw_qty))
            except Exception:
                grams = 500

        # Tags
        tags_list = [l1, f"subcat:{l2}"]
        if code3 and code3 != l1:
            tags_list.append(code3)
        if brand:
            tags_list.append(brand)
        if origin:
            tags_list.append(origin)
        tags_list.append("online_import_2026")
        tags_str = ", ".join(dict.fromkeys(tags_list)) # deduplicate preserving order

        # Image Src
        img_src = f"https://rabuta.dk/cdn/shop/files/{barcode}.jpg" if barcode else ""

        body_html = build_body_html(r)

        record = {
            "Handle": handle,
            "Title": title_da,
            "Body (HTML)": body_html,
            "Vendor": brand,
            "Product Category": f"Food, Beverages & Tobacco > Food Items > {l1}",
            "Type": l1,
            "Tags": tags_str,
            "Published": "True",
            "Option1 Name": "Title",
            "Option1 Value": "Default Title",
            "Variant SKU": sku,
            "Variant Grams": grams,
            "Variant Inventory Tracker": "shopify",
            "Variant Inventory Qty": 100,
            "Variant Inventory Policy": "deny",
            "Variant Fulfillment Service": "manual",
            "Variant Price": price,
            "Variant Compare At Price": "",
            "Variant Requires Shipping": "True",
            "Variant Taxable": "True",
            "Variant Barcode": barcode,
            "Image Src": img_src,
            "Image Position": 1,
            "Image Alt Text": title_da,
            "Gift Card": "False",
            "SEO Title": f"{title_da} | Rabuta Asian Supermarket",
            "SEO Description": f"Køb {title_da} online hos Rabuta.dk. Hurtig levering i hele Danmark.",
            "Status": "active"
        }

        if is_online:
            online_records.append(record)
        else:
            offline_records.append(record)

    print(f"[+] Total Online records: {len(online_records)}")
    print(f"[+] Total Offline records: {len(offline_records)}")

    # Write to CSV
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(online_records[0].keys()))
        writer.writeheader()
        writer.writerows(online_records)

    print(f"[+] Successfully exported {len(online_records)} online products to: {out_csv}")

    # Also update canonical Shopify_Import_Online_Products.csv to keep all tools compatible
    canonical_csv = "output/shopify_import_final/Shopify_Import_Online_Products.csv"
    with open(canonical_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(online_records[0].keys()))
        writer.writeheader()
        writer.writerows(online_records)
    print(f"[+] Updated canonical import CSV: {canonical_csv}")

if __name__ == "__main__":
    export_online_import_csv()
