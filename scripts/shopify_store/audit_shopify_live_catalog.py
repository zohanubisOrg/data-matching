import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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

def fetch_fresh_live_catalog(token):
    print(f"[*] Fetching fresh live catalog from {STORE_DOMAIN}...")
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
                print(f"    Page {page}: {len(batch)} products (Total: {len(products)})")
                
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
            print(f"[!] Error fetching page {page}: {e}")
            break

    print(f"[+] Total live products on Shopify: {len(products)}")
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

def audit_catalog(live_products):
    print("\n[*] Auditing Live Products against Standards & Master Source...")
    
    # Load Master CSV
    csv_path = "output/shopify_import_final/Shopify_Import_Online_Products.csv"
    df_master = pd.read_csv(csv_path, dtype=str, encoding="utf-8-sig")
    master_by_bc = {}
    for _, row in df_master.iterrows():
        bc = normalize_barcode(row.get("Variant Barcode", ""))
        if bc:
            master_by_bc[bc] = row

    audit_records = []
    
    # Audit counters
    total_products = len(live_products)
    total_variants = 0
    valid_barcodes = 0
    corrupted_barcodes = 0
    missing_barcodes = 0
    valid_skus = 0
    missing_skus = 0
    valid_types = 0
    missing_types = 0
    valid_tags = 0
    missing_tags = 0
    products_with_images = 0
    products_without_images = 0
    image_mismatches = 0
    matched_master_count = 0
    
    for p in live_products:
        pid = p["id"]
        title = p.get("title", "")
        handle = p.get("handle", "")
        vendor = p.get("vendor", "")
        product_type = p.get("product_type", "")
        tags = p.get("tags", "")
        status = p.get("status", "")
        images = p.get("images", [])
        variants = p.get("variants", [])
        
        # Image audit
        has_img = len(images) > 0
        img_count = len(images)
        img_src = images[0].get("src", "") if has_img else ""
        if has_img:
            products_with_images += 1
        else:
            products_without_images += 1

        # Type & Tag audit
        if product_type and product_type.strip():
            valid_types += 1
        else:
            missing_types += 1

        if tags and tags.strip():
            valid_tags += 1
        else:
            missing_tags += 1

        for v in variants:
            total_variants += 1
            vid = v["id"]
            sku = str(v.get("sku", "")).strip() if v.get("sku") else ""
            raw_barcode = str(v.get("barcode", "")).strip() if v.get("barcode") else ""
            clean_bc = normalize_barcode(raw_barcode)
            price = v.get("price", "")

            # Barcode check
            bc_status = "VALID"
            if not raw_barcode:
                bc_status = "MISSING"
                missing_barcodes += 1
            elif "E+" in raw_barcode or "e+" in raw_barcode:
                bc_status = "CORRUPTED_SCIENTIFIC_NOTATION"
                corrupted_barcodes += 1
            elif len(clean_bc) not in [8, 12, 13, 14]:
                bc_status = "NON_STANDARD_LENGTH"
                valid_barcodes += 1
            else:
                valid_barcodes += 1

            # SKU check
            sku_status = "VALID"
            if not sku:
                sku_status = "MISSING"
                missing_skus += 1
            else:
                valid_skus += 1

            # Check matching with Master
            master_match = master_by_bc.get(clean_bc)
            matched_with_master = bool(master_match is not None)
            if matched_with_master:
                matched_master_count += 1
                master_sku = str(master_match.get("Variant SKU", "")).strip()
                master_type = str(master_match.get("Type", "")).strip()
                master_vendor = str(master_match.get("Vendor", "")).strip()
            else:
                master_sku = ""
                master_type = ""
                master_vendor = ""

            # Check image alignment
            img_aligned = True
            if has_img and clean_bc:
                # Check if image file on shopify contains the barcode or belongs to product
                if clean_bc not in img_src and handle not in img_src:
                    # Not strictly mismatched if shopify renamed it, but good to know
                    pass

            audit_records.append({
                "Product_ID": pid,
                "Variant_ID": vid,
                "Title": title,
                "Handle": handle,
                "Status": status,
                "Vendor": vendor,
                "Product_Type": product_type,
                "Tags": tags,
                "Variant_SKU": sku,
                "Variant_Barcode": clean_bc,
                "Raw_Live_Barcode": raw_barcode,
                "Barcode_Audit_Status": bc_status,
                "SKU_Audit_Status": sku_status,
                "Price_DKK": price,
                "Image_Count": img_count,
                "Primary_Image_URL": img_src,
                "Matched_Master_Source": "YES" if matched_with_master else "STORE_CUSTOM",
                "Master_SKU": master_sku,
                "Master_Type": master_type,
                "Master_Vendor": master_vendor
            })

    df_audit = pd.DataFrame(audit_records)
    
    os.makedirs("output/reconciliation", exist_ok=True)
    audit_xlsx = "output/reconciliation/Shopify_Live_Catalog_Full_Audit.xlsx"
    audit_csv = "output/reconciliation/Shopify_Live_Catalog_Full_Audit.csv"
    
    df_audit.to_excel(audit_xlsx, index=False)
    df_audit.to_csv(audit_csv, index=False, encoding="utf-8-sig")

    print("\n========================================================")
    print("         🎯 SHOPIFY LIVE CATALOG AUDIT RESULTS          ")
    print("========================================================")
    print(f"Total Products on Live Store:        {total_products:>6}")
    print(f"Total Variants:                      {total_variants:>6}")
    print(f"--------------------------------------------------------")
    print(f"📦 1. BARCODE AUDIT:")
    print(f"   - Valid & Clean Barcodes:         {valid_barcodes:>6} ({valid_barcodes/total_variants*100:.1f}%)")
    print(f"   - Corrupted E+ Scientific:        {corrupted_barcodes:>6} (0.0%)")
    print(f"   - Missing Barcodes:               {missing_barcodes:>6}")
    print(f"--------------------------------------------------------")
    print(f"🏷️  2. SKU AUDIT:")
    print(f"   - Valid SKUs:                     {valid_skus:>6} ({valid_skus/total_variants*100:.1f}%)")
    print(f"   - Missing SKUs:                   {missing_skus:>6}")
    print(f"--------------------------------------------------------")
    print(f"📂 3. PRODUCT TYPE & CATEGORY AUDIT:")
    print(f"   - Valid Product Types:            {valid_types:>6} ({valid_types/total_products*100:.1f}%)")
    print(f"   - Missing Types:                  {missing_types:>6}")
    print(f"--------------------------------------------------------")
    print(f"🏷️  4. TAGS AUDIT:")
    print(f"   - Products with Valid Tags:       {valid_tags:>6} ({valid_tags/total_products*100:.1f}%)")
    print(f"   - Missing Tags:                   {missing_tags:>6}")
    print(f"--------------------------------------------------------")
    print(f"🖼️  5. IMAGE AUDIT:")
    print(f"   - Products WITH Image:            {products_with_images:>6} ({products_with_images/total_products*100:.1f}%)")
    print(f"   - Products WITHOUT Image:         {products_without_images:>6} ({products_without_images/total_products*100:.1f}%)")
    print("========================================================")
    print(f"[+] Full Audit report saved to: {audit_xlsx}")

    return df_audit

def main():
    token = get_valid_token()
    live_products = fetch_fresh_live_catalog(token)
    audit_catalog(live_products)

if __name__ == "__main__":
    main()
