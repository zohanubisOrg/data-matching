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

def enable_and_publish_locale(locale_code):
    print(f"\n[*] Enabling locale '{locale_code}'...")
    
    # 1. Enable locale
    enable_mutation = """
    mutation shopLocaleEnable($locale: String!) {
      shopLocaleEnable(locale: $locale) {
        shopLocale {
          locale
          name
          published
        }
        userErrors {
          field
          message
        }
      }
    }
    """
    res = graphql_query(enable_mutation, {"locale": locale_code})
    print("    Enable result:", res)

    # 2. Update to published if not already
    publish_mutation = """
    mutation shopLocaleUpdate($locale: String!, $shopLocale: ShopLocaleInput!) {
      shopLocaleUpdate(locale: $locale, shopLocale: $shopLocale) {
        shopLocale {
          locale
          name
          published
        }
        userErrors {
          field
          message
        }
      }
    }
    """
    res_pub = graphql_query(publish_mutation, {
        "locale": locale_code,
        "shopLocale": {"published": True}
    })
    print("    Publish result:", res_pub)

def main():
    print("=========================================================")
    print("       ADDING VIETNAMESE (vi) & THAI (th) LOCALES        ")
    print("=========================================================")
    
    # Enable Thai
    enable_and_publish_locale("th")
    
    # Enable Vietnamese
    enable_and_publish_locale("vi")

    # Verify all locales
    query_all = """
    {
      shopLocales {
        locale
        name
        primary
        published
      }
    }
    """
    res = graphql_query(query_all)
    print("\n=========================================================")
    print("             FINAL ACTIVE STORE LOCALES                  ")
    print("=========================================================")
    for loc in res.get("data", {}).get("shopLocales", []):
        is_pri = " (PRIMARY)" if loc["primary"] else ""
        is_pub = "PUBLISHED ✅" if loc["published"] else "UNPUBLISHED ⚠️"
        print(f" • [{loc['locale'].upper()}] {loc['name']}{is_pri} -> {is_pub}")

if __name__ == "__main__":
    main()
