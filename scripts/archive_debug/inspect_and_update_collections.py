import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import json
import urllib.request
import urllib.parse
import urllib.error

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
shop = ENV.get("SHOPIFY_STORE_DOMAIN", "rabuta.myshopify.com")
token = ENV.get("SHOPIFY_ADMIN_ACCESS_TOKEN")

def get_smart_collections():
    url = f"https://{shop}/admin/api/2026-10/smart_collections.json?limit=250"
    req = urllib.request.Request(url)
    req.add_header("X-Shopify-Access-Token", token)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data.get("smart_collections", [])

def get_product_count_for_collection(collection_id):
    url = f"https://{shop}/admin/api/2026-10/products/count.json?collection_id={collection_id}"
    req = urllib.request.Request(url)
    req.add_header("X-Shopify-Access-Token", token)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("count", 0)
    except Exception:
        return 0

def update_smart_collection_rules(col_id, rules, disjunctive=True):
    url = f"https://{shop}/admin/api/2026-10/smart_collections/{col_id}.json"
    payload = {
        "smart_collection": {
            "id": col_id,
            "rules": rules,
            "disjunctive": disjunctive
        }
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="PUT")
    req.add_header("X-Shopify-Access-Token", token)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return res.get("smart_collection", {})
    except Exception as e:
        print(f"[!] Error updating collection {col_id}: {e}")
        return None

def main():
    smart_cols = get_smart_collections()
    print("=========================================================")
    print("         DANH SÁCH & SỐ LƯỢNG SẢN PHẨM TRONG COLLECTION  ")
    print("=========================================================")
    for sc in smart_cols:
        cid = sc["id"]
        title = sc["title"]
        cnt = get_product_count_for_collection(cid)
        print(f" • [{title}] (ID: {cid}): {cnt} sản phẩm")
        print(f"    - Current Rules: {sc.get('rules')}")

if __name__ == "__main__":
    main()
