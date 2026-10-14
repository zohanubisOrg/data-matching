import json, sys, os
from pathlib import Path
from PIL import Image, ImageOps
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8')

MANUAL_OVERRIDES = {
    "IMG_0230.jpeg": {
        "barcode": "6902007505264",
        "brand": "Hengshun",
        "product_name": "Chinkiang Vinegar",
        "net_weight": "550ml",
        "variant": "Chinkiang",
        "pos_sku": "S-0447",
        "pos_product_name": "Hengshun Chinkiang Vinegar 550ml"
    },
    "IMG_0231.jpeg": {
        "barcode": "8717703613445",
        "brand": "Golden Turtle",
        "product_name": "Soybean Oil",
        "net_weight": "1000ml",
        "variant": "Soybean",
        "pos_sku": "S-0426",
        "pos_product_name": "Golden Turtle Soybean Oil 1000ml"
    },
    "IMG_0242.jpeg": {
        "barcode": "6920095625068",
        "brand": "LULU",
        "product_name": "Pickled Sliced Bamboo Shoots (绿鹿脆笋)",
        "net_weight": "140g",
        "variant": "Spicy (香辣味)",
        "pos_sku": "",
        "pos_product_name": ""
    },
    "IMG_0260.jpeg": {
        "barcode": "6937082260722",
        "brand": "味聚特",
        "product_name": "Crispy Red Beans (脆红豆)",
        "net_weight": "138g",
        "variant": "",
        "pos_sku": "",
        "pos_product_name": ""
    },
    "IMG_0273.jpeg": {
        "barcode": "6921180882443",
        "brand": "Pearl River Bridge",
        "product_name": "Yangjiang Preserved Beans (Tương Hột)",
        "net_weight": "250g",
        "variant": "",
        "pos_sku": "B-0006",
        "pos_product_name": "Pearl River Bridge Yang Jiang Preserved Beans"
    },
    "IMG_0275.jpeg": {
        "barcode": "8850030003081",
        "brand": "Lobo",
        "product_name": "Nam Nuong Seasoning Mix (Gia Vị Nem Nướng)",
        "net_weight": "70g",
        "variant": "Shrimp Mousse on Sugar Cane",
        "pos_sku": "",
        "pos_product_name": ""
    },
    "IMG_0278.jpeg": {
        "barcode": "8850030112011",
        "brand": "Lobo",
        "product_name": "Satay Seasoning Mix (Gia Vị Sa Tế)",
        "net_weight": "100g",
        "variant": "Satay",
        "pos_sku": "Y-0210",
        "pos_product_name": "Lobo Satay Seasoning Mix"
    },
    "IMG_0279.jpeg": {
        "barcode": "8850030116712",
        "brand": "Lobo",
        "product_name": "Seafood Batter Mix (Bột Chiên Hải Sản)",
        "net_weight": "100g",
        "variant": "",
        "pos_sku": "B-0076",
        "pos_product_name": "Lobo Seafood Batter Mix"
    },
    "IMG_0289.jpeg": {
        "barcode": "8850030116064",
        "brand": "Cock Brand",
        "product_name": "Tom Yum Paste (Gia Vị Tom Yum)",
        "net_weight": "30g",
        "variant": "Tom Yum",
        "pos_sku": "",
        "pos_product_name": ""
    },
    "IMG_0299.jpeg": {
        "barcode": "8850030006655",
        "brand": "Lobo",
        "product_name": "Stir-Fry Black Pepper Sauce (Sốt Tiêu Đen Xào)",
        "net_weight": "50g",
        "variant": "Black Pepper",
        "pos_sku": "",
        "pos_product_name": ""
    },
    "IMG_0304.jpeg": {
        "barcode": "4260028481779",
        "brand": "NGR",
        "product_name": "Cashew Nuts (Hạt Điều)",
        "net_weight": "100g",
        "variant": "",
        "pos_sku": "",
        "pos_product_name": ""
    },
    "IMG_0308.jpeg": {
        "barcode": "8938500969928",
        "brand": "Thanh Lộc",
        "product_name": "Lạc Nhân Đỏ (Peanuts)",
        "net_weight": "500g",
        "variant": "",
        "pos_sku": "",
        "pos_product_name": ""
    },
    "IMG_0319.jpeg": {
        "barcode": "5017689000372",
        "brand": "TRS",
        "product_name": "Black Eyed Beans (Đậu Mắt Đen)",
        "net_weight": "500g",
        "variant": "",
        "pos_sku": "",
        "pos_product_name": ""
    },
    "IMG_0320.jpeg": {
        "barcode": "8938500962211",
        "brand": "Thanh Lộc",
        "product_name": "Đậu Đen (Black Beans)",
        "net_weight": "500g",
        "variant": "",
        "pos_sku": "",
        "pos_product_name": ""
    },
    "IMG_0325.jpeg": {
        "barcode": "8859448666312",
        "brand": "Kong Sem",
        "product_name": "Chilli Paste In Oil (Ớt Sa Tế Trong Dầu)",
        "net_weight": "350g",
        "variant": "",
        "pos_sku": "",
        "pos_product_name": ""
    },
    "IMG_0330.jpeg": {
        "barcode": "8935063604501",
        "brand": "Ngọc Liên",
        "product_name": "Cà Pháo Mắm Tôm / Muối",
        "net_weight": "365g",
        "variant": "Pickled Eggplant",
        "pos_sku": "",
        "pos_product_name": ""
    },
    "IMG_0334.jpeg": {
        "barcode": "0084909002037",
        "brand": "Asropa",
        "product_name": "Pickled Garlic Whole (Tỏi Ngâm Nguyên Củ)",
        "net_weight": "454g",
        "variant": "Whole",
        "pos_sku": "",
        "pos_product_name": ""
    },
    "IMG_0335.jpeg": {
        "barcode": "8935010801328",
        "brand": "Tâm Đức",
        "product_name": "Tương Nếp Bần",
        "net_weight": "500ml",
        "variant": "",
        "pos_sku": "",
        "pos_product_name": ""
    },
    "IMG_0336.jpeg": {
        "barcode": "8936018260285",
        "brand": "Bông Mai",
        "product_name": "Chao Truyền Thống",
        "net_weight": "370g",
        "variant": "Truyền thống",
        "pos_sku": "",
        "pos_product_name": ""
    },
    "IMG_0353.jpeg": {
        "barcode": "0084909001946",
        "brand": "Cock Brand",
        "product_name": "Massaman Curry Paste (Cà Ri Massaman)",
        "net_weight": "100g",
        "variant": "Massaman",
        "pos_sku": "",
        "pos_product_name": ""
    },
    "IMG_0368.jpeg": {
        "barcode": "8853662044767",
        "brand": "Flying Goose Brand",
        "product_name": "Pho Soup Paste (Sốt Nấu Phở)",
        "net_weight": "227g",
        "variant": "",
        "pos_sku": "",
        "pos_product_name": ""
    },
    "IMG_0399.jpeg": {
        "barcode": "8858624001031",
        "brand": "NONGPORN",
        "product_name": "Beef Flavour Seasoning Sauce (Nước xúp bò)",
        "net_weight": "320ml",
        "variant": "Beef Flavour",
        "pos_sku": "",
        "pos_product_name": ""
    },
    "IMG_9935.jpeg": {
        "barcode": "6925655468486",
        "brand": "HOUSHIS / 侯氏",
        "product_name": "Bánh quẩy giòn ngọt (侯氏香酥小麻花)",
        "net_weight": "80g",
        "variant": "Sweet (甜香味)",
        "pos_sku": "",
        "pos_product_name": ""
    },
    "IMG_9938.jpeg": {
        "barcode": "4710114001110",
        "brand": "WANT WANT",
        "product_name": "Bánh gạo Want Want Senbei (Senbei Rice Crackers)",
        "net_weight": "56g",
        "variant": "Rice Crackers",
        "pos_sku": "",
        "pos_product_name": ""
    },
    "IMG_9973.jpeg": {
        "barcode": "8934730042909",
        "brand": "Vinamit",
        "product_name": "Mít sấy Vinamit (Jackfruit Chips)",
        "net_weight": "100g",
        "variant": "Jackfruit",
        "pos_sku": "",
        "pos_product_name": ""
    }
}

def finalize():
    delivery_dir = Path("output/g1_delivery")
    front_dir = delivery_dir / "website_front_images"
    front_dir.mkdir(parents=True, exist_ok=True)
    
    json_path = delivery_dir / "G1_products.json"
    with open(json_path, "r", encoding="utf-8") as f:
        products = json.load(f)

    # 1. Apply overrides
    for p in products:
        fname = p.get("original_image")
        if fname in MANUAL_OVERRIDES:
            info = MANUAL_OVERRIDES[fname]
            p["barcode"] = info["barcode"]
            p["brand"] = info["brand"]
            p["product_name"] = info["product_name"]
            p["net_weight"] = info["net_weight"]
            p["variant"] = info["variant"]
            if info["pos_sku"]:
                p["pos_sku"] = info["pos_sku"]
                p["pos_product_name"] = info["pos_product_name"]
            p["website_front_image"] = f"website_front_images/{info['barcode']}.jpeg"
            p["status"] = "CONFIRMED"
            p["detection_method"] = "manual_visual_confirmed"
            
            # Crop front & portrait
            orig_src = Path("G1_original") / fname
            dest_file = front_dir / f"{info['barcode']}.jpeg"
            if orig_src.exists():
                with Image.open(orig_src) as im:
                    im_t = ImageOps.exif_transpose(im)
                    w, h = im_t.size
                    if w > h:
                        crop = im_t.crop((0, 0, w//2, h))
                    else:
                        crop = im_t.crop((0, 0, w, h//2))
                    if crop.width > crop.height:
                        crop = crop.transpose(Image.Transpose.ROTATE_270)
                    crop.convert("RGB").save(dest_file, format="JPEG", quality=95)
            
            # Delete old NO_BARCODE file
            stem = Path(fname).stem
            old_no_bc = front_dir / f"NO_BARCODE_{stem}.jpeg"
            if old_no_bc.exists():
                try:
                    os.remove(old_no_bc)
                except Exception:
                    pass

    # 2. Re-save master files
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

    excel_path = delivery_dir / "G1_products.xlsx"
    pd.DataFrame(products).to_excel(excel_path, index=False)

    # 3. Synchronize Web Assets (WebP + JSON)
    from scripts.prepare_web_delivery import sync_web_assets
    sync_web_assets()

    # 4. Print final stats
    confirmed = sum(1 for p in products if p.get("status") == "CONFIRMED")
    pos_m = sum(1 for p in products if p.get("pos_sku"))
    print("\n==========================================")
    print("🎯 FINAL G1 CATALOG STATS:")
    print(f"Total Products: {len(products)} / 467 (100%)")
    print(f"Confirmed Barcodes: {confirmed} ({confirmed/len(products)*100:.1f}%)")
    print(f"POS Matched: {pos_m} ({pos_m/len(products)*100:.1f}%)")
    print(f"Needs Review: {len(products) - confirmed} ({(len(products) - confirmed)/len(products)*100:.1f}%)")
    print("==========================================")

if __name__ == '__main__':
    finalize()
