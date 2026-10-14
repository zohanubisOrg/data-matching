import os
import sys
import json
import time
import urllib.parse

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, ".")
from scripts.setup_full_store_content_and_navigation import graphql_query

def encode_url_param(val: str) -> str:
    return urllib.parse.quote(val)

# Complete clean 3-language hierarchy definitions
MAIN_MENU_ITEMS = [
    {
        "en": "Home",
        "da": "Hjem",
        "vi": "Trang chủ",
        "url": "/",
        "type": "FRONTPAGE",
        "items": []
    },
    {
        "en": "Noodles",
        "da": "Nudler",
        "vi": "Mì & Bún",
        "url": "/collections/nudler",
        "type": "HTTP",
        "items": [
            {"en": "Instant Noodles", "da": "Instantnudler", "vi": "Mì ăn liền", "url": f"/collections/nudler?filter.p.tag={encode_url_param('subcat:Instant Noodles')}"},
            {"en": "Dried Noodles", "da": "Tørrede nudler & risnudler", "vi": "Mì & Bún khô", "url": f"/collections/nudler?filter.p.tag={encode_url_param('subcat:Dried Noodles')}"},
            {"en": "Japanese & Korean Noodles", "da": "Japanske & koreanske nudler", "vi": "Mì Nhật & Hàn Quốc", "url": f"/collections/nudler?filter.p.tag={encode_url_param('subcat:Japanese & Korean Noodles')}"},
            {"en": "Rice Cakes & Tteokbokki", "da": "Riskager & Tteokbokki", "vi": "Bánh gạo & Tteokbokki", "url": f"/collections/nudler?filter.p.tag={encode_url_param('subcat:Rice Cakes & Tteokbokki')}"}
        ]
    },
    {
        "en": "Snacks",
        "da": "Snacks",
        "vi": "Đồ ăn vặt",
        "url": "/collections/snacks",
        "type": "HTTP",
        "items": [
            {"en": "Chips & Savory Snacks", "da": "Chips & salte snacks", "vi": "Snack mặn", "url": f"/collections/snacks?filter.p.tag={encode_url_param('subcat:Chips & Savory Snacks')}"},
            {"en": "Biscuits & Cookies", "da": "Kiks & småkager", "vi": "Bánh quy", "url": f"/collections/snacks?filter.p.tag={encode_url_param('subcat:Biscuits & Cookies')}"},
            {"en": "Cakes & Pastries", "da": "Kager & bagværk", "vi": "Bánh ngọt", "url": f"/collections/snacks?filter.p.tag={encode_url_param('subcat:Cakes & Pastries')}"},
            {"en": "Candy & Chocolate", "da": "Slik & chokolade", "vi": "Kẹo & Sô cô la", "url": f"/collections/snacks?filter.p.tag={encode_url_param('subcat:Candy & Chocolate')}"},
            {"en": "Nuts & Seeds", "da": "Nødder & frø", "vi": "Hạt & Đậu phộng", "url": f"/collections/snacks?filter.p.tag={encode_url_param('subcat:Nuts & Seeds')}"}
        ]
    },
    {
        "en": "Sauces & Soy Sauce",
        "da": "Saucer & Sojasauce",
        "vi": "Nước sốt & Nước tương",
        "url": "/collections/saucer-sojasauce",
        "type": "HTTP",
        "items": [
            {"en": "Soy & Seasoning Sauces", "da": "Sojasauce & kryddersaucer", "vi": "Nước tương & Nước chấm", "url": f"/collections/saucer-sojasauce?filter.p.tag={encode_url_param('subcat:Soy & Seasoning Sauces')}"},
            {"en": "Curry & Cooking Sauces", "da": "Karry & madlavningssaucer", "vi": "Sốt nấu & Cà ri", "url": f"/collections/saucer-sojasauce?filter.p.tag={encode_url_param('subcat:Curry & Cooking Sauces')}"},
            {"en": "Chili & Hot Sauces", "da": "Chilisauce & stærke saucer", "vi": "Tương ớt & Sốt cay", "url": f"/collections/saucer-sojasauce?filter.p.tag={encode_url_param('subcat:Chili & Hot Sauces')}"},
            {"en": "Fish & Seafood Sauces", "da": "Fiskesauce & skaldyrssaucer", "vi": "Nước mắm & Sốt hải sản", "url": f"/collections/saucer-sojasauce?filter.p.tag={encode_url_param('subcat:Fish & Seafood Sauces')}"},
            {"en": "Pastes & Fermented Condiments", "da": "Pastaprodukter & fermenterede krydderier", "vi": "Tương đậu & Gia vị lên men", "url": f"/collections/saucer-sojasauce?filter.p.tag={encode_url_param('subcat:Pastes & Fermented Condiments')}"}
        ]
    },
    {
        "en": "Spices & Curry",
        "da": "Krydderier & Karry",
        "vi": "Gia vị & Cà ri",
        "url": "/collections/krydderier-karry",
        "type": "HTTP",
        "items": [
            {"en": "Seasoning & Spice Mixes", "da": "Krydderiblandinger", "vi": "Gia vị hỗn hợp", "url": f"/collections/krydderier-karry?filter.p.tag={encode_url_param('subcat:Seasoning & Spice Mixes')}"},
            {"en": "Whole Spices & Seeds", "da": "Hele krydderier & frø", "vi": "Gia vị nguyên hạt", "url": f"/collections/krydderier-karry?filter.p.tag={encode_url_param('subcat:Whole Spices & Seeds')}"},
            {"en": "Ground Spices", "da": "Stødte krydderier", "vi": "Gia vị xay", "url": f"/collections/krydderier-karry?filter.p.tag={encode_url_param('subcat:Ground Spices')}"},
            {"en": "Chili & Pepper", "da": "Chili & peber", "vi": "Ớt & Tiêu", "url": f"/collections/krydderier-karry?filter.p.tag={encode_url_param('subcat:Chili & Pepper')}"}
        ]
    },
    {
        "en": "Beverages",
        "da": "Drikkevarer",
        "vi": "Đồ uống",
        "url": "/collections/drikkevarer-vin",
        "type": "HTTP",
        "items": [
            {"en": "Tea & Coffee", "da": "Te & kaffe", "vi": "Trà & Cà phê", "url": f"/collections/drikkevarer-vin?filter.p.tag={encode_url_param('subcat:Tea & Coffee')}"},
            {"en": "Juice & Fruit Drinks", "da": "Juice & frugtdrikke", "vi": "Nước ép & Nước trái cây", "url": f"/collections/drikkevarer-vin?filter.p.tag={encode_url_param('subcat:Juice & Fruit Drinks')}"},
            {"en": "Soft Drinks & Soda", "da": "Sodavand & læskedrikke", "vi": "Nước ngọt có ga", "url": f"/collections/drikkevarer-vin?filter.p.tag={encode_url_param('subcat:Soft Drinks & Soda')}"},
            {"en": "Alcoholic Beverages", "da": "Alkoholiske drikkevarer", "vi": "Bia & Rượu", "url": f"/collections/drikkevarer-vin?filter.p.tag={encode_url_param('subcat:Alcoholic Beverages')}"}
        ]
    },
    {
        "en": "Rice, Flour & Dry Goods",
        "da": "Ris, Mel & Tørvarer",
        "vi": "Gạo, Bột & Đồ khô",
        "url": "/collections/ris-mel-torvarer",
        "type": "HTTP",
        "items": [
            {"en": "Batter & Breading", "da": "Panering & frituremel", "vi": "Bột chiên giòn", "url": f"/collections/ris-mel-torvarer?filter.p.tag={encode_url_param('subcat:Batter & Breading')}"},
            {"en": "Asian Baking Mixes", "da": "Asiatiske bagemix", "vi": "Bột làm bánh Á Châu", "url": f"/collections/ris-mel-torvarer?filter.p.tag={encode_url_param('subcat:Asian Baking Mixes')}"},
            {"en": "Flour & Starch", "da": "Mel & stivelse", "vi": "Bột mì & Tinh bột", "url": f"/collections/ris-mel-torvarer?filter.p.tag={encode_url_param('subcat:Flour & Starch')}"},
            {"en": "Tapioca Products", "da": "Tapiocaprodukter", "vi": "Bột năng & Trân châu", "url": f"/collections/ris-mel-torvarer?filter.p.tag={encode_url_param('subcat:Tapioca Products')}"}
        ]
    },
    {
        "en": "Other Asian Specialties",
        "da": "Andre asiatiske varer",
        "vi": "Hàng Á Châu khác",
        "url": "/collections/andre-asiatiske-varer",
        "type": "HTTP",
        "items": [
            {"en": "Canned Vegetables", "da": "Grøntsagskonserves", "vi": "Rau củ đóng hộp", "url": f"/collections/andre-asiatiske-varer?filter.p.tag={encode_url_param('subcat:Canned Vegetables')}"},
            {"en": "Pickled Vegetables", "da": "Syltede grøntsager", "vi": "Rau củ ngâm chua", "url": f"/collections/andre-asiatiske-varer?filter.p.tag={encode_url_param('subcat:Pickled Vegetables')}"},
            {"en": "Tofu & Soy Products", "da": "Tofu & sojaprodukter", "vi": "Đậu hũ & Sản phẩm từ đậu", "url": f"/collections/andre-asiatiske-varer?filter.p.tag={encode_url_param('subcat:Tofu & Soy Products')}"},
            {"en": "Beans & Pulses", "da": "Bønner & bælgfrugter", "vi": "Các loại đậu", "url": f"/collections/andre-asiatiske-varer?filter.p.tag={encode_url_param('subcat:Beans & Pulses')}"}
        ]
    },
    {
        "en": "About Us",
        "da": "Om os",
        "vi": "Giới thiệu",
        "url": "/pages/om-os",
        "type": "HTTP",
        "items": []
    },
    {
        "en": "Contact",
        "da": "Kontakt",
        "vi": "Liên hệ",
        "url": "/pages/kontakt-os",
        "type": "HTTP",
        "items": []
    }
]

FOOTER_MENU_TRANSLATIONS = {
    "Om Rabuta": {"da": "Om Rabuta", "en": "About Rabuta", "vi": "Về Rabuta"},
    "Kontakt os": {"da": "Kontakt os", "en": "Contact Us", "vi": "Liên hệ với chúng tôi"},
    "Levering & Fragt": {"da": "Levering & Fragt", "en": "Delivery & Shipping", "vi": "Giao hàng & Vận chuyển"},
    "Handelsbetingelser": {"da": "Handelsbetingelser", "en": "Terms & Conditions", "vi": "Điều khoản dịch vụ"},
    "Returpolitik": {"da": "Returpolitik", "en": "Return Policy", "vi": "Chính sách đổi trả"},
    "Privatlivspolitik": {"da": "Privatlivspolitik", "en": "Privacy Policy", "vi": "Chính sách bảo mật"}
}

COLLECTION_TRANSLATIONS = {
    "gid://shopify/Collection/688054665601": {"da": "Snacks", "en": "Snacks", "vi": "Đồ ăn vặt"},
    "gid://shopify/Collection/693648556417": {"da": "Nudler", "en": "Noodles", "vi": "Mì & Bún"},
    "gid://shopify/Collection/694067495297": {"da": "Saucer & Sojasauce", "en": "Sauces & Soy Sauce", "vi": "Nước sốt & Nước tương"},
    "gid://shopify/Collection/694070575489": {"da": "Andre asiatiske varer", "en": "Other Asian Specialties", "vi": "Hàng Á Châu khác"},
    "gid://shopify/Collection/694070608257": {"da": "Krydderier & Karry", "en": "Spices & Curry", "vi": "Gia vị & Cà ri"},
    "gid://shopify/Collection/694070673793": {"da": "Konserves & Kokosmælk", "en": "Canned Goods & Coconut Milk", "vi": "Đồ hộp & Nước cốt dừa"},
    "gid://shopify/Collection/694070706561": {"da": "Drikkevarer", "en": "Beverages", "vi": "Đồ uống & Trà"},
    "gid://shopify/Collection/694396944769": {"da": "Ris, Mel & Tørvarer", "en": "Rice, Flour & Dry Goods", "vi": "Gạo, Bột & Đồ khô"}
}

def register_translation(resource_id, key, value, locale, digest):
    mutation = """
    mutation translationsRegister($resourceId: ID!, $translations: [TranslationInput!]!) {
      translationsRegister(resourceId: $resourceId, translations: $translations) {
        userErrors {
          field
          message
        }
        translations {
          key
          value
          locale
        }
      }
    }
    """
    vars = {
        "resourceId": resource_id,
        "translations": [
            {
                "key": key,
                "value": value,
                "locale": locale,
                "translatableContentDigest": digest
            }
        ]
    }
    res = graphql_query(mutation, variables=vars)
    errs = res.get("data", {}).get("translationsRegister", {}).get("userErrors", [])
    if errs:
        print(f"    [!] Error registering {locale} for {resource_id} ({key}): {errs}")
        return False
    return True

def step1_update_main_menu():
    print("[*] Step 1: Updating main-menu with pure clean English base titles...")
    # Find main menu ID
    menus_res = graphql_query("""
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
    """)
    main_menu_id = None
    for m in menus_res.get("data", {}).get("menus", {}).get("edges", []):
        if m["node"]["handle"] == "main-menu":
            main_menu_id = m["node"]["id"]
            break

    if not main_menu_id:
        raise RuntimeError("Main menu not found!")

    # Format items for GraphQL menuUpdate
    formatted_items = []
    for top in MAIN_MENU_ITEMS:
        sub_items = []
        for sub in top.get("items", []):
            sub_items.append({
                "title": sub["en"],  # Clean English base
                "type": "HTTP",
                "url": sub["url"]
            })
        top_entry = {
            "title": top["en"],      # Clean English base
            "type": top["type"],
            "url": top["url"]
        }
        if sub_items:
            top_entry["items"] = sub_items
        formatted_items.append(top_entry)

    update_mutation = """
    mutation menuUpdate($id: ID!, $title: String!, $items: [MenuItemUpdateInput!]!) {
      menuUpdate(id: $id, title: $title, items: $items) {
        menu {
          id
          title
        }
        userErrors {
          field
          message
        }
      }
    }
    """
    res = graphql_query(update_mutation, variables={
        "id": main_menu_id,
        "title": "Main menu",
        "items": formatted_items
    })
    errs = res.get("data", {}).get("menuUpdate", {}).get("userErrors", [])
    if errs:
        raise RuntimeError(f"menuUpdate failed: {errs}")
    print("[+] Main menu successfully updated with clean base titles!")
    return main_menu_id

def step2_translate_links():
    print("\n[*] Step 2: Fetching translatable LINK resources and registering translations...")
    # Map title -> dict of translations
    # Build lookup table from MAIN_MENU_ITEMS
    title_to_trans = {}
    for top in MAIN_MENU_ITEMS:
        title_to_trans[top["en"]] = {"da": top["da"], "vi": top["vi"]}
        for sub in top.get("items", []):
            title_to_trans[sub["en"]] = {"da": sub["da"], "vi": sub["vi"]}

    # Also add Footer items
    for title, trans in FOOTER_MENU_TRANSLATIONS.items():
        title_to_trans[title] = trans

    # Fetch all translatable LINKs
    links = []
    has_next = True
    cursor = None
    while has_next:
        after_clause = f', after: "{cursor}"' if cursor else ''
        q = f"""
        {{
          translatableResources(first: 50, resourceType: LINK {after_clause}) {{
            edges {{
              cursor
              node {{
                resourceId
                translatableContent {{
                  key
                  value
                  digest
                  locale
                }}
              }}
            }}
            pageInfo {{
              hasNextPage
            }}
          }}
        }}
        """
        res = graphql_query(q)
        edges = res.get("data", {}).get("translatableResources", {}).get("edges", [])
        for e in edges:
            links.append(e["node"])
            cursor = e["cursor"]
        has_next = res.get("data", {}).get("translatableResources", {}).get("pageInfo", {}).get("hasNextPage", False)

    print(f"    - Found {len(links)} translatable Link items")

    success_count = 0
    for l in links:
        res_id = l["resourceId"]
        tc_list = l.get("translatableContent", [])
        for tc in tc_list:
            if tc["key"] == "title":
                title_val = tc["value"]
                digest = tc["digest"]
                if title_val in title_to_trans:
                    trans = title_to_trans[title_val]
                    # Register da
                    if "da" in trans:
                        register_translation(res_id, "title", trans["da"], "da", digest)
                    # Register vi
                    if "vi" in trans:
                        register_translation(res_id, "title", trans["vi"], "vi", digest)
                    success_count += 1
                    print(f"    ✓ Linked '{title_val}' -> DA: '{trans.get('da')}', VI: '{trans.get('vi')}'")

    print(f"[+] Finished translating {success_count} navigation menu items!")

def step3_translate_theme_sections():
    print("\n[*] Step 3: Translating Theme Sections (Footer & Header)...")
    theme_id = "189930996097"
    footer_res_id = f"gid://shopify/OnlineStoreThemeSectionGroup/footer-group?theme_id={theme_id}"
    
    # Query current translatable content for footer
    q = f"""
    {{
      translatableResource(resourceId: "{footer_res_id}") {{
        resourceId
        translatableContent {{
          key
          value
          digest
        }}
      }}
    }}
    """
    res = graphql_query(q)
    tc = res.get("data", {}).get("translatableResource", {}).get("translatableContent", [])
    for item in tc:
        k = item["key"]
        v = item["value"]
        d = item["digest"]
        if "newsletter_heading" in k:
            # Base is "Subscribe to our emails"
            register_translation(footer_res_id, k, "Tilmeld dig vores e-mails", "da", d)
            register_translation(footer_res_id, k, "Đăng ký nhận bản tin", "vi", d)
            print("    ✓ Footer newsletter translated (DA: Tilmeld dig vores e-mails, VI: Đăng ký nhận bản tin)")
        elif "heading" in k and ("Kontakt" in v or "Contact" in v):
            register_translation(footer_res_id, k, "Kontakt os", "da", d)
            register_translation(footer_res_id, k, "Liên hệ với chúng tôi", "vi", d)
            register_translation(footer_res_id, k, "Contact Us", "en", d)
            print("    ✓ Footer contact heading translated (DA: Kontakt os, VI: Liên hệ với chúng tôi, EN: Contact Us)")

    # Header announcement bar
    header_res_id = f"gid://shopify/OnlineStoreThemeSectionGroup/header-group?theme_id={theme_id}"
    q_h = f"""
    {{
      translatableResource(resourceId: "{header_res_id}") {{
        resourceId
        translatableContent {{
          key
          value
          digest
        }}
      }}
    }}
    """
    res_h = graphql_query(q_h)
    tc_h = res_h.get("data", {}).get("translatableResource", {}).get("translatableContent", [])
    for item in tc_h:
        k = item["key"]
        d = item["digest"]
        if "announcement-bar" in k:
            register_translation(header_res_id, k, "Velkommen til Rabuta Asian Supermarket", "da", d)
            register_translation(header_res_id, k, "Chào mừng bạn đến với Rabuta Asian Supermarket", "vi", d)
            register_translation(header_res_id, k, "Welcome to Rabuta Asian Supermarket", "en", d)
            print("    ✓ Header announcement translated!")

def step4_translate_collections():
    print("\n[*] Step 4: Translating Collections...")
    for col_id, trans in COLLECTION_TRANSLATIONS.items():
        q = f"""
        {{
          translatableResource(resourceId: "{col_id}") {{
            resourceId
            translatableContent {{
              key
              value
              digest
            }}
          }}
        }}
        """
        res = graphql_query(q)
        tc = res.get("data", {}).get("translatableResource", {}).get("translatableContent", [])
        for item in tc:
            if item["key"] == "title":
                d = item["digest"]
                if "da" in trans:
                    register_translation(col_id, "title", trans["da"], "da", d)
                if "vi" in trans:
                    register_translation(col_id, "title", trans["vi"], "vi", d)
                print(f"    ✓ Collection {col_id} translated -> DA: '{trans.get('da')}', VI: '{trans.get('vi')}'")

def main():
    print("================================================================")
    print("      SHOPIFY MULTILINGUAL LOCALIZATION PIPELINE                ")
    print("      (Clean 1-Language Mode: Danish, English, Vietnamese)      ")
    print("================================================================")
    step1_update_main_menu()
    time.sleep(1)
    step2_links = step2_translate_links()
    step3_translate_theme_sections()
    step4_translate_collections()
    print("\n================================================================")
    print("  ALL TRANSLATIONS SUCCESSFULLY CONFIGURED ON LIVE STORE!       ")
    print("================================================================")

if __name__ == "__main__":
    main()
