import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import urllib.parse
sys.path.insert(0, ".")
from scripts.setup_full_store_content_and_navigation import graphql_query

def encode_url_param(val: str) -> str:
    return urllib.parse.quote(val)

def build_nested_menu():
    print("[*] Fetching Menus from Shopify Store...")
    get_menus_query = """
    {
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
    res = graphql_query(get_menus_query)
    menus = res.get("data", {}).get("menus", {}).get("edges", [])

    main_menu_id = None
    for m in menus:
        node = m["node"]
        if node["handle"] == "main-menu":
            main_menu_id = node["id"]
            break

    if not main_menu_id:
        print("[!] Main menu not found!")
        return

    print(f"    - Found Main Menu ID: {main_menu_id}")

    # Build Nested Items (Level 1 with Level 2 subcategories)
    menu_items = [
        {
            "title": "Hjem",
            "type": "FRONTPAGE",
            "url": "/",
            "items": []
        },
        {
            "title": "Nudler",
            "type": "HTTP",
            "url": "/collections/nudler",
            "items": [
                {"title": "Instant Noodles (Mì ăn liền)", "type": "HTTP", "url": f"/collections/nudler?filter.p.tag={encode_url_param('subcat:Instant Noodles')}"},
                {"title": "Dried Noodles (Mì/bún khô)", "type": "HTTP", "url": f"/collections/nudler?filter.p.tag={encode_url_param('subcat:Dried Noodles')}"},
                {"title": "Japanese & Korean Noodles", "type": "HTTP", "url": f"/collections/nudler?filter.p.tag={encode_url_param('subcat:Japanese & Korean Noodles')}"},
                {"title": "Rice Cakes & Tteokbokki", "type": "HTTP", "url": f"/collections/nudler?filter.p.tag={encode_url_param('subcat:Rice Cakes & Tteokbokki')}"}
            ]
        },
        {
            "title": "Snacks",
            "type": "HTTP",
            "url": "/collections/snacks",
            "items": [
                {"title": "Chips & Savory Snacks (Snack mặn)", "type": "HTTP", "url": f"/collections/snacks?filter.p.tag={encode_url_param('subcat:Chips & Savory Snacks')}"},
                {"title": "Biscuits & Cookies (Bánh quy)", "type": "HTTP", "url": f"/collections/snacks?filter.p.tag={encode_url_param('subcat:Biscuits & Cookies')}"},
                {"title": "Cakes & Pastries (Bánh ngọt)", "type": "HTTP", "url": f"/collections/snacks?filter.p.tag={encode_url_param('subcat:Cakes & Pastries')}"},
                {"title": "Candy & Chocolate (Kẹo & Socola)", "type": "HTTP", "url": f"/collections/snacks?filter.p.tag={encode_url_param('subcat:Candy & Chocolate')}"},
                {"title": "Nuts & Seeds (Hạt & Đậu phộng)", "type": "HTTP", "url": f"/collections/snacks?filter.p.tag={encode_url_param('subcat:Nuts & Seeds')}"}
            ]
        },
        {
            "title": "Saucer & Sojasauce",
            "type": "HTTP",
            "url": "/collections/saucer-sojasauce",
            "items": [
                {"title": "Soy & Seasoning Sauces (Nước tương)", "type": "HTTP", "url": f"/collections/saucer-sojasauce?filter.p.tag={encode_url_param('subcat:Soy & Seasoning Sauces')}"},
                {"title": "Curry & Cooking Sauces (Sốt nấu & Cà ri)", "type": "HTTP", "url": f"/collections/saucer-sojasauce?filter.p.tag={encode_url_param('subcat:Curry & Cooking Sauces')}"},
                {"title": "Chili & Hot Sauces (Tương ớt)", "type": "HTTP", "url": f"/collections/saucer-sojasauce?filter.p.tag={encode_url_param('subcat:Chili & Hot Sauces')}"},
                {"title": "Fish & Seafood Sauces (Nước mắm)", "type": "HTTP", "url": f"/collections/saucer-sojasauce?filter.p.tag={encode_url_param('subcat:Fish & Seafood Sauces')}"},
                {"title": "Pastes & Fermented Condiments (Tương đậu)", "type": "HTTP", "url": f"/collections/saucer-sojasauce?filter.p.tag={encode_url_param('subcat:Pastes & Fermented Condiments')}"}
            ]
        },
        {
            "title": "Krydderier & Karry",
            "type": "HTTP",
            "url": "/collections/krydderier-karry",
            "items": [
                {"title": "Seasoning & Spice Mixes (Gia vị hỗn hợp)", "type": "HTTP", "url": f"/collections/krydderier-karry?filter.p.tag={encode_url_param('subcat:Seasoning & Spice Mixes')}"},
                {"title": "Whole Spices & Seeds (Gia vị hạt nguyên)", "type": "HTTP", "url": f"/collections/krydderier-karry?filter.p.tag={encode_url_param('subcat:Whole Spices & Seeds')}"},
                {"title": "Ground Spices (Gia vị xay)", "type": "HTTP", "url": f"/collections/krydderier-karry?filter.p.tag={encode_url_param('subcat:Ground Spices')}"},
                {"title": "Chili & Pepper (Tiêu & Ớt)", "type": "HTTP", "url": f"/collections/krydderier-karry?filter.p.tag={encode_url_param('subcat:Chili & Pepper')}"}
            ]
        },
        {
            "title": "Drikkevarer",
            "type": "HTTP",
            "url": "/collections/drikkevarer-vin",
            "items": [
                {"title": "Tea & Coffee (Trà & Cà phê)", "type": "HTTP", "url": f"/collections/drikkevarer-vin?filter.p.tag={encode_url_param('subcat:Tea & Coffee')}"},
                {"title": "Juice & Fruit Drinks (Nước trái cây)", "type": "HTTP", "url": f"/collections/drikkevarer-vin?filter.p.tag={encode_url_param('subcat:Juice & Fruit Drinks')}"},
                {"title": "Soft Drinks & Soda (Nước ngọt)", "type": "HTTP", "url": f"/collections/drikkevarer-vin?filter.p.tag={encode_url_param('subcat:Soft Drinks')}"},
                {"title": "Alcoholic Beverages (Bia & Rượu)", "type": "HTTP", "url": f"/collections/drikkevarer-vin?filter.p.tag={encode_url_param('subcat:Alcoholic Beverages')}"}
            ]
        },
        {
            "title": "Ris, Mel & Tørvarer",
            "type": "HTTP",
            "url": "/collections/ris-mel-torvarer",
            "items": [
                {"title": "Batter & Breading (Bột chiên)", "type": "HTTP", "url": f"/collections/ris-mel-torvarer?filter.p.tag={encode_url_param('subcat:Batter & Breading')}"},
                {"title": "Asian Baking Mixes (Bột bánh Á Châu)", "type": "HTTP", "url": f"/collections/ris-mel-torvarer?filter.p.tag={encode_url_param('subcat:Asian Baking Mixes')}"},
                {"title": "Flour & Starch (Bột mì & Tinh bột)", "type": "HTTP", "url": f"/collections/ris-mel-torvarer?filter.p.tag={encode_url_param('subcat:Flour & Starch')}"},
                {"title": "Tapioca Products (Bột năng & Trân châu)", "type": "HTTP", "url": f"/collections/ris-mel-torvarer?filter.p.tag={encode_url_param('subcat:Tapioca Products')}"}
            ]
        },
        {
            "title": "Andre asiatiske varer",
            "type": "HTTP",
            "url": "/collections/andre-asiatiske-varer",
            "items": [
                {"title": "Canned Vegetables (Rau củ đóng hộp)", "type": "HTTP", "url": f"/collections/andre-asiatiske-varer?filter.p.tag={encode_url_param('subcat:Canned Vegetables')}"},
                {"title": "Pickled Vegetables (Dưa chua)", "type": "HTTP", "url": f"/collections/andre-asiatiske-varer?filter.p.tag={encode_url_param('subcat:Pickled & Fermented Vegetables')}"},
                {"title": "Tofu & Soy Products (Đậu hũ)", "type": "HTTP", "url": f"/collections/andre-asiatiske-varer?filter.p.tag={encode_url_param('subcat:Tofu & Soy Products')}"},
                {"title": "Beans & Pulses (Các loại đậu)", "type": "HTTP", "url": f"/collections/andre-asiatiske-varer?filter.p.tag={encode_url_param('subcat:Beans & Pulses')}"}
            ]
        },
        {
            "title": "Om os",
            "type": "HTTP",
            "url": "/pages/om-os",
            "items": []
        },
        {
            "title": "Kontakt",
            "type": "HTTP",
            "url": "/pages/kontakt-os",
            "items": []
        }
    ]

    update_mutation = """
    mutation menuUpdate($id: ID!, $title: String!, $handle: String!, $items: [MenuItemUpdateInput!]!) {
      menuUpdate(id: $id, title: $title, handle: $handle, items: $items) {
        menu {
          id
          title
          items {
            title
            url
            items {
              title
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

    print("[*] Updating Main Menu with Nested 2-Tier Hierarchy via GraphQL...")
    res_update = graphql_query(update_mutation, {
        "id": main_menu_id,
        "title": "Main menu",
        "handle": "main-menu",
        "items": menu_items
    })

    user_errors = res_update.get("data", {}).get("menuUpdate", {}).get("userErrors", [])
    if user_errors:
        print(f"[!] UserErrors updating menu: {user_errors}")
    else:
        updated_menu = res_update.get("data", {}).get("menuUpdate", {}).get("menu", {})
        print(f"[+] Successfully updated Main Menu: '{updated_menu.get('title')}'")
        for item in updated_menu.get("items", []):
            child_cnt = len(item.get("items", []))
            print(f"    - {item['title']} ({child_cnt} nested sub-items)")

if __name__ == "__main__":
    build_nested_menu()
