import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import openpyxl
import json
from collections import Counter

def update_web_portal():
    clean_master = "output/reconciliation/Master_1659_Reconciled_Clean.xlsx"
    out_json = "web/public/data/products.json"
    os.makedirs(os.path.dirname(out_json), exist_ok=True)

    print(f"[*] Reading Clean Master: {clean_master}")
    wb = openpyxl.load_workbook(clean_master, data_only=True)
    sheet = wb.active
    rows = list(sheet.iter_rows(values_only=True))[3:]

    # Indices
    c_stt = 0
    c_bc = 2
    c_en = 3
    c_da = 4
    c_brand = 5
    c_rec_id = 6
    c_status = 7
    c_name_notes = 11
    c_variant = 12
    c_pkg = 14
    c_qty = 15
    c_unit = 16
    c_origin = 27
    c_ing_da = 34
    c_allg_da = 38
    c_stor_da = 56
    c_prep_da = 53
    c_raw_front = 67
    c_sku = 88
    c_online = 91
    c_code3 = 92
    c_img_cdn = 93
    c_l1 = 96
    c_l2 = 97

    products = []
    l1_counts = Counter()
    l2_counts = Counter()
    online_count = 0

    for r in rows:
        stt = r[c_stt]
        bc = str(r[c_bc] or "").strip()
        name_en = str(r[c_en] or "").strip()
        name_da = str(r[c_da] or "").strip() or name_en
        brand = str(r[c_brand] or "").strip()
        rec_id = str(r[c_rec_id] or f"REC-{stt}").strip()
        sku = str(r[c_sku] or "").strip()
        online_status = str(r[c_online] or "Online").strip()
        l1 = str(r[c_l1] or "Diverse").strip()
        l2 = str(r[c_l2] or f"Other {l1}").strip()
        origin = str(r[c_origin] or "").strip()
        raw_source = str(r[c_raw_front] or "").strip()

        if online_status == "Online":
            online_count += 1
        l1_counts[l1] += 1
        l2_counts[l2] += 1

        cdn_url = f"https://rabuta.dk/cdn/shop/files/{bc}.jpg" if bc else ""
        web_local_img = f"/products/{bc}.jpg" if bc else ""

        prod_item = {
            "stt": stt,
            "barcode": bc,
            "product_name": name_da,
            "full_name_en": name_en,
            "fuldt_navn_da": name_da,
            "brand": brand,
            "record_id": rec_id,
            "pos_sku": sku,
            "pos_product_name": name_da,
            "category": l1,
            "category_level_1": l1,
            "category_level_2": l2,
            "online_status": online_status,
            "country_of_origin": origin,
            "ingredienser_da": str(r[c_ing_da] or "").strip(),
            "allergener_da": str(r[c_allg_da] or "").strip(),
            "opbevaring_da": str(r[c_stor_da] or "").strip(),
            "tilberedning_da": str(r[c_prep_da] or "").strip(),
            "original_image": raw_source,
            "website_front_image": web_local_img or cdn_url,
            "front_web_url": cdn_url,
            "raw_web_url": raw_source,
            "status": "CONFIRMED" if bc else "MANUAL_REVIEW"
        }
        products.append(prod_item)

    all_brands = sorted(list({p["brand"] for p in products if p["brand"]}))

    payload = {
        "stats": {
            "total": len(products),
            "confirmed": sum(1 for p in products if p["status"] == "CONFIRMED"),
            "pos_matched": sum(1 for p in products if p["pos_sku"]),
            "review_needed": sum(1 for p in products if p["status"] != "CONFIRMED"),
            "brands_count": len(all_brands),
            "online_count": online_count,
            "offline_count": len(products) - online_count
        },
        "brands": all_brands,
        "categories_level_1": sorted(list(l1_counts.keys())),
        "categories_level_2": sorted(list(l2_counts.keys())),
        "products": products
    }

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[+] Successfully wrote {len(products)} products to: {out_json}")
    print(f"    - Online products: {online_count}")
    print(f"    - Level 1 categories: {len(l1_counts)}")
    print(f"    - Level 2 categories: {len(l2_counts)}")

if __name__ == "__main__":
    update_web_portal()
