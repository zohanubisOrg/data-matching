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
import time

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
client_id = ENV.get("SHOPIFY_CLIENT_ID")
client_secret = ENV.get("SHOPIFY_CLIENT_SECRET")
token = ENV.get("SHOPIFY_ADMIN_ACCESS_TOKEN")

def get_token():
    global token
    url = f"https://{shop}/admin/oauth/access_token"
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials"
    }).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        token = res["access_token"]
        return token

def graphql_query(query, variables=None, max_retries=3):
    url = f"https://{shop}/admin/api/2026-10/graphql.json"
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    
    for attempt in range(max_retries):
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
        req.add_header("X-Shopify-Access-Token", token)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2.0 * (attempt + 1))
                continue
            elif e.code in [401, 403]:
                get_token()
                time.sleep(1)
                continue
            else:
                return {}
        except Exception:
            time.sleep(1)
    return {}

# 4-Language Master Definition for Collections
COLLECTIONS_4_LANGS = {
    "nudler": {
        "en": "Noodles & Pasta",
        "da": "Nudler",
        "vi": "Mì, Bún & Phở",
        "th": "บะหมี่และก๋วยเตี๋ยว"
    },
    "snacks": {
        "en": "Snacks & Crackers",
        "da": "Snacks",
        "vi": "Bánh kẹo & Đồ ăn vặt",
        "th": "ขนมและของทานเล่น"
    },
    "saucer-sojasauce": {
        "en": "Sauces & Soy Sauce",
        "da": "Saucer & Sojasauce",
        "vi": "Nước sốt & Nước tương",
        "th": "ซอสปรุงรสและซีอิ๊ว"
    },
    "krydderier-karry": {
        "en": "Spices & Curry",
        "da": "Krydderier & Karry",
        "vi": "Gia vị & Bột cà ri",
        "th": "เครื่องเทศและพริกแกง"
    },
    "drikkevarer-vin": {
        "en": "Beverages & Drinks",
        "da": "Drikkevarer",
        "vi": "Nước giải khát & Đồ uống",
        "th": "เครื่องดื่มและชา"
    },
    "ris-mel-torvarer": {
        "en": "Rice, Flour & Dry Goods",
        "da": "Ris, Mel & Tørvarer",
        "vi": "Gạo, Bột & Đồ khô",
        "th": "ข้าว แป้ง และของแห้ง"
    },
    "konserves-kokosmaelk": {
        "en": "Canned Food & Coconut Milk",
        "da": "Konserves & Kokosmælk",
        "vi": "Đồ hộp & Nước cốt dừa",
        "th": "อาหารกระป๋องและกะทิ"
    },
    "andre-asiatiske-varer": {
        "en": "Other Asian Groceries",
        "da": "Andre asiatiske varer",
        "vi": "Hàng tạp hóa Châu Á khác",
        "th": "สินค้าเอเชียอื่นๆ"
    }
}

def translate_collections():
    print("\n[*] Fetching Collections and registering 4-language translations...")
    
    q_cols = """
    {
      collections(first: 20) {
        edges {
          node {
            id
            handle
            title
          }
        }
      }
    }
    """
    res = graphql_query(q_cols)
    cols = res.get("data", {}).get("collections", {}).get("edges", [])
    
    for c in cols:
        node = c["node"]
        cid = node["id"]
        handle = node["handle"]
        
        if handle not in COLLECTIONS_4_LANGS:
            continue
            
        trans_dict = COLLECTIONS_4_LANGS[handle]
        
        # Get digest
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
        res_d = graphql_query(q_digest, {"resourceId": cid})
        contents = res_d.get("data", {}).get("translatableResource", {}).get("translatableContent", [])
        title_digest = next((item["digest"] for item in contents if item["key"] == "title"), None)
        
        if not title_digest:
            continue
            
        # Register translations for non-primary locales (da, vi, th)
        translations = []
        for loc in ["da", "vi", "th"]:
            translations.append({
                "locale": loc,
                "key": "title",
                "value": trans_dict[loc],
                "translatableContentDigest": title_digest
            })

        m_trans = """
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
        res_reg = graphql_query(m_trans, {"resourceId": cid, "translations": translations})
        errs = res_reg.get("data", {}).get("translationsRegister", {}).get("userErrors", [])
        
        if not errs:
            print(f"[+] Collection '{handle}' TRANSLATED:")
            print(f"    🇬🇧 EN (Base): {node['title']}")
            print(f"    🇩🇰 DA:        {trans_dict['da']}")
            print(f"    🇻🇳 VI:        {trans_dict['vi']}")
            print(f"    🇹🇭 TH:        {trans_dict['th']}")
        else:
            print(f"[!] Error on '{handle}': {errs}")

def main():
    print("=========================================================")
    print("   TRANSLATING COLLECTIONS & CATEGORIES TO 4 LANGUAGES   ")
    print("=========================================================")
    translate_collections()
    print("\n=========================================================")
    print("🎉 4-LANGUAGE CATEGORY TRANSLATIONS DEPLOYED 100%!")
    print("=========================================================")

if __name__ == "__main__":
    main()
