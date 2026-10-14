import os
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import time
import json
import openpyxl
import requests
from io import BytesIO
from PIL import Image
from playwright.sync_api import sync_playwright

EXCEL_SOURCE = "source-import/new_source_from_customer/12-10-new-requirment/Rabuta.12.10.2026_original.xlsx"
COOKIE_FILE = "output/google_cookies.json"
OUTPUT_DIR = "output/pilot_20_hd_studio_images"
REPORT_EXCEL = "output/Rabuta_Pilot_20_Images_Audit.xlsx"

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(os.path.dirname(REPORT_EXCEL), exist_ok=True)

HEADERS = {
    'User-Agent': 'RabutaCatalogEngine/2.0 (contact@rabuta.dk; High-Res Importer)',
    'Accept': 'application/json, image/*, */*'
}

def get_image_info(img_bytes):
    try:
        im = Image.open(BytesIO(img_bytes))
        w, h = im.size
        return w, h, im.format
    except Exception:
        return 0, 0, "UNKNOWN"

def fetch_off_images(barcode):
    url = f"https://world.openfoodfacts.org/api/v2/product/{barcode}?fields=code,product_name,image_front_url,image_ingredients_url,image_nutrition_url,image_packaging_url,selected_images"
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        if r.status_code == 200:
            p = r.json().get("product", {})
            
            # Helper to get full-resolution url from selected_images or direct url
            front_url = p.get("image_front_url") or ""
            ing_url = p.get("image_ingredients_url") or ""
            nut_url = p.get("image_nutrition_url") or ""
            pack_url = p.get("image_packaging_url") or ""

            # Upgrade to .full.jpg
            if front_url and ".400.jpg" in front_url:
                front_url = front_url.replace(".400.jpg", ".full.jpg")
            if ing_url and ".400.jpg" in ing_url:
                ing_url = ing_url.replace(".400.jpg", ".full.jpg")
            if nut_url and ".400.jpg" in nut_url:
                nut_url = nut_url.replace(".400.jpg", ".full.jpg")
            if pack_url and ".400.jpg" in pack_url:
                pack_url = pack_url.replace(".400.jpg", ".full.jpg")

            return {
                "front": front_url,
                "ingredients": ing_url,
                "nutrition": nut_url,
                "packaging": pack_url
            }
    except Exception:
        pass
    return {}

def search_google_hd_image(page, query, min_size=400):
    url = f"https://www.google.com/search?q={query}&udm=2&hl=vi"
    try:
        page.goto(url, timeout=18000)
        page.wait_for_timeout(2000)

        if "sorry" in page.url:
            return None, "CAPTCHA"

        # Look for visible image cards in grid
        grid_imgs = page.locator("div#rso img, div#search img").all()
        for idx, img in enumerate(grid_imgs[:5]):
            if not img.is_visible():
                continue
            
            try:
                # Click to open full-resolution preview drawer
                img.click(timeout=2500)
                page.wait_for_timeout(1500)
                
                # Extract preview high-res image
                side_imgs = page.locator("img[src^='http']").all()
                for s in side_imgs:
                    src = s.get_attribute("src") or ""
                    if "gstatic" not in src and "google" not in src and any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                        # Test download to verify resolution
                        try:
                            r = requests.get(src, headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
                            if r.status_code == 200 and len(r.content) > 15000:
                                w, h, _ = get_image_info(r.content)
                                if w >= min_size or h >= min_size:
                                    return r.content, src
                        except Exception:
                            pass
            except Exception:
                pass
    except Exception:
        pass
    return None, None

def run_pilot():
    print(f"[*] Đang tải dữ liệu từ file gốc: {EXCEL_SOURCE}")
    wb = openpyxl.load_workbook(EXCEL_SOURCE, data_only=True, read_only=True)
    sheet = wb["Sheet1"]
    rows = list(sheet.iter_rows(values_only=True))[3:23] # 20 items

    cookies = []
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            cookies = json.load(f)

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768}
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        if cookies:
            context.add_cookies(cookies)
        page = context.new_page()

        print(f"\n========================================================")
        print(f"[*] BẮT ĐẦU CHẠY THỬ NGHIỆM 20 SẢN PHẨM MẪU (PILOT 20)")
        print(f"[*] Tìm ảnh Mặt trước (Front HD) & Mặt sau (Back/Label HD)")
        print(f"========================================================\n")

        for idx, r in enumerate(rows, start=1):
            bc = str(r[0] or "").strip()
            name_en = str(r[1] or "").strip()
            name_da = str(r[2] or "").strip()
            brand = str(r[3] or "").strip()
            weight = str(r[10] or "").strip()

            print(f"\n--------------------------------------------------------")
            print(f"[{idx}/20] SP: {name_en[:45]} | BC: {bc}")

            item_res = {
                "STT": idx,
                "Barcode": bc,
                "Tên sản phẩm": name_en,
                "Thương hiệu": brand,
                "Front_Status": "Chưa tìm thấy",
                "Front_Resolution": "",
                "Front_Source": "",
                "Front_Path": "",
                "Back_Status": "Chưa tìm thấy",
                "Back_Type": "",
                "Back_Resolution": "",
                "Back_Source": "",
                "Back_Path": ""
            }

            # ================= 1. OPEN FOOD FACTS =================
            off_data = fetch_off_images(bc) if bc else {}
            
            # --- MẶT TRƯỚC (FRONT) ---
            front_bytes = None
            front_source = ""
            if off_data.get("front"):
                try:
                    r_f = requests.get(off_data["front"], headers=HEADERS, timeout=8)
                    if r_f.status_code == 200:
                        front_bytes = r_f.content
                        front_source = f"OpenFoodFacts ({off_data['front']})"
                except Exception:
                    pass

            # Nếu OFF không có hoặc ảnh quá nhỏ, search Google Images cho Mặt trước
            if not front_bytes:
                query_front = f"{bc} {brand} packshot" if brand else f"{bc} packaging"
                content, src_url = search_google_hd_image(page, query_front, min_size=400)
                if content:
                    front_bytes = content
                    front_source = f"Google_HD ({src_url})"

            # Lưu ảnh mặt trước
            if front_bytes:
                w, h, fmt = get_image_info(front_bytes)
                front_filename = f"{bc}_front.jpg"
                front_save_path = os.path.join(OUTPUT_DIR, front_filename)
                with open(front_save_path, "wb") as f_out:
                    f_out.write(front_bytes)
                item_res["Front_Status"] = "Thành công (HD)"
                item_res["Front_Resolution"] = f"{w}x{h} ({len(front_bytes)//1024} KB)"
                item_res["Front_Source"] = front_source
                item_res["Front_Path"] = front_save_path
                print(f"  [+] Mặt trước: TÌM THẤY SIÊU NÉT -> {w}x{h} ({len(front_bytes)//1024} KB)")
            else:
                print(f"  [-] Mặt trước: Không tìm thấy ảnh đạt chuẩn")

            # --- MẶT SAU (BACK / LABEL) ---
            back_bytes = None
            back_source = ""
            back_type = ""

            # Check OFF ingredients / packaging / nutrition
            if off_data.get("ingredients"):
                try:
                    r_b = requests.get(off_data["ingredients"], headers=HEADERS, timeout=8)
                    if r_b.status_code == 200:
                        back_bytes = r_b.content
                        back_source = f"OpenFoodFacts ({off_data['ingredients']})"
                        back_type = "Nhãn thành phần (Ingredients Label)"
                except Exception:
                    pass
            elif off_data.get("packaging"):
                try:
                    r_b = requests.get(off_data["packaging"], headers=HEADERS, timeout=8)
                    if r_b.status_code == 200:
                        back_bytes = r_b.content
                        back_source = f"OpenFoodFacts ({off_data['packaging']})"
                        back_type = "Mặt sau bao bì (Back Packaging)"
                except Exception:
                    pass

            # Nếu OFF không có, search Google Images với từ khóa Mặt Sau
            if not back_bytes:
                back_queries = [
                    f'{bc} "back"',
                    f'{bc} "ingredients"',
                    f'{bc} "nutrition label"',
                    f'{brand} {name_en.split()[0]} "back packaging"'
                ]
                for q_b in back_queries:
                    content_b, src_b = search_google_hd_image(page, q_b, min_size=350)
                    if content_b:
                        back_bytes = content_b
                        back_source = f"Google_Web ({src_b})"
                        back_type = "Ảnh tìm kiếm Google (Back/Label)"
                        break

            # Lưu ảnh mặt sau
            if back_bytes:
                w_b, h_b, fmt_b = get_image_info(back_bytes)
                back_filename = f"{bc}_back.jpg"
                back_save_path = os.path.join(OUTPUT_DIR, back_filename)
                with open(back_save_path, "wb") as b_out:
                    b_out.write(back_bytes)
                item_res["Back_Status"] = "Thành công (HD)"
                item_res["Back_Type"] = back_type
                item_res["Back_Resolution"] = f"{w_b}x{h_b} ({len(back_bytes)//1024} KB)"
                item_res["Back_Source"] = back_source
                item_res["Back_Path"] = back_save_path
                print(f"  [+] Mặt sau: TÌM THẤY -> {back_type} | {w_b}x{h_b} ({len(back_bytes)//1024} KB)")
            else:
                print(f"  [-] Mặt sau: Không tìm thấy")

            results.append(item_res)
            time.sleep(1)

        browser.close()

    # Xuất báo cáo Excel
    print(f"\n[*] Đang tạo bảng đối soát Excel: {REPORT_EXCEL}")
    wb_out = openpyxl.Workbook()
    ws = wb_out.active
    ws.title = "Pilot 20 Images Audit"

    headers_list = [
        "STT", "Barcode", "Tên sản phẩm", "Thương hiệu",
        "Trạng thái Mặt trước", "Độ phân giải Mặt trước", "Nguồn Mặt trước", "Đường dẫn file Mặt trước",
        "Trạng thái Mặt sau", "Loại ảnh Mặt sau", "Độ phân giải Mặt sau", "Nguồn Mặt sau", "Đường dẫn file Mặt sau"
    ]
    ws.append(headers_list)

    for item in results:
        ws.append([
            item["STT"], item["Barcode"], item["Tên sản phẩm"], item["Thương hiệu"],
            item["Front_Status"], item["Front_Resolution"], item["Front_Source"], item["Front_Path"],
            item["Back_Status"], item["Back_Type"], item["Back_Resolution"], item["Back_Source"], item["Back_Path"]
        ])

    wb_out.save(REPORT_EXCEL)
    print(f"[+] BÁO CÁO THỬ NGHIỆM ĐÃ XUẤT THÀNH CÔNG: {REPORT_EXCEL}")

if __name__ == "__main__":
    run_pilot()
