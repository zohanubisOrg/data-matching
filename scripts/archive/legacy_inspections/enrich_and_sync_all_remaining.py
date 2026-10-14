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

def clean_bc(x):
    if pd.isna(x) or not x:
        return ""
    s = str(x).strip()
    if s.endswith(".0"):
        s = s[:-2]
    m = re.search(r'(\d{6,14})', s)
    if m:
        return m.group(1).lstrip("0")
    return s.lstrip("0")

def format_std_barcode(bc):
    if not bc:
        return ""
    s = str(bc).strip()
    if s.endswith(".0"):
        s = s[:-2]
    # Remove any non-digits
    digits = re.sub(r'\D', '', s)
    # If 12 digits, can keep as UPC-A / EAN-13
    return digits

def make_shopify_request(endpoint, method="GET", payload=None, token=None, max_retries=5):
    url = f"https://{STORE_DOMAIN}/admin/api/2026-10/{endpoint}"
    data = json.dumps(payload).encode("utf-8") if payload else None
    
    for attempt in range(max_retries):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("X-Shopify-Access-Token", token)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                res_body = resp.read().decode("utf-8")
                return json.loads(res_body) if res_body else {}
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2.0 * (attempt + 1))
                continue
            elif e.code in [401, 403]:
                token = get_valid_token()
                time.sleep(1)
                continue
            elif e.code >= 500:
                time.sleep(2)
                continue
            else:
                return {"error": True, "status": e.code, "message": e.read().decode("utf-8")}
        except Exception as e:
            if attempt == max_retries - 1:
                return {"error": True, "message": str(e)}
            time.sleep(1.5)
    return {"error": True, "message": "Max retries"}

def main():
    token = get_valid_token()
    print(f"[+] Shopify API Connected! Token: {token[:10]}...")
    
    # 1. Load audit report to get all items missing SKU or Barcode
    df_audit = pd.read_excel('output/reconciliation/Shopify_Live_Catalog_Full_Audit.xlsx')
    items_to_fix = df_audit[(df_audit['SKU_Audit_Status'] == 'MISSING') | (df_audit['Barcode_Audit_Status'] == 'MISSING')].copy()
    print(f"[*] Found {len(items_to_fix)} products needing SKU / Barcode standardization...")

    # 2. Build master knowledge graph from all available files
    master_dict = {}

    # A. From customer-send-me.xlsx (header=1)
    if os.path.exists('customer-send-me.xlsx'):
        try:
            df_cust = pd.read_excel('customer-send-me.xlsx', header=1, dtype=str)
            for _, r in df_cust.iterrows():
                cbc = clean_bc(r.get('Barcode'))
                if cbc and cbc not in master_dict:
                    master_dict[cbc] = {
                        "title_da": str(r.get('Fuldt navn (DA)', '')).strip(),
                        "title_en": str(r.get('Full name (EN)', '')).strip(),
                        "brand": str(r.get('Brand', '')).strip(),
                        "sku": str(r.get('Record ID', '')).strip(),
                        "category": str(r.get('Category (editorial)', 'Diverse')).strip(),
                        "raw_bc": str(r.get('Barcode', '')).strip()
                    }
        except Exception as e:
            print(f"[!] Error reading customer-send-me.xlsx: {e}")

    # B. From Master_All_1659_Products_With_Images.xlsx (header=2)
    path_1659 = 'output/shopify_import_final/Master_All_1659_Products_With_Images.xlsx'
    if os.path.exists(path_1659):
        try:
            df_1659 = pd.read_excel(path_1659, header=2, dtype=str)
            for _, r in df_1659.iterrows():
                cbc = clean_bc(r.get('Barcode'))
                if cbc:
                    master_dict[cbc] = {
                        "title_da": str(r.get('Fuldt navn (DA)', '')).strip(),
                        "title_en": str(r.get('Full name (EN)', '')).strip(),
                        "brand": str(r.get('Brand', '')).strip(),
                        "sku": str(r.get('Record ID', '')).strip(),
                        "category": str(r.get('Category (editorial)', 'Diverse')).strip(),
                        "raw_bc": str(r.get('Barcode', '')).strip()
                    }
        except Exception as e:
            print(f"[!] Error reading 1659 excel: {e}")

    print(f"[+] Total master indexed items: {len(master_dict)}")

    # 3. Process and Update Each Product on Shopify
    updated_count = 0
    failed_count = 0
    results = []

    print("\n[*] Synchronizing & Standardizing 95 remaining products on Shopify...")
    for idx, (_, r) in enumerate(items_to_fix.iterrows()):
        pid = int(r['Product_ID'])
        vid = int(r['Variant_ID'])
        live_title = str(r['Title']).strip()
        raw_bc = str(r['Variant_Barcode'])
        
        cbc = clean_bc(raw_bc)
        if not cbc:
            m = re.search(r'(\d{6,14})', live_title)
            if m:
                cbc = clean_bc(m.group(1))

        # Check lookup
        match = master_dict.get(cbc)
        if match:
            da_t = match["title_da"]
            en_t = match["title_en"]
            brand = match["brand"] if match["brand"] and match["brand"] != "nan" else "Asiatisk"
            sku = match["sku"] if match["sku"] and match["sku"] != "nan" else f"POS-{cbc[-4:]}"
            category = match["category"] if match["category"] and match["category"] != "nan" else "Diverse"
            clean_barcode = format_std_barcode(match["raw_bc"]) if match["raw_bc"] else format_std_barcode(raw_bc)
            final_title = da_t if da_t and da_t != "nan" else (en_t if en_t and en_t != "nan" else live_title)
        else:
            clean_barcode = format_std_barcode(raw_bc)
            if not clean_barcode:
                m = re.search(r'(\d{6,14})', live_title)
                clean_barcode = m.group(1) if m else f"POS{pid}"
            brand = "Asiatisk"
            category = "Diverse"
            sku = f"POS-{clean_barcode[-6:] if len(clean_barcode) >= 6 else clean_barcode}"
            final_title = live_title

        tags = f"{category}, {sku[:3]}, {brand}"

        # 1. Update Product metadata (Title, Vendor, Product Type, Tags)
        product_payload = {
            "product": {
                "id": pid,
                "title": final_title,
                "vendor": brand,
                "product_type": category,
                "tags": tags
            }
        }
        res_p = make_shopify_request(f"products/{pid}.json", method="PUT", payload=product_payload, token=token)
        
        # 2. Update Variant metadata (SKU, Barcode)
        variant_payload = {
            "variant": {
                "id": vid,
                "sku": sku,
                "barcode": clean_barcode
            }
        }
        res_v = make_shopify_request(f"variants/{vid}.json", method="PUT", payload=variant_payload, token=token)

        if not res_p.get("error") and not res_v.get("error"):
            updated_count += 1
            print(f"[{idx+1}/{len(items_to_fix)}] [SUCCESS] Product {pid} -> SKU: {sku} | BC: {clean_barcode} | Title: {final_title[:35]}...")
            results.append({
                "Product_ID": pid,
                "Variant_ID": vid,
                "Status": "SUCCESS",
                "New_SKU": sku,
                "Clean_Barcode": clean_barcode,
                "Title": final_title,
                "Vendor": brand,
                "Category": category
            })
        else:
            failed_count += 1
            print(f"[{idx+1}/{len(items_to_fix)}] [FAILED] Product {pid} -> Err: {res_p.get('message', res_v.get('message'))}")
            results.append({
                "Product_ID": pid,
                "Variant_ID": vid,
                "Status": "FAILED",
                "Error": str(res_p) + " | " + str(res_v)
            })

        time.sleep(0.35)

    print("\n========================================================")
    print(f"Standardization Complete: {updated_count} Succeeded, {failed_count} Failed.")
    print("========================================================")

    # Save summary
    df_res = pd.DataFrame(results)
    df_res.to_excel("output/reconciliation/Standardized_95_Products_Result.xlsx", index=False)
    print("[+] Results saved to output/reconciliation/Standardized_95_Products_Result.xlsx")

if __name__ == "__main__":
    main()
