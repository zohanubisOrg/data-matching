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

pid = "gid://shopify/Product/15542672916865"

query = """
query getTranslatable($resourceId: ID!) {
  translatableResource(resourceId: $resourceId) {
    translatableContent {
      key
      value
      digest
      locale
    }
  }
}
"""

req = urllib.request.Request(f"https://{shop}/admin/api/2026-10/graphql.json", data=json.dumps({"query": query, "variables": {"resourceId": pid}}).encode("utf-8"), method="POST")
req.add_header("X-Shopify-Access-Token", token)
req.add_header("Content-Type", "application/json")
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    print("Translatable Content:", data)
    
    contents = data["data"]["translatableResource"]["translatableContent"]
    title_digest = next((c["digest"] for c in contents if c["key"] == "title"), None)
    print("Title Digest:", title_digest)
    
    # Now try registering translation with digest
    mutation = """
    mutation translationsRegister($resourceId: ID!, $translations: [TranslationInput!]!) {
      translationsRegister(resourceId: $resourceId, translations: $translations) {
        userErrors {
          field
          message
        }
        translations {
          locale
          key
          value
        }
      }
    }
    """
    
    translations = [
        {"locale": "vi", "key": "title", "value": "Bánh quy que giòn Lotus Dorkbua vị truyền thống 110 g", "translatableContentDigest": title_digest},
        {"locale": "th", "key": "title", "value": "ขนมขาไก่ โลตัส ดอกบัว รสดั้งเดิม 110 กรัม", "translatableContentDigest": title_digest}
    ]
    
    req_m = urllib.request.Request(f"https://{shop}/admin/api/2026-10/graphql.json", data=json.dumps({"query": mutation, "variables": {"resourceId": pid, "translations": translations}}).encode("utf-8"), method="POST")
    req_m.add_header("X-Shopify-Access-Token", token)
    req_m.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req_m) as resp_m:
        data_m = json.loads(resp_m.read().decode("utf-8"))
        print("\nRegistered Translations Result:", data_m)
