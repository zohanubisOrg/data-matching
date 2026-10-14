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

def graphql_query(query, variables=None):
    url = f"https://{shop}/admin/api/2026-10/graphql.json"
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
    req.add_header("X-Shopify-Access-Token", token)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def main():
    menu_id = "gid://shopify/Menu/308864647553"
    q_digest = """
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
    res = graphql_query(q_digest, {"resourceId": menu_id})
    print("Menu Translatable Content:", res.get("data", {}).get("translatableResource", {}).get("translatableContent", []))

if __name__ == "__main__":
    main()
