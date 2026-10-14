import sys
import json
import urllib.request
sys.path.insert(0, ".")
from scripts.shopify_catalog_sync_cli import get_valid_token, STORE_DOMAIN

def list_theme_assets():
    token = get_valid_token()
    theme_id = 189930996097
    url = f"https://{STORE_DOMAIN}/admin/api/2026-10/themes/{theme_id}/assets.json"
    req = urllib.request.Request(url)
    req.add_header("X-Shopify-Access-Token", token)
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    assets = [a["key"] for a in data.get("assets", []) if "locales/" in a["key"]]
    print("Locale assets:", assets)

if __name__ == "__main__":
    list_theme_assets()
