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
token = ENV.get("SHOPIFY_ADMIN_ACCESS_TOKEN")

def graphql_query(query, variables=None):
    url = f"https://{shop}/admin/api/2026-10/graphql.json"
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
    req.add_header("X-Shopify-Access-Token", token)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[!] GraphQL Error: {e}")
        return {}

def register_translations(resource_id, translations_list):
    mutation = """
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
    res = graphql_query(mutation, {
        "resourceId": resource_id,
        "translations": translations_list
    })
    errors = res.get("data", {}).get("translationsRegister", {}).get("userErrors", [])
    if errors:
        print(f"        [!] Translation Warning for {resource_id}: {errors}")
    return res

# 1. Collections Translations
COLLECTIONS_DATA = {
    "nudler": {
        "vi": {"title": "Mì, Bún & Phở", "body_html": "Các loại mì ăn liền, hủ tiếu, phở và bún khô chính gốc từ Việt Nam, Thái Lan, Hàn Quốc, Nhật Bản."},
        "th": {"title": "บะหมี่และก๋วยเตี๋ยว", "body_html": "บะหมี่กึ่งสำเร็จรูป เส้นก๋วยเตี๋ยว และวุ้นเส้นคุณภาพพรีเมียมจากเอเชีย"}
    },
    "snacks": {
        "vi": {"title": "Bánh kẹo & Đồ ăn vặt", "body_html": "Các loại bánh quy, snack rong biển, đậu phộng giòn tẩm vị, bánh gạo giòn thơm ngon."},
        "th": {"title": "ขนมและของทานเล่น", "body_html": "ขนมขบเคี้ยว สาหร่ายทอด ข้าวเกรียบ และถั่วปรุงรสต้นตำรับ"}
    },
    "saucer-sojasauce": {
        "vi": {"title": "Nước sốt & Nước tương", "body_html": "Nước mắm, nước tương hảo hạng, dầu hào, sốt ớt cay và sốt ướp thịt nướng đậm đà."},
        "th": {"title": "ซอสและซีอิ๊ว", "body_html": "ซอสปรุงรส ซีอิ๊วขาว น้ำมันหอย น้ำปลาแท้ และน้ำพริกเผารสเลิศ"}
    },
    "krydderier-karry": {
        "vi": {"title": "Gia vị & Bột cà ri", "body_html": "Bột cà ri, gói gia vị nấu lẩu, bột ngũ vị hương và các loại gia vị truyền thống Châu Á."},
        "th": {"title": "เครื่องเทศและพริกแกง", "body_html": "พริกแกงไทย ผงปรุงรส ซุปก้อน และเครื่องเทศเข้มข้น"}
    },
    "drikkevarer-vin": {
        "vi": {"title": "Nước giải khát & Trà", "body_html": "Nước dừa tươi, nước trái cây thạch dừa, trà xanh, sữa đậu nành và đồ uống giải nhiệt."},
        "th": {"title": "เครื่องดื่มและชา", "body_html": "น้ำมะพร้าวสด น้ำผลไม้ผสมวุ้น ชาเขียว และเครื่องดื่มยอดนิยม"}
    },
    "andre-asiatiske-varer": {
        "vi": {"title": "Hàng tạp hóa Châu Á khác", "body_html": "Bánh tráng, đồ khô, nấm hương, mộc nhĩ và nguyên liệu ẩm thực đa dạng."},
        "th": {"title": "สินค้าเอเชียอื่นๆ", "body_html": "แป้ง วัตถุดิบอาหารแห้ง และส่วนผสมทำอาหารเอเชียครบวงจร"}
    },
    "ris-mel-torvarer": {
        "vi": {"title": "Gạo, Bột & Đồ khô", "body_html": "Gạo thơm hoa lài thượng hạng, bột nếp, bột năng và các loại hạt ngũ cốc."},
        "th": {"title": "ข้าว แป้ง และของแห้ง", "body_html": "ข้าวหอมมะลิ แป้งทำอาหาร และธัญพืชคัดพิเศษ"}
    }
}

# 2. Pages Translations
PAGES_DATA = {
    "om-os": {
        "vi": {
            "title": "Về Siêu thị Rabuta Asian Supermarket",
            "body_html": """
            <div style="line-height:1.7; font-size:16px;">
                <h2>Chào mừng bạn đến với Rabuta – Siêu thị Thực phẩm Châu Á tại Đan Mạch</h2>
                <p><strong>Rabuta</strong> tự hào mang đến cho quý khách hàng những hương vị ẩm thực Châu Á đích thực ngay tại Đan Mạch. Chúng tôi cung cấp các mặt hàng thực phẩm, mì, bánh kẹo, gia vị và nguyên liệu tươi ngon được nhập khẩu trực tiếp từ <em>Việt Nam, Thái Lan, Hàn Quốc, Nhật Bản, Trung Quốc và Đài Loan</em>.</p>
                <div style="background:#f9f9f9; padding:20px; border-left:4px solid #e53e3e; margin:20px 0;">
                    <h3>Cam kết của Rabuta:</h3>
                    <ul>
                        <li><strong>100% Sản phẩm chính hãng:</strong> Đảm bảo nguồn gốc xuất xứ và tiêu chuẩn vệ sinh an toàn thực phẩm.</li>
                        <li><strong>Giao hàng toàn Đan Mạch:</strong> Đóng gói cẩn thận, giao nhanh 1-2 ngày làm việc qua GLS / PostNord.</li>
                        <li><strong>Hỗ trợ tận tình:</strong> Dịch vụ khách hàng thân thiện, tư vấn nấu ăn và giải đáp nhanh chóng.</li>
                    </ul>
                </div>
            </div>
            """
        },
        "th": {
            "title": "เกี่ยวกับ Rabuta Asian Supermarket",
            "body_html": """
            <div style="line-height:1.7; font-size:16px;">
                <h2>ยินดีต้อนรับสู่ Rabuta – ซูเปอร์มาร์เก็ตสินค้าเอเชียชั้นนำในเดนมาร์ก</h2>
                <p><strong>Rabuta</strong> มุ่งมั่นนำเสนอวัตถุดิบและรสชาติเอเชียแท้ๆ ส่งตรงถึงครัวของคุณในเดนมาร์ก สินค้าของเรานำเข้าโดยตรงจาก <em>ไทย เวียดนาม ญี่ปุ่น เกาหลีใต้ จีน และไต้หวัน</em></p>
                <div style="background:#f9f9f9; padding:20px; border-left:4px solid #e53e3e; margin:20px 0;">
                    <h3>จุดเด่นของเรา:</h3>
                    <ul>
                        <li><strong>สินค้าแท้ 100%:</strong> คัดสรรคุณภาพเพื่อรสชาติแบบดั้งเดิม</li>
                        <li><strong>จัดส่งรวดเร็วทั่วเดนมาร์ก:</strong> บรรจุหีบห่ออย่างดี ส่งถึงบ้านหรือจุดรับพัสดุใน 1-2 วันทำการ</li>
                        <li><strong>บริการด้วยใจ:</strong> พร้อมให้คำแนะนำและช่วยเหลือทุกคำถาม</li>
                    </ul>
                </div>
            </div>
            """
        }
    },
    "kontakt-os": {
        "vi": {
            "title": "Liên hệ & Chăm sóc Khách hàng",
            "body_html": """
            <div style="line-height:1.7; font-size:16px;">
                <h2>Liên hệ Rabuta</h2>
                <p>Quý khách có thắc mắc về đơn hàng, sản phẩm hoặc cần hỗ trợ đặt hàng, vui lòng liên hệ với chúng tôi qua:</p>
                <p>📧 <strong>Email:</strong> nmasianshop@gmail.com<br>🌐 <strong>Website:</strong> https://rabuta.dk</p>
                <p>🕒 <strong>Thời gian phản hồi:</strong> Trong vòng 24 giờ vào các ngày làm việc.</p>
            </div>
            """
        },
        "th": {
            "title": "ติดต่อเราและฝ่ายบริการลูกค้า",
            "body_html": """
            <div style="line-height:1.7; font-size:16px;">
                <h2>ติดต่อ Rabuta</h2>
                <p>หากคุณมีข้อสงสัยเกี่ยวกับสินค้า คำสั่งซื้อ หรือต้องการคำแนะนำ สามารถติดต่อเราได้ที่:</p>
                <p>📧 <strong>อีเมล:</strong> nmasianshop@gmail.com<br>🌐 <strong>เว็บไซต์:</strong> https://rabuta.dk</p>
                <p>🕒 <strong>เวลาทำการฝ่ายบริการลูกค้า:</strong> ตอบกลับภายใน 24 ชั่วโมงในวันทำการ</p>
            </div>
            """
        }
    },
    "levering-fragt": {
        "vi": {
            "title": "Chính sách Giao hàng & Vận chuyển",
            "body_html": """
            <div style="line-height:1.7; font-size:16px;">
                <h2>Vận chuyển nhanh chóng trên toàn Đan Mạch</h2>
                <ul>
                    <li><strong>Giao đến Pakkeshop (GLS / PostNord):</strong> 39 DKK (Thời gian 1-2 ngày).</li>
                    <li><strong>Giao hàng tận nhà:</strong> 59 DKK.</li>
                    <li><strong>MIỄN PHÍ VẬN CHUYỂN:</strong> Cho đơn hàng từ <strong>499 DKK</strong> trở lên.</li>
                </ul>
            </div>
            """
        },
        "th": {
            "title": "การจัดส่งและค่าบริการจัดส่ง",
            "body_html": """
            <div style="line-height:1.7; font-size:16px;">
                <h2>บริการจัดส่งพัสดุทั่วประเทศเดนมาร์ก</h2>
                <ul>
                    <li><strong>จัดส่งไปยังจุดรับพัสดุ (Pakkeshop):</strong> 39 DKK (1-2 วันทำการ)</li>
                    <li><strong>จัดส่งถึงหน้าบ้าน:</strong> 59 DKK</li>
                    <li><strong>ฟรีค่าจัดส่ง:</strong> เมื่อสั่งซื้อครบ <strong>499 DKK</strong> ขึ้นไป</li>
                </ul>
            </div>
            """
        }
    },
    "handelsbetingelser": {
        "vi": {
            "title": "Điều khoản Dịch vụ & Mua hàng",
            "body_html": """
            <div style="line-height:1.7; font-size:15px;">
                <h2>Điều khoản mua hàng trên Rabuta.dk</h2>
                <p>Áp dụng theo luật thương mại điện tử Đan Mạch (Købeloven và Forbrugeraftaleloven). Giá trên website tính bằng DKK và đã bao gồm 25% thuế VAT Đan Mạch.</p>
                <p>Quyền đổi trả 14 ngày cho hàng khô đóng gói chưa bóc bao bì.</p>
            </div>
            """
        },
        "th": {
            "title": "ข้อกำหนดและเงื่อนไขการสั่งซื้อ",
            "body_html": """
            <div style="line-height:1.7; font-size:15px;">
                <h2>ข้อกำหนดและเงื่อนไข Rabuta.dk</h2>
                <p>ราคาสินค้าทั้งหมดเป็นสกุลเงินโครนเดนมาร์ก (DKK) รวมภาษีมูลค่าเพิ่ม 25% ตามกฎหมายเดนมาร์ก</p>
            </div>
            """
        }
    },
    "returpolitik": {
        "vi": {
            "title": "Chính sách Đổi trả & Hoàn tiền",
            "body_html": "<p>Quý khách có quyền hoàn trả hàng hóa chưa bóc mở trong vòng 14 ngày kể từ ngày nhận hàng. Vui lòng liên hệ nmasianshop@gmail.com trước khi gửi hàng về.</p>"
        },
        "th": {
            "title": "นโยบายการคืนสินค้าและการคืนเงิน",
            "body_html": "<p>สามารถคืนสินค้าที่ยังไม่เปิดบรรจุภัณฑ์ได้ภายใน 14 วัน กรุณาติดต่อ nmasianshop@gmail.com ก่อนทำการส่งคืน</p>"
        }
    },
    "privatlivspolitik": {
        "vi": {
            "title": "Chính sách Bảo mật & Quyền riêng tư (GDPR)",
            "body_html": "<p>Chúng tôi cam kết bảo vệ tuyệt đối thông tin cá nhân của quý khách theo quy định GDPR Châu Âu.</p>"
        },
        "th": {
            "title": "นโยบายความเป็นส่วนตัว (GDPR)",
            "body_html": "<p>ข้อมูลส่วนบุคคลของท่านได้รับการคุ้มครองอย่างปลอดภัยตามมาตรฐาน GDPR ของสหภาพยุโรป</p>"
        }
    }
}

def main():
    print("=========================================================")
    print("     AUTOMATING VIETNAMESE (vi) & THAI (th) TRANSLATIONS ")
    print("=========================================================")
    
    # 1. Fetch Collections & Pages IDs
    get_ids_query = """
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
    }
    """
    res = graphql_query(get_ids_query)["data"]
    col_map = {c["node"]["handle"]: c["node"]["id"] for c in res["collections"]["edges"]}
    page_map = {p["node"]["handle"]: p["node"]["id"] for p in res["pages"]["edges"]}

    # 2. Register Translations for Collections
    print("\n[*] Translating Collections to VI & TH...")
    for handle, trans_data in COLLECTIONS_DATA.items():
        cid = col_map.get(handle)
        if not cid:
            continue
        
        t_list = []
        for loc in ["vi", "th"]:
            if loc in trans_data:
                t_list.append({"locale": loc, "key": "title", "value": trans_data[loc]["title"]})
                t_list.append({"locale": loc, "key": "body_html", "value": trans_data[loc]["body_html"]})
        
        register_translations(cid, t_list)
        print(f"    [+] Translated Collection '{handle}' -> VI: '{trans_data['vi']['title']}' | TH: '{trans_data['th']['title']}'")
        time.sleep(0.2)

    # 3. Register Translations for Pages
    print("\n[*] Translating Store Pages to VI & TH...")
    for handle, trans_data in PAGES_DATA.items():
        pid = page_map.get(handle)
        if not pid:
            continue
        
        t_list = []
        for loc in ["vi", "th"]:
            if loc in trans_data:
                t_list.append({"locale": loc, "key": "title", "value": trans_data[loc]["title"]})
                t_list.append({"locale": loc, "key": "body_html", "value": trans_data[loc]["body_html"]})
        
        register_translations(pid, t_list)
        print(f"    [+] Translated Page '{handle}' -> VI: '{trans_data['vi']['title']}' | TH: '{trans_data['th']['title']}'")
        time.sleep(0.2)

    print("\n=========================================================")
    print("🎉 VIETNAMESE & THAI MULTI-LANGUAGE DEPLOYED 100%!")
    print("=========================================================")

if __name__ == "__main__":
    main()
