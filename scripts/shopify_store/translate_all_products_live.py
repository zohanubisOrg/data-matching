import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import json
import time
import urllib.request
import urllib.parse
import re
import pandas as pd
import argparse

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

def graphql_query(query, variables=None, max_retries=5):
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
            elif e.code >= 500:
                time.sleep(2)
                continue
            else:
                return {}
        except Exception:
            time.sleep(1.5)
    return {}

# Clean barcode lookup helper
def clean_bc(x):
    if pd.isna(x) or not x:
        return ""
    s = str(x).strip()
    if s.endswith(".0"):
        s = s[:-2]
    m = re.search(r'(\d{6,14})', s)
    if m:
        return m.group(1).lstrip("0")
    return s.lstrip("0")

# Build dictionary of Category translations
CATEGORY_TRANS = {
    "Snack": {"vi": "Bánh kẹo & Đồ ăn vặt", "th": "ขนมและของทานเล่น"},
    "Nudler": {"vi": "Mì, Bún & Phở", "th": "บะหมี่และก๋วยเตี๋ยว"},
    "Saucer": {"vi": "Nước sốt & Nước tương", "th": "ซอสและซีอิ๊ว"},
    "Saucer & Sojasauce": {"vi": "Nước sốt & Nước tương", "th": "ซอสและซีอิ๊ว"},
    "Krydderier": {"vi": "Gia vị & Cà ri", "th": "เครื่องเทศและพริกแกง"},
    "Krydderier & Karry": {"vi": "Gia vị & Cà ri", "th": "เครื่องเทศและพริกแกง"},
    "Drikker": {"vi": "Nước giải khát & Trà", "th": "เครื่องดื่มและชา"},
    "Drikkevarer & Vin": {"vi": "Nước giải khát & Trà", "th": "เครื่องดื่มและชา"},
    "Diverse": {"vi": "Hàng tạp hóa Châu Á", "th": "สินค้าเอเชียทั่วไป"},
    "Andre asiatiske varer": {"vi": "Hàng tạp hóa Châu Á", "th": "สินค้าเอเชียทั่วไป"},
    "Konserves": {"vi": "Đồ hộp & Nước cốt dừa", "th": "อาหารกระป๋องและกะทิ"},
    "Konserves & Kokosmælk": {"vi": "Đồ hộp & Nước cốt dừa", "th": "อาหารกระป๋องและกะทิ"},
    "Ris, Mel & Tørvarer": {"vi": "Gạo, Bột & Đồ khô", "th": "ข้าว แป้ง และของแห้ง"},
    "Ris": {"vi": "Gạo & Nông sản", "th": "ข้าวและธัญพืช"},
    "Bønner": {"vi": "Đậu các loại", "th": "ถั่วชนิดต่างๆ"}
}

def translate_product_title(danish_title, origin_label, category, brand):
    # If original label exists and is readable, use it as Thai/Vietnamese base
    clean_da = str(danish_title).strip()
    
    # 1. Build Vietnamese Title
    vi_title = clean_da
    # Replace common Danish descriptor terms with natural Vietnamese
    replacements_vi = [
        (r'originale kiksstænger', 'bánh quy que giòn vị nguyên bản'),
        (r'rissnack og jordnødder med sojasauce', 'snack bánh gạo đậu phộng vị nước tương'),
        (r'overtrukne grønne ærter med wasabi', 'đậu hà lan sấy giòn vị wasabi'),
        (r'jordnøddecrackers med sesam og kokos', 'bánh phồng đậu phộng mè dừa'),
        (r'kokosovertrukne jordnødder', 'đậu phộng da cá nước cốt dừa'),
        (r'blandede riscrackers', 'bánh gạo giòn thập cẩm'),
        (r'jordnøddecrackers med sesam', 'bánh đậu phộng mè rang'),
        (r'syltede mangostrimler med chili', 'xoài sấy dẻo ngâm chua cay'),
        (r'flødemælkekarameller', 'kẹo sữa mềm truyền thống'),
        (r'budding med blandet frugtsmag', 'thạch pudding hương trái cây tổng hợp'),
        (r'gelédessert med kokossmag', 'rau câu dừa thạch dừa nata de coco'),
        (r'sojasauce til dumplings', 'nước tương chấm bánh xếp gyoza'),
        (r'sauce til nudler i koreansk stil', 'nước sốt xào miến chuẩn phong cách Hàn Quốc'),
        (r'instant-nudler', 'mì ăn liền'),
        (r'instant nudler', 'mì ăn liền'),
        (r'med smag af', 'hương vị'),
        (r'med smag', 'vị'),
        (r'stærk', 'cay nồng'),
        (r'ekstra stærk', 'siêu cay'),
        (r'kyllingesmag', 'vị gà'),
        (r'rejesmag', 'vị tôm'),
        (r'oksekødssmag', 'vị bò'),
        (r'svinekødssmag', 'vị thịt heo'),
        (r'karrypasta', 'cốt cà ri'),
        (r'grøn karrypasta', 'cốt cà ri xanh Thái'),
        (r'rød karrypasta', 'cốt cà ri đỏ Thái'),
        (r'gul karrypasta', 'cốt cà ri vàng'),
        (r'fiskesauce', 'nước mắm'),
        (r'østerssauce', 'dầu hào'),
        (r'sojasauce', 'nước tương'),
        (r'chilisauce', 'tương ớt'),
        (r'sød chilisauce', 'tương ớt ngọt'),
        (r'kokosmælk', 'nước cốt dừa'),
        (r'kokoscreme', 'kem dừa béo ngậy'),
        (r'rispapir', 'bánh tráng cuốn'),
        (r'poser', 'gói'),
        (r'stk\.', 'miếng'),
        (r'dåse', 'lon')
    ]
    for pattern, rep in replacements_vi:
        vi_title = re.sub(pattern, rep, vi_title, flags=re.IGNORECASE)

    # 2. Build Thai Title
    th_title = clean_da
    if origin_label and pd.notna(origin_label) and any(ord(c) > 0x0E00 and ord(c) < 0x0E7F for c in str(origin_label)):
        th_title = str(origin_label).strip()
    else:
        replacements_th = [
            (r'originale kiksstænger', 'ขนมขาไก่รสดั้งเดิม'),
            (r'rissnack og jordnødder med sojasauce', 'ขนมข้าวอบกรอบผสมถั่วลิสงรสซีอิ๊ว'),
            (r'overtrukne grønne ærter med wasabi', 'ถั่วลันเตาอบกรอบรสวาซาบิ'),
            (r'kokosovertrukne jordnødder', 'ถั่วลิสงเคลือบกะทิ'),
            (r'blandede riscrackers', 'ข้าวเกรียบรวมมิตร'),
            (r'syltede mangostrimler med chili', 'มะม่วงแช่อิ่มคลุกพริกเกลือ'),
            (r'flødemælkekarameller', 'ลูกอมรสนม'),
            (r'budding med blandet frugtsmag', 'พุดดิ้งรสผลไม้รวม'),
            (r'gelédessert med kokossmag', 'วุ้นมะพร้าวผสมวุ้นคาราจีแนน'),
            (r'instant-nudler', 'บะหมี่กึ่งสำเร็จรูป'),
            (r'instant nudler', 'บะหมี่กึ่งสำเร็จรูป'),
            (r'med smag af', 'รส'),
            (r'med smag', 'รส'),
            (r'stærk', 'รสเผ็ด'),
            (r'kyllingesmag', 'รสไก่'),
            (r'rejesmag', 'รสต้มยำกุ้ง'),
            (r'oksekødssmag', 'รสเนื้อ'),
            (r'karrypasta', 'พริกแกง'),
            (r'grøn karrypasta', 'พริกแกงเขียวหวาน'),
            (r'rød karrypasta', 'พริกแกงเผ็ด'),
            (r'gul karrypasta', 'พริกแกงกะหรี่'),
            (r'fiskesauce', 'น้ำปลาแท้'),
            (r'østerssauce', 'ซอสหอยนางรม'),
            (r'sojasauce', 'ซีอิ๊วขาว'),
            (r'chilisauce', 'ซอสพริก'),
            (r'sød chilisauce', 'น้ำจิ้มไก่'),
            (r'kokosmælk', 'กะทิสด'),
            (r'poser', 'ซอง'),
            (r'stk\.', 'ชิ้น')
        ]
        for pattern, rep in replacements_th:
            th_title = re.sub(pattern, rep, th_title, flags=re.IGNORECASE)

    return vi_title, th_title

def run_multilingual_sync(limit=None):
    print("=========================================================")
    print("       STARTING FULL CATALOG MULTILINGUAL TRANSLATION    ")
    print("=========================================================")
    
    # Load Master 1659
    master_dict = {}
    path_1659 = 'output/shopify_import_final/Master_All_Products_89cols_With_Images.xlsx'
    if os.path.exists(path_1659):
        df_1659 = pd.read_excel(path_1659, header=2, dtype=str)
        for _, r in df_1659.iterrows():
            cbc = clean_bc(r.get('Barcode'))
            if cbc:
                master_dict[cbc] = {
                    "origin_label": str(r.get('Tên nguyên văn trên nhãn', '')),
                    "brand": str(r.get('Brand', '')),
                    "category": str(r.get('Category (editorial)', ''))
                }

    # Load Audit products
    df_audit = pd.read_excel('output/reconciliation/Shopify_Live_Catalog_Full_Audit.xlsx')
    if limit:
        df_audit = df_audit.head(limit)

    total = len(df_audit)
    print(f"Total Products to translate: {total}")

    # Progress tracking
    progress_file = "output/reconciliation/translations_progress.json"
    completed = {}
    if os.path.exists(progress_file):
        try:
            with open(progress_file, "r", encoding="utf-8") as f:
                completed = json.load(f)
        except Exception:
            completed = {}

    success_count = 0
    start_time = time.time()

    for idx, (_, row) in enumerate(df_audit.iterrows()):
        pid_raw = str(row['Product_ID']).strip()
        pid = f"gid://shopify/Product/{pid_raw}"
        live_title = str(row['Title']).strip()
        live_type = str(row['Product_Type']).strip()
        raw_bc = str(row['Variant_Barcode'])
        cbc = clean_bc(raw_bc)

        if pid_raw in completed:
            success_count += 1
            continue

        # Get translatable digests
        query_trans = """
        query getTranslatable($resourceId: ID!) {
          translatableResource(resourceId: $resourceId) {
            translatableContent {
              key
              value
              digest
            }
          }
        }
        """
        res_t = graphql_query(query_trans, {"resourceId": pid})
        content_list = res_t.get("data", {}).get("translatableResource", {}).get("translatableContent", [])
        if not content_list:
            continue

        title_digest = next((c["digest"] for c in content_list if c["key"] == "title"), None)
        type_digest = next((c["digest"] for c in content_list if c["key"] == "product_type"), None)

        if not title_digest:
            continue

        # Generate Translations
        m_info = master_dict.get(cbc, {})
        vi_title, th_title = translate_product_title(
            live_title,
            m_info.get("origin_label", ""),
            live_type,
            m_info.get("brand", "")
        )

        translations = [
            {"locale": "vi", "key": "title", "value": vi_title, "translatableContentDigest": title_digest},
            {"locale": "th", "key": "title", "value": th_title, "translatableContentDigest": title_digest}
        ]

        # Add Category / Type translation if digest available
        if type_digest and live_type in CATEGORY_TRANS:
            translations.append({"locale": "vi", "key": "product_type", "value": CATEGORY_TRANS[live_type]["vi"], "translatableContentDigest": type_digest})
            translations.append({"locale": "th", "key": "product_type", "value": CATEGORY_TRANS[live_type]["th"], "translatableContentDigest": type_digest})

        # Register Translations
        mutation = """
        mutation translationsRegister($resourceId: ID!, $translations: [TranslationInput!]!) {
          translationsRegister(resourceId: $resourceId, translations: $translations) {
            userErrors {
              field
              message
            }
          }
        }
        """
        res_reg = graphql_query(mutation, {"resourceId": pid, "translations": translations})
        errors = res_reg.get("data", {}).get("translationsRegister", {}).get("userErrors", [])
        
        if not errors:
            success_count += 1
            completed[pid_raw] = {"vi": vi_title, "th": th_title}
            print(f"[{idx+1}/{total}] [SUCCESS] {raw_bc} | VI: {vi_title[:30]}... | TH: {th_title[:30]}...")
        else:
            print(f"[{idx+1}/{total}] [ERROR] {raw_bc} -> {errors}")

        if (idx + 1) % 20 == 0:
            with open(progress_file, "w", encoding="utf-8") as f:
                json.dump(completed, f, ensure_ascii=False, indent=2)
            elapsed = time.time() - start_time
            rate = (idx + 1) / elapsed if elapsed > 0 else 1
            rem = (total - (idx + 1)) / rate if rate > 0 else 0
            print(f"    --> Progress: {idx+1}/{total} ({(idx+1)/total*100:.1f}%) | Est. remaining: {rem/60:.1f} mins")

        time.sleep(0.3)

    # Save final progress
    with open(progress_file, "w", encoding="utf-8") as f:
        json.dump(completed, f, ensure_ascii=False, indent=2)

    print("\n=========================================================")
    print(f"🎉 TRANSLATION COMPLETE: {success_count}/{total} products translated to Vietnamese & Thai!")
    print("=========================================================")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    run_multilingual_sync(limit=args.limit)
