#!/usr/bin/env python3
"""
scripts/repair_39_error_backs.py
---------------------------------
Sửa toàn diện 39 ảnh mặt sau bị lỗi (cắt hụt, cắt ngang chai lọ, nhận diện nhầm).
Đọc ảnh gốc ở độ phân giải tối đa, crop chính xác 100% toàn bộ bao bì/chai lọ
rồi ghi đè vào D:\Work\shopify\output\catalog_pairs\tagged\back-v2
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance
import pillow_heif

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

pillow_heif.register_heif_opener()

ROOT = Path(__file__).resolve().parent.parent

# Tọa độ tỷ lệ chuẩn [x0, y0, x1, y1] (0.0 đến 1.0) và góc xoay (nếu cần)
CROP_BOXES: dict[str, dict] = {
    # 01: Tiparos Fish Sauce 700 ml (Chai bên phải trọn vẹn từ nắp trắng đến đáy)
    "021723778885": {"box": (0.62, 0.10, 0.96, 0.92)},
    
    # 02: India Gate Premium Pure Basmati Rice 1 kg (Túi bên phải trọn vẹn)
    "0690225301244": {"box": (0.49, 0.10, 0.84, 0.87)},
    
    # 03: Lee Kum Kee Honey & Soy Sauce (Túi bên trái trọn vẹn)
    "078895131178": {"box": (0.05, 0.10, 0.49, 0.90)},
    
    # 04: Lee Kum Kee Kung Pao Chicken Sauce (Túi bên trái trọn vẹn)
    "078895148299": {"box": (0.05, 0.10, 0.47, 0.89)},
    
    # 05: Wang Korea Seasoned Seaweed (Nửa dưới trọn vẹn 3 gói kèm nhãn phụ & barcode)
    "087703007796": {"box": (0.06, 0.48, 0.98, 0.98)},
    
    # 06: New Chin Hoa BBQ Pork Buns (Gói dưới chứa toàn bộ bảng dinh dưỡng & thông tin)
    "3439868888814": {"box": (0.10, 0.44, 0.93, 0.98)},
    
    # 07: Three Coconut Tree Lotus Root (Gói dưới chứa bảng dinh dưỡng, thông tin & barcode)
    "4045198904330": {"box": (0.05, 0.43, 0.94, 0.88)},
    
    # 08: Taiwan Dessert Mico Mochi Calamansi (Hộp bên phải chứa nhãn thành phần)
    "4711931037855": {"box": (0.53, 0.40, 0.91, 0.69)},
    
    # 09: White King Puto Cake Mix (Mặt hông bên phải trọn vẹn từ đỉnh tới đáy)
    "4800110091556": {"box": (0.54, 0.04, 0.86, 0.94)},
    
    # 10: Kung Fu Dumplings Chicken & Mushroom (Gói dưới trọn vẹn hướng dẫn, dinh dưỡng, barcode)
    "5060284550153": {"box": (0.04, 0.51, 0.96, 0.97)},
    
    # 11: Shen Dan Cooked Salted Duck Eggs (Toàn bộ khay trứng kèm nhãn)
    "6913084222296": {"box": (0.05, 0.08, 0.85, 0.78)},
    
    # 12: Pearl River Bridge Superior Light Soy Sauce (Chai bên trái trọn vẹn từ nắp đến đáy)
    "6921180820025": {"box": (0.14, 0.05, 0.48, 0.95)},
    
    # 13: Pearl River Bridge Wei Ji Xian Soy Sauce (Chai bên trái trọn vẹn từ nắp vàng đến đáy)
    "6947593021071": {"box": (0.01, 0.01, 0.47, 0.98)},
    
    # 14: Pasco Mild Garam Masala Paste (Hũ bên trái trọn vẹn từ nắp đến đáy)
    "7178600000270": {"box": (0.02, 0.34, 0.43, 0.84)},
    
    # 15: Shinode Sushi Rice 10 kg (Toàn bộ bao gạo mặt sau)
    "8005734101568": {"box": (0.10, 0.03, 0.88, 0.98)},
    
    # 16: Wadakyu Katsuobushi 40 g (Túi bên phải trọn vẹn)
    "8436566460033": {"box": (0.48, 0.01, 0.98, 0.88)},
    
    # 17: Mega Sardines in Tomato Sauce (Lon bên phải trọn vẹn từ miệng lon đến đáy)
    "857451000314": {"box": (0.47, 0.29, 0.82, 0.79)},
    
    # 18: Asian Pearl Giant Seaperch (Gói cá bên trái trọn vẹn từ đầu đến đuôi)
    "8716789052834": {"box": (0.05, 0.10, 0.45, 0.95)},
    
    # 19: S. Khonkaen Naem Sausage (Thanh nem chua ở giữa trọn vẹn nằm ngang)
    "8720165077120": {"box": (0.07, 0.40, 0.90, 0.64)},
    
    # 20: Royal Tiger Gold Jasmine Rice 5 kg (Toàn bộ bao gạo mặt sau)
    "8720301100453": {"box": (0.09, 0.03, 0.93, 0.96)},
    
    # 21: Asian Choice Surimi Sticks 500 g (Toàn bộ gói thanh cua mặt sau)
    "8720663432667": {"box": (0.06, 0.01, 0.94, 0.96)},
    
    # 22: Orion Choco Pie (Hộp đứng bên phải chứa mã vạch & dinh dưỡng)
    "8801117584115": {"box": (0.69, 0.22, 0.96, 0.79)},
    
    # 23: Busan Fishcake Squares 300 g (Túi chả cá bên phải trọn vẹn)
    "8803122006200": {"box": (0.47, 0.06, 0.82, 0.88)},
    
    # 24: 7drops Apple Soju (Chai bên trái trọn vẹn từ nắp đỏ đến đáy)
    "8809409972220": {"box": (0.14, 0.14, 0.42, 0.86)},
    
    # 25: Mooijer Cambodian Fragrant Jasmine Rice 20 kg (Toàn bộ bao gạo mặt sau)
    "8847100983893": {"box": (0.03, 0.01, 0.86, 0.96)},
    
    # 26: Lobo Yum Yentafo Sauce (Gói bên trái trọn vẹn thông tin & barcode)
    "8850030007706": {"box": (0.03, 0.06, 0.52, 0.98)},
    
    # 27: Pantai Norasingh Fish Sauce 300 ml (Chai bên phải trọn vẹn từ nắp vàng đến đáy)
    "8850058006484": {"box": (0.45, 0.04, 0.78, 0.96)},
    
    # 28: Dek Som Boon Bar-B-Q Steak Sauce (Chai bên trái trọn vẹn từ nắp đen đến đáy)
    "8850206227136": {"box": (0.15, 0.01, 0.47, 0.97)},
    
    # 29: Mogu Mogu Mango Drink (Chai ở giữa trọn vẹn từ nắp trắng đến đáy)
    "8850389113264": {"box": (0.38, 0.16, 0.60, 0.91)},
    
    # 30: Squid Brand Fish Sauce 60 ml (Chai bên trái trọn vẹn nhãn dinh dưỡng & thành phần)
    "8850620000605": {"box": (0.08, 0.01, 0.49, 0.95)},
    
    # 31: Lotus Pickled Bamboo Shoot (Gói bên phải, xoay 180 độ đúng chiều)
    "8852032625124": {"box": (0.48, 0.04, 0.94, 0.98), "rotate": 180},
    
    # 32: Thai Dancer Teriyaki Mayo Sauce 450 ml (Chai bên trái trọn vẹn từ nắp xanh đến đáy)
    "8852646104503": {"box": (0.10, 0.03, 0.49, 0.91)},
    
    # 33: Royal Thai Glutinous Rice 10 kg (Toàn bộ bao gạo mặt sau)
    "8853969000954": {"box": (0.03, 0.02, 0.95, 0.98)},
    
    # 34: Kaijae Rice Glutinous Rice 5 kg (Toàn bộ bao gạo mặt sau)
    "8858901603828": {"box": (0.08, 0.02, 0.96, 0.96)},
    
    # 35: Asian Home Gourmet Singapore Coconut Rice (Gói bên phải trọn vẹn)
    "8886390204011": {"box": (0.51, 0.08, 0.96, 0.91)},
    
    # 36: India Gate Idli Rice 5 kg (Toàn bộ bao gạo mặt sau)
    "8908014100018": {"box": (0.08, 0.05, 0.85, 0.97)},
    
    # 37: Minh Duong Dien Bao Sweet Potato Vermicelli (Gói miến bên phải trọn vẹn)
    "8938506580127": {"box": (0.48, 0.01, 0.95, 0.98)},
    
    # 38: Glico Pocky Strawberry Flavour (Mặt hông bên trái trọn vẹn từ đỉnh tới đáy)
    "8990044000017": {"box": (0.13, 0.14, 0.33, 0.91)},
    
    # 39: Unico Lava Bites Matcha Strawberry (Hộp bên phải chứa mã vạch, date, thông tin)
    "9555907800525": {"box": (0.56, 0.28, 0.91, 0.69)},
}


def enhance_back_hq(img: Image.Image, max_long: int = 2400) -> Image.Image:
    width, height = img.size
    if max(width, height) > max_long:
        scale = max_long / max(width, height)
        img = img.resize((max(1, int(width * scale)), max(1, int(height * scale))), Image.Resampling.LANCZOS)
    img = ImageEnhance.Sharpness(img).enhance(1.25)
    img = ImageEnhance.Contrast(img).enhance(1.08)
    return img


def repair_all_39():
    print("===============================================================================")
    print("       XỬ LÝ LẠI VÀ GHI ĐÈ 39 ẢNH MẶT SAU BỊ LỖI CẮT HỤT VÀO BACK-V2          ")
    print("===============================================================================\n")

    analysis_file = ROOT / "output/catalog_pairs/review/errors_39_analysis.json"
    analysis_data = json.loads(analysis_file.read_text(encoding="utf-8"))

    dest_dir = ROOT / "output/catalog_pairs/tagged/back-v2"
    preview_dir = ROOT / "output/catalog_pairs/review/fixed_39_backs"
    dest_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    success_count = 0

    for idx, item in enumerate(analysis_data, 1):
        bc = item["barcode"]
        src_path = item.get("source")
        if not src_path or not Path(src_path).exists():
            print(f"[-] #{idx:02d} {bc}: Không tìm thấy file gốc {src_path}")
            continue

        cfg = CROP_BOXES.get(bc)
        if not cfg:
            print(f"[-] #{idx:02d} {bc}: Chưa định nghĩa crop box")
            continue

        box_pct = cfg["box"]
        rot = cfg.get("rotate", 0)

        try:
            with Image.open(src_path) as raw_img:
                img = ImageOps.exif_transpose(raw_img)
                w, h = img.size

                x0 = int(round(w * box_pct[0]))
                y0 = int(round(h * box_pct[1]))
                x1 = int(round(w * box_pct[2]))
                y1 = int(round(h * box_pct[3]))

                cropped = img.crop((x0, y0, x1, y1))
                if rot != 0:
                    cropped = cropped.rotate(rot, expand=True, resample=Image.Resampling.BICUBIC)

                fixed_back = enhance_back_hq(cropped)

                # 1. Ghi đè vào back-v2
                out_path = dest_dir / f"{bc}-back.jpg"
                fixed_back.save(out_path, "JPEG", quality=95, subsampling=0)

                # 2. Lưu bản xem trước
                preview_path = preview_dir / f"{idx:02d}_{bc}-back_fixed.jpg"
                fixed_back.save(preview_path, "JPEG", quality=90)

                print(f"[+] #{idx:02d} Đã sửa {bc}: Box({x0},{y0},{x1},{y1}) -> {out_path.name}")
                success_count += 1

        except Exception as e:
            print(f"[-] #{idx:02d} Lỗi khi xử lý {bc}: {e}")

    print(f"\n=== HOÀN TẤT: Đã sửa và ghi đè {success_count}/{len(analysis_data)} ảnh mặt sau vào back-v2 ===")


if __name__ == "__main__":
    repair_all_39()
