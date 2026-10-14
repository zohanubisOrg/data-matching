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
import json
import time
import base64
import urllib.request
import urllib.parse
import urllib.error

ENV_PATH = ".env"
def load_env(env_path=".env"):
    config = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip()
    return config

ENV = load_env(ENV_PATH)
STORE_DOMAIN = ENV.get("SHOPIFY_STORE_DOMAIN", "rabuta.myshopify.com")
CLIENT_ID = ENV.get("SHOPIFY_CLIENT_ID", "")
CLIENT_SECRET = ENV.get("SHOPIFY_CLIENT_SECRET", "")
ACCESS_TOKEN = ENV.get("SHOPIFY_ADMIN_ACCESS_TOKEN", "")

SOURCE_EXCEL = "output/Esbjerg_Asian_Market_Da_Loc_Cap_Nhat_Anh_Moi.xlsx"
IMAGE_DIR = "output/barcode_hd_images_updated"
OUT_CSV = "output/shopify_import_final/Shopify_Import_Online_Products.csv"

def get_valid_token():
    global ACCESS_TOKEN
    if ACCESS_TOKEN:
        try:
            req = urllib.request.Request(f"https://{STORE_DOMAIN}/admin/api/2026-10/shop.json")
            req.add_header("X-Shopify-Access-Token", ACCESS_TOKEN)
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    return ACCESS_TOKEN
        except Exception:
            pass

    url = f"https://{STORE_DOMAIN}/admin/oauth/access_token"
    data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials"
    }).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=15) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        ACCESS_TOKEN = res["access_token"]
        return ACCESS_TOKEN

def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[æ]', 'ae', text)
    text = re.sub(r'[ø]', 'oe', text)
    text = re.sub(r'[å]', 'aa', text)
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return text

def build_nutrition_table(r):
    energy_kj = r[41]
    energy_kcal = r[42]
    fat = r[43]
    sat_fat = r[44]
    carbs = r[45]
    sugar = r[46]
    protein = r[48]
    salt = r[49]

    if not any([energy_kj, energy_kcal, fat, carbs, protein, salt]):
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

    return (
        '<table class="nutrition-table" style="width:100%; border-collapse:collapse; margin-top:10px;">'
        '<thead><tr style="background:#f4f4f4;"><th style="border:1px solid #ddd; padding:6px;">Næringsdeklaration</th>'
        '<th style="border:1px solid #ddd; padding:6px;">pr. 100g</th></tr></thead>'
        f'<tbody>{"".join(rows_html)}</tbody></table>'
    )

def build_body_html(r):
    ing = str(r[34] or "").strip() # Ingredienser (DA)
    allg = str(r[38] or "").strip() # Allergener (DA)
    stor = str(r[56] or "").strip() # Opbevaring (DA)
    prep = str(r[53] or "").strip() # Tilberedning (DA)
    
    parts = ['<div class="product-description" style="font-family:inherit; line-height:1.6;">']
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

def export_csv_from_updated_excel():
    print(f"[*] Reading Updated Excel: {SOURCE_EXCEL}")
    wb = openpyxl.load_workbook(SOURCE_EXCEL, data_only=True)
    sheet = wb["Da loc barcode"]
    rows = list(sheet.iter_rows(values_only=True))[3:]

    records = []
    for r in rows:
        barcode = str(r[2] or "").strip()
        sku = str(r[88] or "").strip()
        
        # Clean concise title
        title_da = str(r[4] or "").strip()
        title_en = str(r[3] or "").strip()
        web_title = str(r[101] or "").strip() if len(r) > 101 and r[101] else ""
        
        # Choose concise title
        final_title = title_da or title_en or web_title or f"Product {barcode or sku}"
        # Remove redundant long brackets if any
        final_title = re.sub(r'\s*\([^)]*\)', '', final_title).strip()
        if not final_title:
            final_title = title_da or title_en

        brand = str(r[5] or "").strip()
        origin = str(r[27] or "").strip()
        l1 = str(r[96] or "").strip() or "Diverse"
        l2 = str(r[97] or "").strip() or f"Other {l1}"
        online_status = str(r[91] or "").strip()
        
        price = r[87]
        try:
            price_val = float(price) if price is not None and str(price).strip() not in ['', '0', '0.0'] else 25.0
        except Exception:
            price_val = 25.0

        handle_base = slugify(final_title)
        handle = f"{handle_base}-{barcode}" if barcode else f"{handle_base}-{sku}"

        raw_qty = r[15]
        grams = 500
        if raw_qty:
            try:
                grams = int(float(raw_qty))
            except Exception:
                grams = 500

        # Tags with Level 1 and Level 2 hierarchy
        tags_list = [l1, f"subcat:{l2}", "online_import_2026"]
        if brand:
            tags_list.append(brand)
        if origin:
            tags_list.append(origin)
        tags_str = ", ".join(dict.fromkeys(tags_list))

        body_html = build_body_html(r)
        
        # Local image check
        local_img = os.path.join(IMAGE_DIR, f"{barcode}.jpg") if barcode else ""
        has_local_img = os.path.exists(local_img)

        rec = {
            "Handle": handle,
            "Title": final_title,
            "Body (HTML)": body_html,
            "Vendor": brand or "Rabuta",
            "Product Category": f"Food, Beverages & Tobacco > Food Items > {l1}",
            "Type": l1,
            "Tags": tags_str,
            "Published": "True" if online_status == "Online" else "False",
            "Option1 Name": "Title",
            "Option1 Value": "Default Title",
            "Variant SKU": sku,
            "Variant Grams": grams,
            "Variant Inventory Tracker": "shopify",
            "Variant Inventory Qty": 100,
            "Variant Inventory Policy": "deny",
            "Variant Fulfillment Service": "manual",
            "Variant Price": price_val,
            "Variant Compare At Price": "",
            "Variant Requires Shipping": "True",
            "Variant Taxable": "True",
            "Variant Barcode": barcode,
            "Image Src": f"https://rabuta.dk/cdn/shop/files/{barcode}.jpg" if barcode else "",
            "Image Position": 1,
            "Image Alt Text": final_title,
            "Status": "active" if online_status == "Online" else "draft",
            "Local Image Path": local_img if has_local_img else "",
            "Category Level 1": l1,
            "Category Level 2": l2
        }
        records.append(rec)

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)

    print(f"[+] Exported {len(records)} clean products to: {OUT_CSV}")
    return records

def push_to_shopify(sample_limit=None):
    token = get_valid_token()
    if not token:
        print("[!] Error obtaining Shopify access token. Check credentials.")
        return

    records = export_csv_from_updated_excel()
    if sample_limit:
        records = records[:sample_limit]

    print(f"\n========================================================")
    print(f"[*] SYNCING TO SHOPIFY LIVE ({STORE_DOMAIN})")
    print(f"[*] Total products to sync: {len(records)}")
    print(f"========================================================")

    # 1. Fetch existing products mapping from Shopify (by Barcode & SKU)
    print("[*] Fetching existing live products on Shopify to map Barcodes...")
    live_map = {}
    url = f"https://{STORE_DOMAIN}/admin/api/2026-10/products.json?limit=250&fields=id,title,variants,images"
    while url:
        req = urllib.request.Request(url)
        req.add_header("X-Shopify-Access-Token", token)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for p in data.get("products", []):
                    p_id = p["id"]
                    for v in p.get("variants", []):
                        bc = str(v.get("barcode") or "").strip()
                        v_id = v["id"]
                        if bc:
                            live_map[bc] = {"product_id": p_id, "variant_id": v_id, "images": p.get("images", [])}
                
                # Check pagination Link header
                link_header = resp.headers.get("Link", "")
                next_url = None
                if link_header:
                    for part in link_header.split(","):
                        if 'rel="next"' in part:
                            next_url = part.split(";")[0].strip("<> ")
                url = next_url
        except Exception as e:
            print(f"[!] Warning fetching live products: {e}")
            break

    print(f"[+] Found {len(live_map)} mapped barcodes currently live on Shopify.")

    # 2. Iterate and sync each product
    success_count = 0
    updated_count = 0
    created_count = 0

    for idx, rec in enumerate(records, start=1):
        bc = rec["Variant Barcode"]
        title = rec["Title"]
        body_html = rec["Body (HTML)"]
        vendor = rec["Vendor"]
        p_type = rec["Type"]
        tags = rec["Tags"]
        price = rec["Variant Price"]
        sku = rec["Variant SKU"]
        local_img = rec["Local Image Path"]

        # Prepare Image Payload
        images_payload = []
        if local_img and os.path.exists(local_img):
            try:
                with open(local_img, "rb") as imf:
                    b64 = base64.b64encode(imf.read()).decode("utf-8")
                    images_payload.append({
                        "attachment": b64,
                        "filename": f"{bc}.jpg",
                        "alt": title
                    })
            except Exception:
                pass

        if bc in live_map:
            # UPDATE EXISTING PRODUCT
            p_id = live_map[bc]["product_id"]
            v_id = live_map[bc]["variant_id"]
            
            payload = {
                "product": {
                    "id": p_id,
                    "title": title,
                    "body_html": body_html,
                    "vendor": vendor,
                    "product_type": p_type,
                    "tags": tags
                }
            }
            if images_payload:
                payload["product"]["images"] = images_payload

            # API PUT
            try:
                put_url = f"https://{STORE_DOMAIN}/admin/api/2026-10/products/{p_id}.json"
                req = urllib.request.Request(put_url, data=json.dumps(payload).encode("utf-8"), method="PUT")
                req.add_header("X-Shopify-Access-Token", token)
                req.add_header("Content-Type", "application/json")
                with urllib.request.urlopen(req, timeout=30) as resp:
                    pass
                updated_count += 1
                success_count += 1
                print(f"[{idx}/{len(records)}] [UPDATED LIVE] {bc} | {title[:40]} | Image Attached: {bool(images_payload)}")
            except Exception as e:
                print(f"[{idx}/{len(records)}] [UPDATE FAILED] {bc} | Err: {e}")
        else:
            # CREATE NEW PRODUCT
            new_payload = {
                "product": {
                    "title": title,
                    "body_html": body_html,
                    "vendor": vendor,
                    "product_type": p_type,
                    "tags": tags,
                    "status": "active" if rec["Published"] == "True" else "draft",
                    "variants": [{
                        "barcode": bc,
                        "sku": sku,
                        "price": str(price),
                        "inventory_management": "shopify",
                        "inventory_quantity": 100
                    }]
                }
            }
            if images_payload:
                new_payload["product"]["images"] = images_payload

            try:
                post_url = f"https://{STORE_DOMAIN}/admin/api/2026-10/products.json"
                req = urllib.request.Request(post_url, data=json.dumps(new_payload).encode("utf-8"), method="POST")
                req.add_header("X-Shopify-Access-Token", token)
                req.add_header("Content-Type", "application/json")
                with urllib.request.urlopen(req, timeout=30) as resp:
                    pass
                created_count += 1
                success_count += 1
                print(f"[{idx}/{len(records)}] [CREATED NEW] {bc} | {title[:40]} | Image Attached: {bool(images_payload)}")
            except Exception as e:
                print(f"[{idx}/{len(records)}] [CREATE FAILED] {bc} | Err: {e}")

        # Rate-limiting pause
        time.sleep(0.5)

    print(f"\n========================================================")
    print(f"[+] SHOPIFY SYNC COMPLETE!")
    print(f"    - Total processed: {len(records)}")
    print(f"    - Successfully updated: {updated_count}")
    print(f"    - Successfully created: {created_count}")
    print(f"    - Success rate: {success_count}/{len(records)} ({success_count/len(records)*100:.1f}%)")
    print(f"========================================================")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--export-only", action="store_true", help="Only export CSV")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of items to sync")
    args = parser.parse_args()

    if args.export_only:
        export_csv_from_updated_excel()
    else:
        push_to_shopify(sample_limit=args.limit)
