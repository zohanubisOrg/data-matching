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
    market_id = "gid://shopify/Market/98935341441"
    domain_id = "gid://shopify/Domain/171723915649"
    
    mutation = """
    mutation marketWebPresenceCreate($marketId: ID!, $webPresence: MarketWebPresenceCreateInput!) {
      marketWebPresenceCreate(marketId: $marketId, webPresence: $webPresence) {
        market {
          id
          name
          webPresence {
            id
            subfolderSuffix
            rootUrls {
              locale
              url
            }
          }
        }
        userErrors {
          field
          message
        }
      }
    }
    """
    
    payload_create = {
        "domainId": domain_id,
        "defaultLocale": "en",
        "alternateLocales": ["da", "vi", "th"]
    }
    
    res = graphql_query(mutation, {
        "marketId": market_id,
        "webPresence": payload_create
    })
    print("Market Web Presence Create Result:", json.dumps(res, indent=2))

if __name__ == "__main__":
    main()
