import urllib.request
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("SHOPIFY_ADMIN_ACCESS_TOKEN")
url = "https://rabuta.myshopify.com/admin/api/2024-01/graphql.json"

def gql(query, variables=None):
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": token
        }
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def register_translation(resource_id, locale, translations_list):
    """
    translations_list: list of dicts with 'key', 'value', 'digest', 'locale'
    """
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
    res = gql(mutation, {
        "resourceId": resource_id,
        "translations": [
            {
                "key": t["key"],
                "value": t["value"],
                "translatableContentDigest": t["digest"],
                "locale": locale
            }
            for t in translations_list
        ]
    })
    errors = res.get("data", {}).get("translationsRegister", {}).get("userErrors", [])
    if errors:
        print(f"    [Error] {locale} for {resource_id}: {errors}")
    else:
        print(f"    [Success] {locale} registered for {resource_id}")
    return res

# 1. TRANSLATIONS DICTIONARIES
# ==========================================
# Link translations: match base title -> translation in [da, vi, th]
LINK_TRANSLATIONS = {
    "Hjem": {
        "da": "Hjem",
        "vi": "Trang chủ",
        "th": "หน้าแรก"
    },
    "Home": {
        "da": "Hjem",
        "vi": "Trang chủ",
        "th": "หน้าแรก"
    },
    "Nudler": {
        "da": "Nudler & Pasta",
        "vi": "Mì & Bún Á Châu",
        "th": "บะหมี่และก๋วยเตี๋ยว"
    },
    "Snacks": {
        "da": "Snacks & Chips",
        "vi": "Bánh kẹo & Đồ ăn vặt",
        "th": "ขนมและของทานเล่น"
    },
    "Saucer & Sojasauce": {
        "da": "Saucer & Sojasauce",
        "vi": "Nước xốt & Nước tương",
        "th": "ซอสปรุงรสและซีอิ๊ว"
    },
    "Saucer": {
        "da": "Saucer & Sojasauce",
        "vi": "Nước xốt & Nước tương",
        "th": "ซอสปรุงรสและซีอิ๊ว"
    },
    "Krydderier & Karry": {
        "da": "Krydderier & Karrypasta",
        "vi": "Gia vị & Cà ri",
        "th": "เครื่องเทศและพริกแกง"
    },
    "Krydderier": {
        "da": "Krydderier & Karrypasta",
        "vi": "Gia vị & Cà ri",
        "th": "เครื่องเทศและพริกแกง"
    },
    "Drikkevarer": {
        "da": "Drikkevarer & Te",
        "vi": "Đồ uống & Trà Á Châu",
        "th": "เครื่องดื่มและชา"
    },
    "Drikkevarer & Vin": {
        "da": "Drikkevarer & Te",
        "vi": "Đồ uống & Trà Á Châu",
        "th": "เครื่องดื่มและชา"
    },
    "Konserves & Kokosmælk": {
        "da": "Konserves & Kokosmælk",
        "vi": "Đồ hộp & Nước cốt dừa",
        "th": "อาหารกระป๋องและกะทิ"
    },
    "Konserves": {
        "da": "Konserves & Kokosmælk",
        "vi": "Đồ hộp & Nước cốt dừa",
        "th": "อาหารกระป๋องและกะทิ"
    },
    "Ris, Mel & Tørvarer": {
        "da": "Ris, Mel & Tørvarer",
        "vi": "Gạo, Bột & Đồ khô",
        "th": "ข้าว แป้ง และของแห้ง"
    },
    "Andre asiatiske varer": {
        "da": "Andre asiatiske varer",
        "vi": "Sản phẩm Á châu khác",
        "th": "สินค้าเอเชียอื่นๆ"
    },
    "Diverser": {
        "da": "Andre asiatiske varer",
        "vi": "Sản phẩm Á châu khác",
        "th": "สินค้าเอเชียอื่นๆ"
    },
    "Om os": {
        "da": "Om os",
        "vi": "Về chúng tôi",
        "th": "เกี่ยวกับเรา"
    },
    "Om Rabuta": {
        "da": "Om Rabuta",
        "vi": "Giới thiệu Rabuta",
        "th": "เกี่ยวกับราบูตะ"
    },
    "Kontakt": {
        "da": "Kontakt",
        "vi": "Liên hệ",
        "th": "ติดต่อเรา"
    },
    "Kontakt os": {
        "da": "Kontakt os",
        "vi": "Liên hệ chúng tôi",
        "th": "ติดต่อเรา"
    },
    "Levering & Fragt": {
        "da": "Levering & Fragt",
        "vi": "Giao hàng & Vận chuyển",
        "th": "การจัดส่งสินค้า"
    },
    "Handelsbetingelser": {
        "da": "Handelsbetingelser",
        "vi": "Điều khoản dịch vụ",
        "th": "ข้อกำหนดและเงื่อนไข"
    },
    "Returpolitik": {
        "da": "Retur- og refusionspolitik",
        "vi": "Chính sách hoàn trả & Đổi hàng",
        "th": "นโยบายการคืนสินค้าและคืนเงิน"
    },
    "Privatlivspolitik": {
        "da": "Privatlivspolitik & Cookies",
        "vi": "Chính sách bảo mật",
        "th": "นโยบายความเป็นส่วนตัว"
    }
}

# 2. TRANSLATE ALL LINKS (MENU ITEMS)
print("=== 1. SYNCING LINK (MENU ITEMS) TRANSLATIONS ===")
links_res = gql("""
{
  translatableResources(first: 50, resourceType: LINK) {
    nodes {
      resourceId
      translatableContent {
        key
        value
        digest
      }
    }
  }
}
""")

for node in links_res.get("data", {}).get("translatableResources", {}).get("nodes", []):
    resource_id = node["resourceId"]
    tc_map = {item["key"]: item for item in node.get("translatableContent", [])}
    title_tc = tc_map.get("title")
    if not title_tc:
        continue
    
    base_title = title_tc["value"].strip()
    trans_map = LINK_TRANSLATIONS.get(base_title)
    if not trans_map:
        # Check case-insensitive or partial
        for k, v in LINK_TRANSLATIONS.items():
            if k.lower() == base_title.lower():
                trans_map = v
                break
    
    if trans_map:
        print(f"Processing Link: '{base_title}' ({resource_id})")
        for loc in ["da", "vi", "th"]:
            if loc in trans_map:
                t_val = trans_map[loc]
                register_translation(resource_id, loc, [{"key": "title", "value": t_val, "digest": title_tc["digest"]}])
    else:
        print(f"Skipping link '{base_title}' (No mapping defined)")

print("\nLink translation sync completed.")
