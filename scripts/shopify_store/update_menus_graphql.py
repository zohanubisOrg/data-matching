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
    # 1. Fetch Collections GIDs
    cols_query = """
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
      pages(first: 20) {
        edges {
          node {
            id
            handle
            title
          }
        }
      }
      menus(first: 10) {
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
    data = graphql_query(cols_query)["data"]
    col_map = {c["node"]["handle"]: c["node"]["id"] for c in data["collections"]["edges"]}
    page_map = {p["node"]["handle"]: p["node"]["id"] for p in data["pages"]["edges"]}
    menu_map = {m["node"]["handle"]: m["node"]["id"] for m in data["menus"]["edges"]}
    
    print("Found Collections:", col_map)
    print("Found Pages:", page_map)
    print("Found Menus:", menu_map)

    # 2. Prepare Main Menu items with resourceId
    main_items = [
        {"title": "Hjem", "type": "HTTP", "url": "/"},
        {"title": "Nudler", "type": "COLLECTION", "resourceId": col_map.get("nudler"), "url": "/collections/nudler"},
        {"title": "Snacks", "type": "COLLECTION", "resourceId": col_map.get("snacks"), "url": "/collections/snacks"},
        {"title": "Saucer & Sojasauce", "type": "COLLECTION", "resourceId": col_map.get("saucer-sojasauce"), "url": "/collections/saucer-sojasauce"},
        {"title": "Krydderier & Karry", "type": "COLLECTION", "resourceId": col_map.get("krydderier-karry"), "url": "/collections/krydderier-karry"},
        {"title": "Drikkevarer", "type": "COLLECTION", "resourceId": col_map.get("drikkevarer-vin"), "url": "/collections/drikkevarer-vin"},
        {"title": "Andre asiatiske varer", "type": "COLLECTION", "resourceId": col_map.get("andre-asiatiske-varer"), "url": "/collections/andre-asiatiske-varer"},
        {"title": "Om os", "type": "PAGE", "resourceId": page_map.get("om-os"), "url": "/pages/om-os"},
        {"title": "Kontakt", "type": "PAGE", "resourceId": page_map.get("kontakt-os"), "url": "/pages/kontakt-os"}
    ]
    # Filter out any missing resourceId
    main_items = [i for i in main_items if i.get("type") == "HTTP" or i.get("resourceId")]

    # 3. Prepare Footer Menu items with resourceId
    footer_items = [
        {"title": "Om Rabuta", "type": "PAGE", "resourceId": page_map.get("om-os"), "url": "/pages/om-os"},
        {"title": "Kontakt os", "type": "PAGE", "resourceId": page_map.get("kontakt-os"), "url": "/pages/kontakt-os"},
        {"title": "Levering & Fragt", "type": "PAGE", "resourceId": page_map.get("levering-fragt"), "url": "/pages/levering-fragt"},
        {"title": "Handelsbetingelser", "type": "PAGE", "resourceId": page_map.get("handelsbetingelser"), "url": "/pages/handelsbetingelser"},
        {"title": "Returpolitik", "type": "PAGE", "resourceId": page_map.get("returpolitik"), "url": "/pages/returpolitik"},
        {"title": "Privatlivspolitik", "type": "PAGE", "resourceId": page_map.get("privatlivspolitik"), "url": "/pages/privatlivspolitik"}
    ]
    footer_items = [i for i in footer_items if i.get("type") == "HTTP" or i.get("resourceId")]

    mutation = """
    mutation menuUpdate($id: ID!, $title: String!, $handle: String!, $items: [MenuItemUpdateInput!]!) {
      menuUpdate(id: $id, title: $title, handle: $handle, items: $items) {
        menu {
          id
          title
          items {
            title
            url
          }
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    if menu_map.get("main-menu"):
        res_m = graphql_query(mutation, {
            "id": menu_map["main-menu"],
            "title": "Main menu",
            "handle": "main-menu",
            "items": main_items
        })
        print("\n[+] Main Menu Update Result:", res_m)

    if menu_map.get("footer"):
        res_f = graphql_query(mutation, {
            "id": menu_map["footer"],
            "title": "Footer menu",
            "handle": "footer",
            "items": footer_items
        })
        print("\n[+] Footer Menu Update Result:", res_f)

if __name__ == "__main__":
    main()
