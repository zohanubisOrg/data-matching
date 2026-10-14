import urllib.request
import json
import os
import sys

# Ensure UTF-8 output on Windows
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
    translations_list: list of dicts with 'key', 'value', 'digest'
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
        print(f"    [Error] {locale} for {resource_id}: {errors}", flush=True)
    else:
        print(f"    [Success] {locale} registered for {resource_id} ({[t['key'] for t in translations_list]})", flush=True)
    return res


# ==============================================================================
# 1. COLLECTIONS DATA (8 Standard Collections)
# ==============================================================================
COLLECTIONS_DATA = {
    "nudler": {
        "title": {
            "en": "Noodles & Instant Ramen",
            "da": "Nudler & Asiatisk Pasta",
            "vi": "Mì, Bún & Phở Á Châu",
            "th": "บะหมี่และก๋วยเตี๋ยว"
        },
        "description": {
            "en": "<p>Discover our wide selection of authentic Asian instant noodles, ramen, rice noodles, udon, and vermicelli from Vietnam, Thailand, Korea, and Japan.</p>",
            "da": "<p>Udforsk vores store udvalg af autentiske asiatiske instant nudler, ramen, risnudler, udon og glasnudler fra Vietnam, Thailand, Korea og Japan.</p>",
            "vi": "<p>Khám phá bộ sưu tập mì ăn liền, bún, phở, miến khô, mì ramen và udon thượng hạng nhập khẩu chính hãng từ Việt Nam, Thái Lan, Hàn Quốc và Nhật Bản.</p>",
            "th": "<p>พบกับบะหมี่กึ่งสำเร็จรูป ราเมน เส้นก๋วยเตี๋ยว เส้นหมี่ และวุ้นเส้นคุณภาพเยี่ยมจากเวียดนาม ไทย เกาหลี และญี่ปุ่น</p>"
        }
    },
    "snacks": {
        "title": {
            "en": "Asian Snacks & Sweets",
            "da": "Asiatiske Snacks & Søde Sager",
            "vi": "Bánh kẹo & Đồ ăn vặt Á Châu",
            "th": "ขนมและของทานเล่น"
        },
        "description": {
            "en": "<p>Authentic Asian rice crackers, seaweed snacks, shrimp chips, mochi, candies, and traditional treats.</p>",
            "da": "<p>Autentiske asiatiske riskiks, tangsnacks, rejechips, mochi, slik og traditionelle asiatiske lækkerier.</p>",
            "vi": "<p>Các loại bánh kẹo, snack rong biển giòn rụm, bánh phồng tôm, bánh gạo, mochi và đồ ăn vặt hấp dẫn từ châu Á.</p>",
            "th": "<p>ขนมขบเคี้ยว สาหร่ายทอดกรอบ ข้าวเกรียบกุ้ง โมจิ และขนมหวานต้นตำรับจากทั่วเอเชีย</p>"
        }
    },
    "saucer-sojasauce": {
        "title": {
            "en": "Sauces & Soy Sauce",
            "da": "Saucer & Sojasauce",
            "vi": "Nước xốt & Nước tương",
            "th": "ซอสปรุงรสและซีอิ๊ว"
        },
        "description": {
            "en": "<p>Premium soy sauce, oyster sauce, fish sauce, sriracha chili sauces, dipping sauces, and authentic cooking pastes.</p>",
            "da": "<p>Kvalitetssojasauce, østerssauce, autentisk fiskesauce, sriracha chilisaucer, dips og uundværlige smagsgivere til det asiatiske køkken.</p>",
            "vi": "<p>Các loại nước mắm truyền thống Phú Quốc, nước tương hảo hạng, dầu hào, tương ớt Sriracha và xốt chấm đặc trưng.</p>",
            "th": "<p>ซีอิ๊วขาว น้ำมันหอย น้ำปลาแท้ ซอสพริกศรีราชา และซอสปรุงรสชั้นนำสำหรับครัวเอเชีย</p>"
        }
    },
    "krydderier-karry": {
        "title": {
            "en": "Spices & Curry Pastes",
            "da": "Krydderier & Karrypasta",
            "vi": "Gia vị & Cà ri Á Châu",
            "th": "เครื่องเทศและพริกแกง"
        },
        "description": {
            "en": "<p>Authentic curry pastes (green, red, yellow, massaman, panang), spices, marinades, and seasoning mixes.</p>",
            "da": "<p>Autentiske karrypastaer (grøn, rød, gul, massaman, panang), asiatiske krydderier, marinader og krydderiblandinger.</p>",
            "vi": "<p>Bộ gia vị hoàn chỉnh, bột cà ri, xốt ướp thịt nướng, ngũ vị hương, thảo mộc khô và gia vị nấu ăn đậm đà chuẩn vị.</p>",
            "th": "<p>พริกแกงเขียวหวาน พริกแกงเผ็ด มัสมั่น เครื่องเทศ และผงปรุงรสเข้มข้นสไตล์เอเชีย</p>"
        }
    },
    "drikkevarer-vin": {
        "title": {
            "en": "Beverages & Tea",
            "da": "Drikkevarer & Asiatisk Te",
            "vi": "Đồ uống, Trà & Giải khát",
            "th": "เครื่องดื่มและชา"
        },
        "description": {
            "en": "<p>Exotic tropical fruit juices, coconut water, Asian green teas, bubble tea ingredients, and refreshing drinks.</p>",
            "da": "<p>Eksotiske frugtjuicer, frisk asiatisk kokosvand, grøn te, boba-te ingredienser og forfriskende asiatiske drikkevarer.</p>",
            "vi": "<p>Nước ép trái cây nhiệt đới, nước dừa tươi nguyên chất, trà xanh, nguyên liệu trà sữa trân châu và nước giải khát Á Châu thơm mát.</p>",
            "th": "<p>น้ำผลไม้เมืองร้อน น้ำมะพร้าวสด ชาเขียว เครื่องดื่มสมุนไพร และวัตถุดิบชาไข่มุกยอดนิยม</p>"
        }
    },
    "konserves-kokosmaelk": {
        "title": {
            "en": "Canned Food & Coconut Milk",
            "da": "Konserves & Kokosmælk",
            "vi": "Đồ hộp & Nước cốt dừa",
            "th": "อาหารกระป๋องและกะทิ"
        },
        "description": {
            "en": "<p>Rich coconut milk and coconut cream, canned bamboo shoots, tropical fruits in syrup, water chestnuts, and canned specialties.</p>",
            "da": "<p>Kvalitets kokosmælk og kokosfløde, bambusskud på dåse, eksotiske frugter i lage og konserverede asiatiske specialiteter.</p>",
            "vi": "<p>Nước cốt dừa béo ngậy, măng tre đóng hộp, trái cây nhiệt đới ngâm đường (vải, nhãn, chôm chôm) và thực phẩm đóng hộp tiện lợi.</p>",
            "th": "<p>กะทิแท้เข้มข้น หัวกะทิ หน่อไม้กระป๋อง ผลไม้ลอยแก้ว และอาหารกระป๋องพร้อมปรุงคุณภาพดี</p>"
        }
    },
    "ris-mel-torvarer": {
        "title": {
            "en": "Rice, Flour & Dry Goods",
            "da": "Ris, Mel & Tørvarer",
            "vi": "Gạo, Bột & Đồ khô",
            "th": "ข้าว แป้ง และของแห้ง"
        },
        "description": {
            "en": "<p>Fragrant Jasmine rice, sticky glutinous rice, tapioca starch, rice paper, dried mushrooms, and pantry essentials.</p>",
            "da": "<p>Premium jasminris, klistrede ris, tapiokamel, rispapir, tørrede shiitake svampe og essentielle tørvarer til hverdagen.</p>",
            "vi": "<p>Gạo thơm Jasmine hảo hạng, gạo nếp nương, bánh tráng cuốn gỏi, bột mì, bột năng, bột gạo, nấm đông cô và mộc nhĩ khô.</p>",
            "th": "<p>ข้าวหอมมะลิ ข้าวเหนียว แป้งมันสำปะหลัง แผ่นแป้งปอเปี๊ยะ เห็ดหอมแห้ง และวัตถุดิบแห้งชั้นเลิศ</p>"
        }
    },
    "andre-asiatiske-varer": {
        "title": {
            "en": "Other Asian Specialties",
            "da": "Andre Asiatiske Specialiteter",
            "vi": "Sản phẩm Á Châu khác",
            "th": "สินค้าเอเชียอื่นๆ"
        },
        "description": {
            "en": "<p>Specialty Asian ingredients, cooking utensils, kitchenware, and diverse marketplace grocery items.</p>",
            "da": "<p>Spændende specialingredienser, køkkenudstyr, spisepinde og diverse asiatiske dagligvarer til hjemmet.</p>",
            "vi": "<p>Các loại nguyên liệu nấu ăn đặc thù, dụng cụ làm bếp, đũa ăn và các mặt hàng tạp hóa phong phú Á Đông.</p>",
            "th": "<p>วัตถุดิบปรุงอาหารสูตรพิเศษ อุปกรณ์เครื่องครัว และสินค้าเบ็ดเตล็ดนำเข้าจากเอเชีย</p>"
        }
    }
}


# ==============================================================================
# 2. MENU LINKS DATA (Main Menu & Footer Menu)
# ==============================================================================
LINK_TRANSLATIONS = {
    "Hjem": {
        "en": "Home",
        "da": "Hjem",
        "vi": "Trang chủ",
        "th": "หน้าแรก"
    },
    "Home": {
        "en": "Home",
        "da": "Hjem",
        "vi": "Trang chủ",
        "th": "หน้าแรก"
    },
    "Nudler": {
        "en": "Noodles",
        "da": "Nudler",
        "vi": "Mì & Bún",
        "th": "บะหมี่และก๋วยเตี๋ยว"
    },
    "Snacks": {
        "en": "Snacks",
        "da": "Snacks",
        "vi": "Bánh kẹo & Ăn vặt",
        "th": "ขนมและของทานเล่น"
    },
    "Saucer & Sojasauce": {
        "en": "Sauces & Soy Sauce",
        "da": "Saucer & Sojasauce",
        "vi": "Nước xốt & Nước tương",
        "th": "ซอสปรุงรสและซีอิ๊ว"
    },
    "Saucer": {
        "en": "Sauces & Soy Sauce",
        "da": "Saucer & Sojasauce",
        "vi": "Nước xốt & Nước tương",
        "th": "ซอสปรุงรสและซีอิ๊ว"
    },
    "Krydderier & Karry": {
        "en": "Spices & Curry",
        "da": "Krydderier & Karry",
        "vi": "Gia vị & Cà ri",
        "th": "เครื่องเทศและพริกแกง"
    },
    "Krydderier": {
        "en": "Spices & Curry",
        "da": "Krydderier & Karry",
        "vi": "Gia vị & Cà ri",
        "th": "เครื่องเทศและพริกแกง"
    },
    "Drikkevarer": {
        "en": "Beverages",
        "da": "Drikkevarer",
        "vi": "Đồ uống & Trà",
        "th": "เครื่องดื่มและชา"
    },
    "Drikkevarer & Vin": {
        "en": "Beverages",
        "da": "Drikkevarer & Vin",
        "vi": "Đồ uống & Trà",
        "th": "เครื่องดื่มและชา"
    },
    "Konserves & Kokosmælk": {
        "en": "Canned & Coconut Milk",
        "da": "Konserves & Kokosmælk",
        "vi": "Đồ hộp & Nước cốt dừa",
        "th": "อาหารกระป๋องและกะทิ"
    },
    "Konserves": {
        "en": "Canned & Coconut Milk",
        "da": "Konserves & Kokosmælk",
        "vi": "Đồ hộp & Nước cốt dừa",
        "th": "อาหารกระป๋องและกะทิ"
    },
    "Ris, Mel & Tørvarer": {
        "en": "Rice, Flour & Dry Goods",
        "da": "Ris, Mel & Tørvarer",
        "vi": "Gạo, Bột & Đồ khô",
        "th": "ข้าว แป้ง และของแห้ง"
    },
    "Andre asiatiske varer": {
        "en": "Other Asian Products",
        "da": "Andre asiatiske varer",
        "vi": "Sản phẩm Á Châu khác",
        "th": "สินค้าเอเชียอื่นๆ"
    },
    "Diverser": {
        "en": "Other Asian Products",
        "da": "Andre asiatiske varer",
        "vi": "Sản phẩm Á Châu khác",
        "th": "สินค้าเอเชียอื่นๆ"
    },
    "Om os": {
        "en": "About Us",
        "da": "Om os",
        "vi": "Về chúng tôi",
        "th": "เกี่ยวกับเรา"
    },
    "Om Rabuta": {
        "en": "About Rabuta",
        "da": "Om Rabuta",
        "vi": "Giới thiệu Rabuta",
        "th": "เกี่ยวกับราบูตะ"
    },
    "Kontakt": {
        "en": "Contact",
        "da": "Kontakt",
        "vi": "Liên hệ",
        "th": "ติดต่อเรา"
    },
    "Kontakt os": {
        "en": "Contact Us",
        "da": "Kontakt os",
        "vi": "Liên hệ chúng tôi",
        "th": "ติดต่อเรา"
    },
    "Levering & Fragt": {
        "en": "Shipping & Delivery",
        "da": "Levering & Fragt",
        "vi": "Giao hàng & Vận chuyển",
        "th": "การจัดส่งสินค้า"
    },
    "Handelsbetingelser": {
        "en": "Terms & Conditions",
        "da": "Handelsbetingelser",
        "vi": "Điều khoản dịch vụ",
        "th": "ข้อกำหนดและเงื่อนไข"
    },
    "Returpolitik": {
        "en": "Return Policy",
        "da": "Retur- og refusionspolitik",
        "vi": "Chính sách đổi trả & Hoàn tiền",
        "th": "นโยบายการคืนสินค้าและคืนเงิน"
    },
    "Privatlivspolitik": {
        "en": "Privacy Policy",
        "da": "Privatlivspolitik & Cookies",
        "vi": "Chính sách bảo mật",
        "th": "นโยบายความเป็นส่วนตัว"
    }
}


# ==============================================================================
# 3. PAGES DATA (6 Standard Pages)
# ==============================================================================
PAGES_DATA = {
    "om-os": {
        "title": {
            "en": "About Rabuta Asian Supermarket",
            "da": "Om Rabuta Asian Supermarket",
            "vi": "Giới thiệu về Siêu thị Á Châu Rabuta",
            "th": "เกี่ยวกับ Rabuta Asian Supermarket"
        },
        "body": {
            "en": """
<h2>Welcome to Rabuta Asian Supermarket</h2>
<p>Rabuta is your premier destination for authentic Asian groceries, snacks, beverages, and specialty ingredients in Denmark. We are passionate about bringing the rich, diverse flavors of Vietnam, Thailand, Korea, Japan, China, and the Philippines directly to your home kitchen.</p>
<h3>Our Mission</h3>
<p>Our mission is to provide an unmatched selection of high-quality Asian food items with guaranteed freshness, transparent origin, and fast, reliable delivery throughout Denmark.</p>
<h3>Why Choose Rabuta?</h3>
<ul>
  <li><strong>Authentic Quality:</strong> 100% genuine imported Asian ingredients from trusted global producers.</li>
  <li><strong>Huge Selection:</strong> Over 1,000+ items across noodles, sauces, spices, snacks, and fresh/dry staples.</li>
  <li><strong>Fast Delivery in Denmark:</strong> Secure, temperature-controlled packaging delivered straight to your door via DAO and PostNord.</li>
  <li><strong>Customer Service:</strong> Dedicated multilingual support ready to assist you.</li>
</ul>
""",
            "da": """
<h2>Velkommen til Rabuta Asian Supermarket</h2>
<p>Rabuta er dit foretrukne asiatiske supermarked i Danmark. Vi brænder for at bringe de autentiske, rige smagsoplevelser fra Vietnam, Thailand, Korea, Japan, Kina og Filippinerne direkte til dit køkken.</p>
<h3>Vores Mission</h3>
<p>Vores mission er at levere et bredt udvalg af asiatiske fødevarer af højeste kvalitet med garanteret friskhed, gennemsigtighed og hurtig, pålidelig levering i hele Danmark.</p>
<h3>Hvorfor vælge Rabuta?</h3>
<ul>
  <li><strong>Autentiske Produkter:</strong> 100% ægte importerede asiatiske varer fra velkendte varemærker.</li>
  <li><strong>Stort Udvalg:</strong> Over 1.000+ produkter inden for nudler, saucer, krydderier, snacks og tørvarer.</li>
  <li><strong>Hurtig Levering i Danmark:</strong> Hurtig og sikker forsendelse direkte til din dør med DAO og PostNord.</li>
  <li><strong>Kundeservice:</strong> Dedikeret flersproget kundeservice klar til at hjælpe dig.</li>
</ul>
""",
            "vi": """
<h2>Chào mừng bạn đến với Siêu thị Á Châu Rabuta</h2>
<p>Rabuta là siêu thị thực phẩm Á Châu trực tuyến hàng đầu tại Đan Mạch. Chúng tôi tự hào mang hương vị quê hương chuẩn vị và phong phú từ Việt Nam, Thái Lan, Hàn Quốc, Nhật Bản, Trung Quốc và Philippines đến tận gian bếp của bạn.</p>
<h3>Sứ mệnh của Rabuta</h3>
<p>Sứ mệnh của chúng tôi là cung cấp các sản phẩm thực phẩm Á Châu chất lượng cao, nguồn gốc rõ ràng, bảo quản tiêu chuẩn và dịch vụ giao hàng nhanh chóng, tận tâm trên khắp Đan Mạch.</p>
<h3>Tại sao nên chọn Rabuta?</h3>
<ul>
  <li><strong>Hàng chính hãng:</strong> 100% sản phẩm nhập khẩu chính ngạch từ các thương hiệu uy tín hàng đầu.</li>
  <li><strong>Danh mục đa dạng:</strong> Hơn 1.000 mặt hàng từ mì phở, gia vị, nước mắm, đồ hộp, bánh kẹo đến đồ khô.</li>
  <li><strong>Giao hàng nhanh toàn Đan Mạch:</strong> Đóng gói cẩn thận, an toàn và giao nhanh qua DAO & PostNord.</li>
  <li><strong>Hỗ trợ tận tâm:</strong> Đội ngũ chăm sóc khách hàng đa ngôn ngữ luôn sẵn sàng phục vụ.</li>
</ul>
""",
            "th": """
<h2>ยินดีต้อนรับสู่ Rabuta Asian Supermarket</h2>
<p>Rabuta คือซูเปอร์มาร์เก็ตเอเชียชั้นนำของคุณในเดนมาร์ก เรามุ่งมั่นนำรสชาติอาหารเอเชียต้นตำรับจากไทย เวียดนาม เกาหลี ญี่ปุ่น และทั่วเอเชียมาสู่ครัวของคุณอย่างสะดวกสบาย</p>
<h3>พันธกิจของเรา</h3>
<p>เรามุ่งมั่นคัดสรรสินค้าอุปโภคบริโภคคุณภาพเยี่ยม สดใหม่ ได้มาตรฐาน พร้อมบริการจัดส่งที่รวดเร็วและปลอดภัยครอบคลุมทั่วประเทศเดนมาร์ก</p>
<h3>ทำไมต้องเลือกซื้อกับ Rabuta?</h3>
<ul>
  <li><strong>สินค้าแท้ 100%:</strong> นำเข้าตรงจากแบรนด์ชั้นนำของเอเชีย</li>
  <li><strong>สินค้าครบครัน:</strong> มากกว่า 1,000 รายการ ทั้งบะหมี่ ซอสปรุงรส พริกแกง ขนม และของแห้ง</li>
  <li><strong>จัดส่งรวดเร็วทั่วเดนมาร์ก:</strong> บรรจุหีบห่ออย่างดี จัดส่งตรงถึงบ้านด้วย DAO และ PostNord</li>
  <li><strong>บริการด้วยใจ:</strong> ทีมงานพร้อมดูแลและตอบข้อซักถามในหลากหลายภาษา</li>
</ul>
"""
        }
    },
    "kontakt-os": {
        "title": {
            "en": "Contact Us & Store Information",
            "da": "Kontakt os & Butiksinformation",
            "vi": "Liên hệ & Thông tin cửa hàng",
            "th": "ติดต่อเราและข้อมูลร้านค้า"
        },
        "body": {
            "en": """
<h2>Contact Rabuta</h2>
<p>Have a question about our products, an existing order, or special requests? We are here to help!</p>
<div style="background:#f9f9f9; padding:20px; border-radius:8px; margin:20px 0;">
  <p><strong>Store Name:</strong> Rabuta Asian Supermarket</p>
  <p><strong>Email:</strong> support@rabuta.dk</p>
  <p><strong>Website:</strong> https://rabuta.dk</p>
  <p><strong>Opening Hours:</strong> Monday – Saturday: 09:00 – 18:00 (CET)</p>
  <p><strong>Response Time:</strong> We usually reply within 24 hours on business days.</p>
</div>
""",
            "da": """
<h2>Kontakt Rabuta</h2>
<p>Har du spørgsmål til vores produkter, en igangværende ordre eller særlige forespørgsler? Vi står altid klar til at hjælpe!</p>
<div style="background:#f9f9f9; padding:20px; border-radius:8px; margin:20px 0;">
  <p><strong>Butiksnavn:</strong> Rabuta Asian Supermarket</p>
  <p><strong>E-mail:</strong> support@rabuta.dk</p>
  <p><strong>Hjemmeside:</strong> https://rabuta.dk</p>
  <p><strong>Åbningstider:</strong> Mandag – Lørdag: 09:00 – 18:00</p>
  <p><strong>Svartid:</strong> Vi besvarer normalt alle henvendelser inden for 24 timer på hverdage.</p>
</div>
""",
            "vi": """
<h2>Liên hệ Rabuta</h2>
<p>Bạn có bất kỳ câu hỏi nào về sản phẩm, trạng thái đơn hàng hoặc yêu cầu đặc biệt? Đội ngũ Rabuta luôn sẵn sàng hỗ trợ bạn!</p>
<div style="background:#f9f9f9; padding:20px; border-radius:8px; margin:20px 0;">
  <p><strong>Cửa hàng:</strong> Siêu thị Á Châu Rabuta</p>
  <p><strong>Email hỗ trợ:</strong> support@rabuta.dk</p>
  <p><strong>Website:</strong> https://rabuta.dk</p>
  <p><strong>Giờ làm việc:</strong> Thứ Hai – Thứ Bảy: 09:00 – 18:00</p>
  <p><strong>Thời gian phản hồi:</strong> Chúng tôi sẽ phản hồi email trong vòng 24 giờ vào các ngày làm việc.</p>
</div>
""",
            "th": """
<h2>ติดต่อสอบถาม Rabuta</h2>
<p>หากคุณมีคำถามเกี่ยวกับสินค้า คำสั่งซื้อ หรือต้องการสอบถามข้อมูลเพิ่มเติม สามารถติดต่อเราได้ทันที</p>
<div style="background:#f9f9f9; padding:20px; border-radius:8px; margin:20px 0;">
  <p><strong>ชื่อร้านค้า:</strong> Rabuta Asian Supermarket</p>
  <p><strong>อีเมล:</strong> support@rabuta.dk</p>
  <p><strong>เว็บไซต์:</strong> https://rabuta.dk</p>
  <p><strong>เวลาทำการ:</strong> จันทร์ – เสาร์: 09:00 – 18:00 น.</p>
  <p><strong>การตอบกลับ:</strong> เราจะติดต่อกลับภายใน 24 ชั่วโมงในวันทำการ</p>
</div>
"""
        }
    },
    "levering-fragt": {
        "title": {
            "en": "Shipping & Delivery Policy",
            "da": "Levering & Fragtbetingelser",
            "vi": "Chính sách Vận chuyển & Giao hàng",
            "th": "นโยบายการจัดส่งและค่าขนส่ง"
        },
        "body": {
            "en": """
<h2>Shipping & Delivery in Denmark</h2>
<p>At Rabuta, we ensure fast and secure packaging so your Asian ingredients arrive fresh and undamaged.</p>
<h3>Delivery Carriers & Options</h3>
<ul>
  <li><strong>DAO Parcel Shop / Home Delivery:</strong> 1-3 business days.</li>
  <li><strong>PostNord:</strong> 1-2 business days across all regions in Denmark.</li>
</ul>
<h3>Shipping Rates & Free Delivery</h3>
<ul>
  <li>Standard shipping starting from <strong>39 DKK</strong>.</li>
  <li><strong>FREE SHIPPING</strong> on orders over <strong>499 DKK</strong> to parcel shops across Denmark.</li>
</ul>
""",
            "da": """
<h2>Levering og Fragt i Danmark</h2>
<p>Hos Rabuta pakker vi dine asiatiske fødevarer forsvarligt og sikkert, så de ankommer i perfekt stand.</p>
<h3>Leveringsmuligheder & Partnere</h3>
<ul>
  <li><strong>DAO Pakkeshop / Hjemmelevering:</strong> 1-3 hverdage.</li>
  <li><strong>PostNord:</strong> 1-2 hverdage til hele Danmark.</li>
</ul>
<h3>Fragtpriser & Fri Fragt</h3>
<ul>
  <li>Standard forsendelse fra kun <strong>39 DKK</strong>.</li>
  <li><strong>FRI FRAGT</strong> ved køb over <strong>499 DKK</strong> til pakkeshops i hele Danmark.</li>
</ul>
""",
            "vi": """
<h2>Chính sách Vận chuyển & Giao hàng tại Đan Mạch</h2>
<p>Rabuta cam kết đóng gói an toàn, chắc chắn và vận chuyển nhanh chóng để sản phẩm đến tay bạn luôn tươi mới và nguyên vẹn.</p>
<h3>Đơn vị vận chuyển & Thời gian giao hàng</h3>
<ul>
  <li><strong>DAO (Giao tại điểm nhận hàng hoặc tận nhà):</strong> 1-3 ngày làm việc.</li>
  <li><strong>PostNord:</strong> 1-2 ngày làm việc trên toàn lãnh thổ Đan Mạch.</li>
</ul>
<h3>Phí vận chuyển & Miễn phí giao hàng</h3>
<ul>
  <li>Phí ship tiêu chuẩn chỉ từ <strong>39 DKK</strong>.</li>
  <li><strong>MIỄN PHÍ VẬN CHUYỂN</strong> cho mọi đơn hàng từ <strong>499 DKK</strong> đến các điểm nhận hàng DAO / PostNord.</li>
</ul>
""",
            "th": """
<h2>นโยบายการจัดส่งสินค้าในเดนมาร์ก</h2>
<p>Rabuta บรรจุสินค้าอย่างพิถีพิถันเพื่อรับประกันว่าสินค้าทุกชิ้นจะถึงมือคุณในสภาพสมบูรณ์ที่สุด</p>
<h3>ผู้ให้บริการจัดส่งและระยะเวลา</h3>
<ul>
  <li><strong>DAO (จุดรับพัสดุ / ส่งถึงบ้าน):</strong> 1-3 วันทำการ</li>
  <li><strong>PostNord:</strong> 1-2 วันทำการทั่วเดนมาร์ก</li>
</ul>
<h3>อัตราค่าจัดส่งและโปรโมชั่นส่งฟรี</h3>
<ul>
  <li>ค่าจัดส่งเริ่มต้นเพียง <strong>39 DKK</strong></li>
  <li><strong>จัดส่งฟรี!</strong> สำหรับคำสั่งซื้อตั้งแต่ <strong>499 DKK</strong> ขึ้นไปสำหรับจุดรับพัสดุในเดนมาร์ก</li>
</ul>
"""
        }
    },
    "handelsbetingelser": {
        "title": {
            "en": "Terms of Service & Sales Conditions",
            "da": "Handels- og Salgsbetingelser",
            "vi": "Điều khoản Dịch vụ & Mua bán",
            "th": "ข้อกำหนดและเงื่อนไขการใช้บริการ"
        },
        "body": {
            "en": """
<h2>Terms of Service</h2>
<p>These terms apply to all purchases made on Rabuta.dk. By placing an order, you accept these terms and conditions.</p>
<h3>Payment Methods</h3>
<p>We accept MobilePay, Visa, Mastercard, Apple Pay, and Google Pay through secure, encrypted payment gateways.</p>
<h3>Order Confirmation</h3>
<p>Once your order is placed, you will receive an automatic order confirmation by email with your order summary and tracking details.</p>
""",
            "da": """
<h2>Handelsbetingelser</h2>
<p>Disse handelsbetingelser gælder for alle køb foretaget på Rabuta.dk. Ved afgivelse af ordre accepterer du nedenstående vilkår.</p>
<h3>Betalingsmuligheder</h3>
<p>Vi modtager MobilePay, Visa, Mastercard, Apple Pay og Google Pay via sikre, kryptered betalingssystemer.</p>
<h3>Ordrebekræftelse</h3>
<p>Så snart din ordre er modtaget, fremsendes automatisk en ordrebekræftelse pr. e-mail med ordredetaljer og sporingsnummer.</p>
""",
            "vi": """
<h2>Điều khoản Dịch vụ</h2>
<p>Các điều khoản này áp dụng cho mọi giao dịch mua sắm trên website Rabuta.dk. Khi đặt hàng, quý khách đồng ý tuân thủ các quy định dưới đây.</p>
<h3>Phương thức thanh toán</h3>
<p>Chúng tôi hỗ trợ thanh toán an toàn qua MobilePay, Visa, Mastercard, Apple Pay và Google Pay với cổng thanh toán bảo mật tiêu chuẩn quốc tế.</p>
<h3>Xác nhận đơn hàng</h3>
<p>Sau khi hoàn tất đặt hàng, bạn sẽ nhận được email xác nhận tự động kèm mã theo dõi lộ trình đơn hàng.</p>
""",
            "th": """
<h2>ข้อกำหนดและเงื่อนไขการบริการ</h2>
<p>ข้อกำหนดนี้มีผลบังคับใช้กับการสั่งซื้อทั้งหมดบนเว็บไซต์ Rabuta.dk เมื่อทำรายการสั่งซื้อ ถือว่าคุณยอมรับข้อกำหนดเหล่านี้</p>
<h3>วิธีการชำระเงิน</h3>
<p>เรารองรับการชำระเงินผ่าน MobilePay, Visa, Mastercard, Apple Pay และ Google Pay ผ่านระบบรักษาความปลอดภัยระดับสูง</p>
<h3>การยืนยันคำสั่งซื้อ</h3>
<p>เมื่อสั่งซื้อสำเร็จ คุณจะได้รับอีเมลยืนยันรายการสั่งซื้อพร้อมลิงก์ติดตามสถานะพัสดุ</p>
"""
        }
    },
    "returpolitik": {
        "title": {
            "en": "Refund & Return Policy",
            "da": "Retur- og Refusionspolitik",
            "vi": "Chính sách Đổi trả & Hoàn tiền",
            "th": "นโยบายการคืนสินค้าและคืนเงิน"
        },
        "body": {
            "en": """
<h2>Return & Refund Policy</h2>
<p>As a consumer in Denmark, you have a 14-day right of withdrawal for non-perishable goods in accordance with Danish consumer legislation.</p>
<h3>Food Items & Exceptions</h3>
<p>For health and hygiene reasons, fresh foods, perishable items, and opened food containers cannot be returned once delivered.</p>
<h3>Damaged or Defective Items</h3>
<p>If an item arrives damaged during transit or is defective, please contact support@rabuta.dk within 48 hours with a photo of the item, and we will issue an immediate replacement or full refund.</p>
""",
            "da": """
<h2>Retur- og Refusionspolitik</h2>
<p>Som forbruger i Danmark har du 14 dages fortrydelsesret på ikke-letfordærvelige varer i overensstemmelse med dansk forbrugerlovgivning.</p>
<h3>Fødevarer & Undtagelser</h3>
<p>Af sundheds- og hygiejnemæssige årsager kan letfordærvelige fødevarer samt åbnede fødevareemballager ikke returneres.</p>
<h3>Beskadigede Varer</h3>
<p>Hvis en vare er beskadiget under transporten, bedes du kontakte support@rabuta.dk inden for 48 timer med et foto, så fremsender vi straks en erstatningsvare eller refunderer beløbet.</p>
""",
            "vi": """
<h2>Chính sách Đổi trả & Hoàn tiền</h2>
<p>Theo luật bảo vệ người tiêu dùng tại Đan Mạch, quý khách có quyền đổi trả trong vòng 14 ngày đối với các sản phẩm hàng khô chưa qua sử dụng và còn nguyên niêm phong.</p>
<h3>Quy định đối với Thực phẩm</h3>
<p>Vì lý do vệ sinh an toàn thực phẩm, các mặt hàng tươi sống, hàng mau hỏng và sản phẩm đã mở bao bì sẽ không được áp dụng đổi trả.</p>
<h3>Hàng hóa lỗi hoặc hư hỏng do vận chuyển</h3>
<p>Nếu sản phẩm bị hư hỏng trong quá trình vận chuyển, vui lòng gửi email kèm ảnh chụp đến support@rabuta.dk trong vòng 48 giờ để được hoàn tiền 100% hoặc gửi bù hàng miễn phí.</p>
""",
            "th": """
<h2>นโยบายการคืนสินค้าและขอคืนเงิน</h2>
<p>คุณมีสิทธิ์เปลี่ยนหรือคืนสินค้าภายใน 14 วันสำหรับสินค้าแห้งที่ยังไม่เปิดใช้งานและอยู่ในบรรจุภัณฑ์เดิม ตามกฎหมายคุ้มครองผู้บริโภคของเดนมาร์ก</p>
<h3>ข้อยกเว้นสำหรับอาหาร</h3>
<p>ด้วยเหตุผลด้านสุขอนามัย สินค้าอาหารสด สินค้าเน่าเสียง่าย และสินค้าที่เปิดบรรจุภัณฑ์แล้ว จะไม่สามารถรับคืนได้</p>
<h3>กรณีสินค้าเสียหายจากการขนส่ง</h3>
<p>หากสินค้าชำรุดเสียหายจากการขนส่ง กรุณาถ่ายภาพและแจ้งเราที่ support@rabuta.dk ภายใน 48 ชั่วโมง เรายินดีเปลี่ยนสินค้าใหม่หรือคืนเงินเต็มจำนวนทันที</p>
"""
        }
    },
    "privatlivspolitik": {
        "title": {
            "en": "Privacy Policy & GDPR",
            "da": "Privatlivspolitik & GDPR",
            "vi": "Chính sách Bảo mật & GDPR",
            "th": "นโยบายความเป็นส่วนตัวและ GDPR"
        },
        "body": {
            "en": """
<h2>Privacy Policy & GDPR Compliance</h2>
<p>Rabuta respects your privacy and is committed to protecting your personal data in full compliance with the European General Data Protection Regulation (GDPR).</p>
<h3>Data We Collect</h3>
<p>We only collect the necessary personal data required to process your order, such as your name, shipping address, email address, and telephone number.</p>
<h3>Data Protection</h3>
<p>Your data is never sold or shared with third parties, except with trusted shipping partners (DAO/PostNord) strictly for delivery purposes.</p>
""",
            "da": """
<h2>Privatlivspolitik & GDPR</h2>
<p>Rabuta respekterer dit privatliv og beskytter dine personoplysninger i fuld overensstemmelse med EU's databeskyttelsesforordning (GDPR).</p>
<h3>Hvilke oplysninger indsamler vi?</h3>
<p>Vi indsamler udelukkende de nødvendige oplysninger til behandling og levering af din ordre (navn, adresse, e-mail og telefonnummer).</p>
<h3>Sikkerhed & Tredjeparter</h3>
<p>Dine data sælges aldrig videre og deles udelukkende med vores betroede fragtpartnere (DAO/PostNord) med det formål at levere dine varer.</p>
""",
            "vi": """
<h2>Chính sách Bảo mật thông tin & GDPR</h2>
<p>Rabuta cam kết bảo mật tuyệt đối thông tin cá nhân của quý khách theo đúng Quy định Bảo vệ Dữ liệu Chung Châu Âu (GDPR).</p>
<h3>Dữ liệu thu thập</h3>
<p>Chúng tôi chỉ thu thập các thông tin cần thiết để xử lý và giao hàng (họ tên, địa chỉ nhận hàng, email và số điện thoại liên hệ).</p>
<h3>Bảo mật thông tin</h3>
<p>Thông tin của bạn không bao giờ được chia sẻ cho bên thứ ba, ngoại trừ các đơn vị vận chuyển chính thức (DAO/PostNord) phục vụ việc giao nhận đơn hàng.</p>
""",
            "th": """
<h2>นโยบายความเป็นส่วนตัวตามมาตรฐาน GDPR</h2>
<p>Rabuta ให้ความสำคัญสูงสุดในการปกป้องข้อมูลส่วนบุคคลของคุณตามระเบียบข้อบังคับการคุ้มครองข้อมูลส่วนบุคคลของสหภาพยุโรป (GDPR)</p>
<h3>ข้อมูลที่เราจัดเก็บ</h3>
<p>เราจัดเก็บเฉพาะข้อมูลที่จำเป็นต่อการจัดส่งสินค้า เช่น ชื่อ ที่อยู่จัดส่ง อีเมล และเบอร์โทรศัพท์เท่านั้น</p>
<h3>ความปลอดภัยของข้อมูล</h3>
<p>ข้อมูลของคุณจะถูกเก็บรักษาอย่างปลอดภัย และไม่ถูกเปิดเผยต่อบุคคลภายนอก ยกเว้นบริษัทขนส่งที่ร่วมงานเพื่อการส่งสินค้าถึงคุณ</p>
"""
        }
    }
}


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================
def main():
    print("==================================================================", flush=True)
    print("STARTING FULL MULTILINGUAL TRANSLATION SYNC (DA, EN, VI, TH)", flush=True)
    print("==================================================================", flush=True)

    # 1. SYNC COLLECTIONS
    print("\n--- 1. PROCESSING COLLECTIONS ---", flush=True)
    col_res = gql("""
    {
      collections(first: 20) {
        nodes {
          id
          title
          handle
        }
      }
      translatableResources(first: 30, resourceType: COLLECTION) {
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
    
    col_nodes = {c["id"]: c for c in col_res.get("data", {}).get("collections", {}).get("nodes", [])}
    for tr_node in col_res.get("data", {}).get("translatableResources", {}).get("nodes", []):
        r_id = tr_node["resourceId"]
        c_info = col_nodes.get(r_id)
        if not c_info:
            continue
        handle = c_info["handle"]
        data = COLLECTIONS_DATA.get(handle)
        if not data:
            print(f"Skipping collection handle: {handle}", flush=True)
            continue
        
        print(f"\nTranslating Collection: [{c_info['title']}] ({handle}) -> {r_id}", flush=True)
        tc_map = {item["key"]: item for item in tr_node.get("translatableContent", [])}
        
        # We need to register for da, vi, th (and en if primary is da)
        # Check shop primary locale
        for loc in ["da", "vi", "th", "en"]:
            trans_list = []
            if "title" in tc_map and loc in data["title"]:
                trans_list.append({
                    "key": "title",
                    "value": data["title"][loc],
                    "digest": tc_map["title"]["digest"]
                })
            if "body_html" in tc_map and loc in data["description"]:
                trans_list.append({
                    "key": "body_html",
                    "value": data["description"][loc],
                    "digest": tc_map["body_html"]["digest"]
                })
            
            if trans_list:
                register_translation(r_id, loc, trans_list)

    # 2. SYNC PAGES
    print("\n--- 2. PROCESSING PAGES ---", flush=True)
    pages_res = gql("""
    {
      pages(first: 20) {
        nodes {
          id
          title
          handle
        }
      }
      translatableResources(first: 30, resourceType: PAGE) {
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
    
    page_nodes = {p["id"]: p for p in pages_res.get("data", {}).get("pages", {}).get("nodes", [])}
    for tr_node in pages_res.get("data", {}).get("translatableResources", {}).get("nodes", []):
        r_id = tr_node["resourceId"]
        p_info = page_nodes.get(r_id)
        if not p_info:
            continue
        handle = p_info["handle"]
        data = PAGES_DATA.get(handle)
        if not data:
            print(f"Skipping page handle: {handle}", flush=True)
            continue
            
        print(f"\nTranslating Page: [{p_info['title']}] ({handle}) -> {r_id}", flush=True)
        tc_map = {item["key"]: item for item in tr_node.get("translatableContent", [])}
        
        for loc in ["da", "vi", "th", "en"]:
            trans_list = []
            if "title" in tc_map and loc in data["title"]:
                trans_list.append({
                    "key": "title",
                    "value": data["title"][loc],
                    "digest": tc_map["title"]["digest"]
                })
            if "body_html" in tc_map and loc in data["body"]:
                trans_list.append({
                    "key": "body_html",
                    "value": data["body"][loc],
                    "digest": tc_map["body_html"]["digest"]
                })
            
            if trans_list:
                register_translation(r_id, loc, trans_list)

    # 3. SYNC MENU LINKS
    print("\n--- 3. PROCESSING MENU LINKS ---", flush=True)
    links_res = gql("""
    {
      translatableResources(first: 100, resourceType: LINK) {
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
    
    for tr_node in links_res.get("data", {}).get("translatableResources", {}).get("nodes", []):
        r_id = tr_node["resourceId"]
        tc_map = {item["key"]: item for item in tr_node.get("translatableContent", [])}
        title_tc = tc_map.get("title")
        if not title_tc:
            continue
        
        base_title = title_tc["value"].strip()
        trans_map = LINK_TRANSLATIONS.get(base_title)
        if not trans_map:
            for k, v in LINK_TRANSLATIONS.items():
                if k.lower() == base_title.lower():
                    trans_map = v
                    break
        
        if trans_map:
            print(f"Translating Menu Link: [{base_title}] ({r_id})", flush=True)
            for loc in ["da", "vi", "th", "en"]:
                if loc in trans_map:
                    register_translation(r_id, loc, [{
                        "key": "title",
                        "value": trans_map[loc],
                        "digest": title_tc["digest"]
                    }])
        else:
            print(f"Skipping link '{base_title}' (No mapping)", flush=True)

    print("\n==================================================================", flush=True)
    print("ALL 4-LANGUAGE TRANSLATIONS SYNC COMPLETED SUCCESSFULLY!", flush=True)
    print("==================================================================", flush=True)


if __name__ == "__main__":
    main()
