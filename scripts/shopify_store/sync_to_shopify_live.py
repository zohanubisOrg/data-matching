import os
import sys

# Force UTF-8 stdout/stderr for Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import json
import time
import base64
import urllib.request
import urllib.parse
import urllib.error
import re
import pandas as pd
import argparse
from datetime import datetime

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

IMAGE_SEARCH_DIRS = [
    "output/shopify_import_final/HD_Studio_Front_Images",
    "output/shopify_import_final/Shopify_Upload_Images_Online_Active",
    "output/shopify_import_final/product_images_barcode_only",
    "output/shopify_import_final/Master_1659_Clean_Front_Images",
    "output/shopify_import_final/excel_delivery_thumbs"
]

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

def find_local_image(barcode):
    if not barcode:
        return None
    bc = str(barcode).strip()
    for d in IMAGE_SEARCH_DIRS:
        if not os.path.exists(d):
            continue
        for f in os.listdir(d):
            if f.startswith(f"{bc}.") or f == f"{bc}.jpg" or f"_{bc}_" in f:
                return os.path.join(d, f)
    return None

def make_shopify_request(endpoint, method="GET", payload=None, token=None, max_retries=6):
    url = f"https://{STORE_DOMAIN}/admin/api/2026-10/{endpoint}"
    data = json.dumps(payload).encode("utf-8") if payload else None
    
    for attempt in range(max_retries):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("X-Shopify-Access-Token", token)
        req.add_header("Content-Type", "application/json")
        
        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                res_body = resp.read().decode("utf-8")
                return json.loads(res_body) if res_body else {}
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8")
            if e.code == 429:
                wait_sec = 2.0 * (attempt + 1)
                print(f"        [Rate Limit 429] Waiting {wait_sec}s...")
                time.sleep(wait_sec)
                continue
            elif e.code == 401 or e.code == 403:
                token = get_valid_token()
                time.sleep(1)
                continue
            elif e.code >= 500:
                time.sleep(2)
                continue
            else:
                return {"error": True, "status": e.code, "message": err_msg}
        except Exception as e:
            if attempt == max_retries - 1:
                return {"error": True, "message": str(e)}
            time.sleep(1.5)
            
    return {"error": True, "message": "Max retries exceeded"}

def sync_single_product(row, action, live_pid, live_vid, token, dry_run=False, replace_images=True):
    title = str(row.get("Title", "")).strip()
    handle = str(row.get("Handle", "")).strip()
    body_html = str(row.get("Body (HTML)", "")) if pd.notna(row.get("Body (HTML)")) else ""
    vendor = str(row.get("Vendor", "")).strip() if pd.notna(row.get("Vendor")) else ""
    product_type = str(row.get("Type", "")).strip() if pd.notna(row.get("Type")) else ""
    tags = str(row.get("Tags", "")).strip() if pd.notna(row.get("Tags")) else ""
    barcode = str(row.get("Variant Barcode", "")).strip()
    sku = str(row.get("Variant SKU", "")).strip() if pd.notna(row.get("Variant SKU")) else ""
    price = str(row.get("Variant Price", "")).strip() if pd.notna(row.get("Variant Price")) else ""
    compare_at_price = str(row.get("Variant Compare At Price", "")).strip() if pd.notna(row.get("Variant Compare At Price")) and str(row.get("Variant Compare At Price")).strip() != "nan" else None
    grams = int(float(row.get("Variant Grams", 0))) if pd.notna(row.get("Variant Grams")) and str(row.get("Variant Grams")).replace('.', '', 1).isdigit() else 500
    
    image_path = find_local_image(barcode)
    image_payload = []
    if image_path:
        try:
            with open(image_path, "rb") as img_f:
                b64 = base64.b64encode(img_f.read()).decode("utf-8")
                image_payload.append({
                    "attachment": b64,
                    "filename": f"{barcode}.jpg",
                    "alt": title
                })
        except Exception as e:
            pass

    if dry_run:
        return {
            "success": True,
            "action": action,
            "dry_run": True,
            "barcode": barcode,
            "title": title,
            "has_image": bool(image_path),
            "product_type": product_type,
            "tags": tags
        }

    # ==================== UPDATE FLOW ====================
    if action == "UPDATE_EXISTING" and live_pid:
        product_update_payload = {
            "product": {
                "id": int(live_pid),
                "title": title,
                "body_html": body_html,
                "vendor": vendor,
                "product_type": product_type,
                "tags": tags
            }
        }
        
        live_img_count = int(row.get("Live_Image_Count", 0)) if pd.notna(row.get("Live_Image_Count")) else 0
        if (live_img_count == 0 or replace_images) and image_payload:
            product_update_payload["product"]["images"] = image_payload

        res = make_shopify_request(f"products/{live_pid}.json", method="PUT", payload=product_update_payload, token=token)
        if res.get("error"):
            return {"success": False, "action": action, "barcode": barcode, "error": res}

        if live_vid:
            variant_payload = {
                "variant": {
                    "id": int(live_vid),
                    "barcode": barcode,
                    "sku": sku,
                    "grams": grams
                }
            }
            if price:
                variant_payload["variant"]["price"] = price
            if compare_at_price:
                variant_payload["variant"]["compare_at_price"] = compare_at_price
                
            res_v = make_shopify_request(f"variants/{live_vid}.json", method="PUT", payload=variant_payload, token=token)

        return {
            "success": True,
            "action": "UPDATE_EXISTING",
            "barcode": barcode,
            "product_id": live_pid,
            "title": title,
            "handle": res.get("product", {}).get("handle", handle)
        }

    # ==================== CREATE FLOW ====================
    else:
        new_product_payload = {
            "product": {
                "title": title,
                "handle": handle,
                "body_html": body_html,
                "vendor": vendor,
                "product_type": product_type,
                "tags": tags,
                "status": "active",
                "variants": [
                    {
                        "barcode": barcode,
                        "sku": sku,
                        "price": price if price else "0",
                        "grams": grams,
                        "inventory_management": "shopify",
                        "inventory_policy": "deny"
                    }
                ]
            }
        }
        if compare_at_price:
            new_product_payload["product"]["variants"][0]["compare_at_price"] = compare_at_price
            
        if image_payload:
            new_product_payload["product"]["images"] = image_payload

        res = make_shopify_request("products.json", method="POST", payload=new_product_payload, token=token)
        if res.get("error"):
            return {"success": False, "action": "CREATE_NEW", "barcode": barcode, "error": res}

        created_p = res.get("product", {})
        return {
            "success": True,
            "action": "CREATE_NEW",
            "barcode": barcode,
            "product_id": created_p.get("id"),
            "title": title,
            "handle": created_p.get("handle", handle)
        }

def run_sync(mode="full", count=5, dry_run=False, force=False):
    token = get_valid_token()
    os.makedirs("output/reconciliation", exist_ok=True)
    report_csv = "output/reconciliation/Shopify_Live_Reconciliation_Report.csv"
    if not os.path.exists(report_csv):
        print(f"[!] Reconciliation report not found at {report_csv}. Please run shopify_catalog_sync_cli.py first.")
        return

    df_rec = pd.read_csv(report_csv, dtype=str)
    df_local = pd.read_csv("output/shopify_import_final/Shopify_Import_Online_Products.csv", dtype=str, encoding="utf-8-sig")
    
    merged = pd.merge(df_rec, df_local, left_on="Local_Barcode", right_on="Variant Barcode", how="inner")
    merged = merged.drop_duplicates(subset=["Local_Barcode"])
    
    progress_file = "output/reconciliation/sync_progress.json"
    completed_barcodes = {}
    if os.path.exists(progress_file):
        try:
            with open(progress_file, "r", encoding="utf-8") as f:
                completed_barcodes = json.load(f)
        except Exception:
            completed_barcodes = {}

    targets = merged
    if mode == "test":
        updates = merged[merged["Reconciliation_Action"] == "UPDATE_EXISTING"]
        creates = merged[merged["Reconciliation_Action"] == "CREATE_NEW"]
        u_count = min(2, len(updates))
        c_count = min(count - u_count, len(creates))
        targets = pd.concat([updates.head(u_count), creates.head(c_count)])

    total = len(targets)
    already_done = sum(1 for _, row in targets.iterrows() if row["Local_Barcode"] in completed_barcodes and completed_barcodes[row["Local_Barcode"]].get("success"))
    
    print(f"\n========================================================")
    print(f"       STARTING SHOPIFY SYNC ({mode.upper()} MODE)       ")
    print(f"       Total Products to Process: {total}               ")
    print(f"       Already Completed in Log:  {already_done}/{total}")
    print(f"========================================================")

    results = []
    success_count = 0
    fail_count = 0
    start_time = time.time()
    processed_this_run = 0

    for idx, (_, row) in enumerate(targets.iterrows()):
        barcode = row["Local_Barcode"]
        action = row["Reconciliation_Action"]
        title = row["Local_Title"]
        live_pid = row["Live_Product_ID"]
        live_vid = row["Live_Variant_ID"]

        # Check if already processed
        if not dry_run and not force and barcode in completed_barcodes and completed_barcodes[barcode].get("success"):
            results.append(completed_barcodes[barcode])
            success_count += 1
            continue

        res = sync_single_product(row, action, live_pid, live_vid, token, dry_run=dry_run)
        results.append(res)
        completed_barcodes[barcode] = res
        processed_this_run += 1

        if res.get("success"):
            success_count += 1
            tag = "[DRY-RUN]" if dry_run else "[SUCCESS]"
            pid = res.get("product_id", "")
            try:
                print(f"[{idx+1}/{total}] {tag} ({action}) {barcode} | (ID: {pid})")
            except Exception:
                print(f"[{idx+1}/{total}] {tag} ({action}) {barcode}")
        else:
            fail_count += 1
            try:
                print(f"[{idx+1}/{total}] [FAILED] ({action}) {barcode} | Err: {res.get('error')}")
            except Exception:
                print(f"[{idx+1}/{total}] [FAILED] ({action}) {barcode}")

        # Save progress every 10 items
        if processed_this_run % 10 == 0:
            with open(progress_file, "w", encoding="utf-8") as f:
                json.dump(completed_barcodes, f, ensure_ascii=False, indent=2)
            elapsed = time.time() - start_time
            rate = processed_this_run / elapsed if elapsed > 0 else 1
            remaining = (total - success_count) / rate if rate > 0 else 0
            print(f"    --> Total Progress: {success_count}/{total} ({success_count/total*100:.1f}%) | Est. remaining: {remaining/60:.1f} mins")

        time.sleep(0.35)

    # Final save
    with open(progress_file, "w", encoding="utf-8") as f:
        json.dump(completed_barcodes, f, ensure_ascii=False, indent=2)

    # Export final Excel summary
    df_results = pd.DataFrame(results)
    summary_xlsx = "output/reconciliation/Shopify_Full_Bulk_Sync_Summary.xlsx"
    df_results.to_excel(summary_xlsx, index=False)

    print("\n========================================================")
    print(f"🎉 BULK SYNC COMPLETE!")
    print(f"   - Total Processed: {total}")
    print(f"   - Succeeded:       {success_count}")
    print(f"   - Failed:          {fail_count}")
    print(f"   - Summary Report:  {summary_xlsx}")
    print("========================================================")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["test", "full"], default="full")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    
    run_sync(mode=args.mode, count=args.count, dry_run=args.dry_run, force=args.force)
