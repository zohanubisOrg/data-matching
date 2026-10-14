import os
import sys
import json
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

# Define clean hierarchy with exact 3-language mapping (English Base, Danish, Vietnamese)
MENU_DEF = [
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
            {"en": "Instant Noodles", "da": "Instantnudler", "vi": "Mì ăn liền", "subcat": "Instant Noodles"},
            {"en": "Dried Noodles", "da": "Tørrede nudler & risnudler", "vi": "Mì & Bún khô", "subcat": "Dried Noodles"},
            {"en": "Japanese & Korean Noodles", "da": "Japanske & koreanske nudler", "vi": "Mì Nhật & Hàn Quốc", "subcat": "Japanese & Korean Noodles"},
            {"en": "Rice Cakes & Tteokbokki", "da": "Riskager & Tteokbokki", "vi": "Bánh gạo & Tteokbokki", "subcat": "Rice Cakes & Tteokbokki"}
        ]
    },
    {
        "en": "Snacks",
        "da": "Snacks",
        "vi": "Đồ ăn vặt",
        "url": "/collections/snacks",
        "type": "HTTP",
        "items": [
            {"en": "Chips & Savory Snacks", "da": "Chips & salte snacks", "vi": "Snack mặn", "subcat": "Chips & Savory Snacks"},
            {"en": "Biscuits & Cookies", "da": "Kiks & småkager", "vi": "Bánh quy", "subcat": "Biscuits & Cookies"},
            {"en": "Cakes & Pastries", "da": "Kager & bagværk", "vi": "Bánh ngọt", "subcat": "Cakes & Pastries"},
            {"en": "Candy & Chocolate", "da": "Slik & chokolade", "vi": "Kẹo & Sô cô la", "subcat": "Candy & Chocolate"},
            {"en": "Nuts & Seeds", "da": "Nødder & frø", "vi": "Hạt & Đậu phộng", "subcat": "Nuts & Seeds"}
        ]
    },
    {
        "en": "Sauces & Soy Sauce",
        "da": "Saucer & Sojasauce",
        "vi": "Nước sốt & Nước tương",
        "url": "/collections/saucer-sojasauce",
        "type": "HTTP",
        "items": [
            {"en": "Soy & Seasoning Sauces", "da": "Sojasauce & kryddersaucer", "vi": "Nước tương & Nước chấm", "subcat": "Soy & Seasoning Sauces"},
            {"en": "Curry & Cooking Sauces", "da": "Karry & madlavningssaucer", "vi": "Sốt nấu & Cà ri", "subcat": "Curry & Cooking Sauces"},
            {"en": "Chili & Hot Sauces", "da": "Chilisauce & stærke saucer", "vi": "Tương ớt & Sốt cay", "subcat": "Chili & Hot Sauces"},
            {"en": "Fish & Seafood Sauces", "da": "Fiskesauce & skaldyrssaucer", "vi": "Nước mắm & Sốt hải sản", "subcat": "Fish & Seafood Sauces"},
            {"en": "Pastes & Fermented Condiments", "da": "Pastaprodukter & fermenterede krydderier", "vi": "Tương đậu & Gia vị lên men", "subcat": "Pastes & Fermented Condiments"}
        ]
    },
    {
        "en": "Spices & Curry",
        "da": "Krydderier & Karry",
        "vi": "Gia vị & Cà ri",
        "url": "/collections/krydderier-karry",
        "type": "HTTP",
        "items": [
            {"en": "Seasoning & Spice Mixes", "da": "Krydderiblandinger", "vi": "Gia vị hỗn hợp", "subcat": "Seasoning & Spice Mixes"},
            {"en": "Whole Spices & Seeds", "da": "Hele krydderier & frø", "vi": "Gia vị nguyên hạt", "subcat": "Whole Spices & Seeds"},
            {"en": "Ground Spices", "da": "Stødte krydderier", "vi": "Gia vị xay", "subcat": "Ground Spices"},
            {"en": "Chili & Pepper", "da": "Chili & peber", "vi": "Ớt & Tiêu", "subcat": "Chili & Pepper"}
        ]
    },
    {
        "en": "Beverages",
        "da": "Drikkevarer",
        "vi": "Đồ uống",
        "url": "/collections/drikkevarer-vin",
        "type": "HTTP",
        "items": [
            {"en": "Tea & Coffee", "da": "Te & kaffe", "vi": "Trà & Cà phê", "subcat": "Tea & Coffee"},
            {"en": "Juice & Fruit Drinks", "da": "Juice & frugtdrikke", "vi": "Nước ép & Nước trái cây", "subcat": "Juice & Fruit Drinks"},
            {"en": "Soft Drinks & Soda", "da": "Sodavand & læskedrikke", "vi": "Nước ngọt có ga", "subcat": "Soft Drinks & Soda"},
            {"en": "Alcoholic Beverages", "da": "Alkoholiske drikkevarer", "vi": "Bia & Rượu", "subcat": "Alcoholic Beverages"}
        ]
    },
    {
        "en": "Rice, Flour & Dry Goods",
        "da": "Ris, Mel & Tørvarer",
        "vi": "Gạo, Bột & Đồ khô",
        "url": "/collections/ris-mel-torvarer",
        "type": "HTTP",
        "items": [
            {"en": "Batter & Breading", "da": "Panering & frituremel", "vi": "Bột chiên giòn", "subcat": "Batter & Breading"},
            {"en": "Asian Baking Mixes", "da": "Asiatiske bagemix", "vi": "Bột làm bánh Á Châu", "subcat": "Asian Baking Mixes"},
            {"en": "Flour & Starch", "da": "Mel & stivelse", "vi": "Bột mì & Tinh bột", "subcat": "Flour & Starch"},
            {"en": "Tapioca Products", "da": "Tapiocaprodukter", "vi": "Bột năng & Trân châu", "subcat": "Tapioca Products"}
        ]
    },
    {
        "en": "Other Asian Specialties",
        "da": "Andre asiatiske varer",
        "vi": "Hàng Á Châu khác",
        "url": "/collections/andre-asiatiske-varer",
        "type": "HTTP",
        "items": [
            {"en": "Canned Vegetables", "da": "Grøntsagskonserves", "vi": "Rau củ đóng hộp", "subcat": "Canned Vegetables"},
            {"en": "Pickled Vegetables", "da": "Syltede grøntsager", "vi": "Rau củ ngâm chua", "subcat": "Pickled Vegetables"},
            {"en": "Tofu & Soy Products", "da": "Tofu & sojaprodukter", "vi": "Đậu hũ & Sản phẩm từ đậu", "subcat": "Tofu & Soy Products"},
            {"en": "Beans & Pulses", "da": "Bønner & bælgfrugter", "vi": "Các loại đậu", "subcat": "Beans & Pulses"}
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

print("MENU_DEF defined with", len(MENU_DEF), "top categories.")
