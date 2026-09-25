import json, sys, os
from pathlib import Path
from PIL import Image, ImageOps

sys.stdout.reconfigure(encoding='utf-8')

CONFIRMED_21 = {
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
        "brand": "Cock Brand",
        "product_name": "Specialty Food Seasoning",
        "net_weight": "100g",
        "variant": "",
        "pos_sku": "",
        "pos_product_name": ""
    }
}

def apply():
    json_path = Path("output/g1_delivery/G1_products.json")
    if not json_path.exists():
        print("JSON not found")
        return
    with open(json_path, "r", encoding="utf-8") as f:
        products = json.load(f)

    updated = 0
    for p in products:
        fname = p.get("original_image")
        if fname in CONFIRMED_21:
            info = CONFIRMED_21[fname]
            p["barcode"] = info["barcode"]
            p["brand"] = info["brand"]
            p["product_name"] = info["product_name"]
            p["net_weight"] = info["net_weight"]
            p["variant"] = info["variant"]
            p["pos_sku"] = info["pos_sku"]
            p["pos_product_name"] = info["pos_product_name"]
            p["status"] = "CONFIRMED"
            p["detection_method"] = "manual_visual_confirmed"
            
            # Ensure website front image is updated
            dest_front = f"website_front_images/{info['barcode']}.jpeg"
            p["website_front_image"] = dest_front
            
            # Crop/orient front image
            orig_src = Path("G1_original") / fname
            dest_path = Path("output/g1_delivery") / dest_front
            if orig_src.exists():
                with Image.open(orig_src) as im:
                    im_t = ImageOps.exif_transpose(im)
                    # For 2-sided photo, front packaging is typically left or top half
                    w, h = im_t.size
                    if w > h:
                        crop_front = im_t.crop((0, 0, w//2, h))
                    else:
                        crop_front = im_t.crop((0, 0, w, h//2))
                    crop_front.convert("RGB").save(dest_path, format="JPEG", quality=95)
            
            updated += 1

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

    print(f"Successfully injected and confirmed all {updated} products!")

if __name__ == '__main__':
    apply()
