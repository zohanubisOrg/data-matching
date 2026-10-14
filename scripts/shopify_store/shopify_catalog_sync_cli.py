import os
import sys
import json
import time
import urllib.request
import urllib.parse
import urllib.error
import re
import pandas as pd

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

ENV = load_env()
STORE_DOMAIN = ENV.get("SHOPIFY_STORE_DOMAIN", "rabuta.myshopify.com")
CLIENT_ID = ENV.get("SHOPIFY_CLIENT_ID", "92dffc351563618e67f903ad62c89b91")
CLIENT_SECRET = ENV.get("SHOPIFY_CLIENT_SECRET", "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")
ACCESS_TOKEN = ENV.get("SHOPIFY_ADMIN_ACCESS_TOKEN", "")

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

def fetch_all_live_products(token):
    print(f"[*] Fetching all live products from {STORE_DOMAIN}...")
    products = []
    url = f"https://{STORE_DOMAIN}/admin/api/2026-10/products.json?limit=250"
    
    page = 1
    while url:
        req = urllib.request.Request(url)
        req.add_header("X-Shopify-Access-Token", token)
        req.add_header("Content-Type", "application/json")
        
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                batch = data.get("products", [])
                products.extend(batch)
                print(f"    Page {page}: Retrieved {len(batch)} products (Total so far: {len(products)})")
                
                # Check pagination Link header
                link_header = resp.headers.get("Link")
                url = None
                if link_header:
                    for part in link_header.split(","):
                        if 'rel="next"' in part:
                            match = re.search(r'<([^>]+)>', part)
                            if match:
                                url = match.group(1)
                page += 1
                time.sleep(0.3)
        except Exception as e:
            print(f"[!] Error fetching products page {page}: {e}")
            break

    print(f"[+] Total live products retrieved from Shopify: {len(products)}")
    return products

def normalize_barcode(bc):
    if pd.isna(bc) or bc is None:
        return ""
    bc_str = str(bc).strip()
    if bc_str.endswith(".0"):
        bc_str = bc_str[:-2]
    m = re.search(r'(\d{8,14})', bc_str)
    if m:
        return m.group(1)
    return bc_str

def reconcile(live_products, csv_path="output/shopify_import_final/Shopify_Import_Online_Products.csv"):
    os.makedirs("output/reconciliation", exist_ok=True)
    print(f"[*] Loading local CSV import dataset from {csv_path}...")
    df_local = pd.read_csv(csv_path, dtype=str, encoding="utf-8-sig")
    print(f"[+] Loaded {len(df_local)} local products")

    # Index live products
    live_by_barcode = {}
    live_by_sku = {}
    live_by_handle = {}
    live_by_id = {}

    for p in live_products:
        pid = p["id"]
        live_by_id[pid] = p
        p_handle = p.get("handle", "").strip().lower()
        if p_handle:
            live_by_handle[p_handle] = p

        for v in p.get("variants", []):
            v_bc = normalize_barcode(v.get("barcode", ""))
            if v_bc:
                live_by_barcode[v_bc] = {"product": p, "variant": v}
            v_sku = str(v.get("sku", "")).strip().lower()
            if v_sku:
                live_by_sku[v_sku] = {"product": p, "variant": v}

    print(f"[+] Live indexing summary:")
    print(f"    - Unique Live Barcodes: {len(live_by_barcode)}")
    print(f"    - Unique Live SKUs:     {len(live_by_sku)}")
    print(f"    - Unique Live Handles:  {len(live_by_handle)}")

    reconciled_rows = []
    matched_live_product_ids = set()

    counts = {
        "MATCH_BY_BARCODE": 0,
        "MATCH_BY_HANDLE": 0,
        "MATCH_BY_SKU": 0,
        "NEW_PRODUCT": 0
    }

    for idx, row in df_local.iterrows():
        local_bc = normalize_barcode(row.get("Variant Barcode", ""))
        local_sku = str(row.get("Variant SKU", "")).strip().lower()
        local_handle = str(row.get("Handle", "")).strip().lower()
        local_title = str(row.get("Title", "")).strip()
        local_price = str(row.get("Variant Price", "")).strip()

        match_type = "NEW_PRODUCT"
        matched_p = None
        matched_v = None

        if local_bc and local_bc in live_by_barcode:
            match_type = "MATCH_BY_BARCODE"
            matched_p = live_by_barcode[local_bc]["product"]
            matched_v = live_by_barcode[local_bc]["variant"]
        elif local_handle and local_handle in live_by_handle:
            match_type = "MATCH_BY_HANDLE"
            matched_p = live_by_handle[local_handle]
            matched_v = matched_p["variants"][0] if matched_p.get("variants") else None
        elif local_sku and local_sku in live_by_sku:
            match_type = "MATCH_BY_SKU"
            matched_p = live_by_sku[local_sku]["product"]
            matched_v = live_by_sku[local_sku]["variant"]

        counts[match_type] += 1

        rec_item = {
            "STT": idx + 1,
            "Reconciliation_Action": "UPDATE_EXISTING" if matched_p else "CREATE_NEW",
            "Match_Method": match_type,
            "Local_Handle": row.get("Handle", ""),
            "Local_Title": local_title,
            "Local_Barcode": local_bc,
            "Local_SKU": row.get("Variant SKU", ""),
            "Local_Price": local_price,
            "Local_Status": row.get("Status", "active"),
            "Local_Image": row.get("Image Src", ""),
            "Live_Product_ID": matched_p["id"] if matched_p else "",
            "Live_Variant_ID": matched_v["id"] if matched_v else "",
            "Live_Title": matched_p["title"] if matched_p else "",
            "Live_Handle": matched_p["handle"] if matched_p else "",
            "Live_Barcode": matched_v.get("barcode", "") if matched_v else "",
            "Live_SKU": matched_v.get("sku", "") if matched_v else "",
            "Live_Price": matched_v.get("price", "") if matched_v else "",
            "Live_Status": matched_p.get("status", "") if matched_p else "",
            "Live_Image_Count": len(matched_p.get("images", [])) if matched_p else 0
        }

        if matched_p:
            matched_live_product_ids.add(matched_p["id"])

        reconciled_rows.append(rec_item)

    df_rec = pd.DataFrame(reconciled_rows)
    
    report_xlsx = "output/reconciliation/Shopify_Live_Reconciliation_Report.xlsx"
    report_csv = "output/reconciliation/Shopify_Live_Reconciliation_Report.csv"
    
    df_rec.to_excel(report_xlsx, index=False)
    df_rec.to_csv(report_csv, index=False, encoding="utf-8-sig")

    print("\n========================================================")
    print("           RECONCILIATION SUMMARY AUDIT                 ")
    print("========================================================")
    print(f"Total Local Products in CSV:         {len(df_local):>6}")
    print(f"Total Live Products on Shopify:      {len(live_products):>6}")
    print(f"--------------------------------------------------------")
    print(f"Found Existing (MATCH BY BARCODE):   {counts['MATCH_BY_BARCODE']:>6}")
    print(f"Found Existing (MATCH BY HANDLE):    {counts['MATCH_BY_HANDLE']:>6}")
    print(f"Found Existing (MATCH BY SKU):       {counts['MATCH_BY_SKU']:>6}")
    total_update = counts['MATCH_BY_BARCODE'] + counts['MATCH_BY_HANDLE'] + counts['MATCH_BY_SKU']
    print(f"Total Products to UPDATE:            {total_update:>6}")
    print(f"Total Products to CREATE NEW:        {counts['NEW_PRODUCT']:>6}")
    print(f"Live Products Untouched on Web:      {len(live_products) - len(matched_live_product_ids):>6}")
    print("========================================================")
    print(f"[+] Full detailed report exported to:")
    print(f"    - Excel: {report_xlsx}")
    print(f"    - CSV:   {report_csv}")

    return df_rec

def main():
    os.makedirs("output/reconciliation", exist_ok=True)
    token = get_valid_token()
    print(f"[+] Shopify Connected Successfully! Token: {token[:10]}...")
    
    # 1. Fetch live products
    live_products = fetch_all_live_products(token)
    
    # Save live backup
    with open("output/reconciliation/live_shopify_backup.json", "w", encoding="utf-8") as f:
        json.dump(live_products, f, ensure_ascii=False, indent=2)
    print("[+] Live backup saved to output/reconciliation/live_shopify_backup.json")
    
    # 2. Reconcile
    reconcile(live_products)

if __name__ == "__main__":
    main()
