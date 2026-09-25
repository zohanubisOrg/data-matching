import json, sys, os, shutil
from pathlib import Path
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8')

VERIFIED_BARCODES = {
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
    }
}

def main():
    delivery_dir = Path("output/g1_delivery")
    front_dir = delivery_dir / "website_front_images"
    front_dir.mkdir(parents=True, exist_ok=True)
    
    json_path = delivery_dir / "G1_products.json"
    if not json_path.exists():
        print("JSON not found")
        return
        
    with open(json_path, "r", encoding="utf-8") as f:
        products = json.load(f)

    print("--- UPDATING AND RENAMING NO_BARCODE IMAGES ---")
    for fname, info in VERIFIED_BARCODES.items():
        bc = info["barcode"]
        stem = Path(fname).stem
        old_no_bc_file = front_dir / f"NO_BARCODE_{stem}.jpeg"
        new_bc_file = front_dir / f"{bc}.jpeg"
        
        # 1. Generate/Ensure new barcode front crop in portrait orientation
        orig_img_path = Path("G1_original") / fname
        if orig_img_path.exists():
            with Image.open(orig_img_path) as im:
                im_t = ImageOps.exif_transpose(im)
                w, h = im_t.size
                
                # Crop front view (left half or top half)
                if w > h:
                    front_crop = im_t.crop((0, 0, w//2, h))
                else:
                    front_crop = im_t.crop((0, 0, w, h//2))
                
                # If still landscape, rotate to portrait
                if front_crop.width > front_crop.height:
                    front_crop = front_crop.transpose(Image.Transpose.ROTATE_270)
                
                front_crop.convert("RGB").save(new_bc_file, format="JPEG", quality=95)
                print(f"✅ Generated {new_bc_file.name} (size: {front_crop.size})")

        # 2. Delete outdated NO_BARCODE file
        if old_no_bc_file.exists() and old_no_bc_file != new_bc_file:
            try:
                os.remove(old_no_bc_file)
                print(f"🗑️ Deleted legacy: {old_no_bc_file.name}")
            except Exception as e:
                print(f"Could not delete {old_no_bc_file.name}: {e}")

        # 3. Clean up legacy files from web/public/products/front/
        legacy_webp = Path("web/public/products/front") / f"NO_BARCODE_{stem}.webp"
        if legacy_webp.exists():
            try:
                os.remove(legacy_webp)
                print(f"🗑️ Deleted legacy webp: {legacy_webp.name}")
            except Exception:
                pass

        # 4. Update product in memory
        found = False
        for p in products:
            if p.get("original_image") == fname:
                p["barcode"] = bc
                p["brand"] = info["brand"]
                p["product_name"] = info["product_name"]
                p["net_weight"] = info["net_weight"]
                p["variant"] = info["variant"]
                p["pos_sku"] = info["pos_sku"]
                p["pos_product_name"] = info["pos_product_name"]
                p["website_front_image"] = f"website_front_images/{bc}.jpeg"
                p["status"] = "CONFIRMED"
                p["detection_method"] = "manual_visual_confirmed"
                found = True
                break
        
        if not found:
            # Append if not present
            products.append({
                "barcode": bc,
                "brand": info["brand"],
                "product_name": info["product_name"],
                "net_weight": info["net_weight"],
                "variant": info["variant"],
                "pos_sku": info["pos_sku"],
                "pos_product_name": info["pos_product_name"],
                "original_image": fname,
                "website_front_image": f"website_front_images/{bc}.jpeg",
                "status": "CONFIRMED",
                "detection_method": "manual_visual_confirmed"
            })

    # Save JSON & Excel
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

    import pandas as pd
    excel_path = delivery_dir / "G1_products.xlsx"
    try:
        pd.DataFrame(products).to_excel(excel_path, index=False)
        print("✅ Updated G1_products.xlsx")
    except Exception:
        pass

    # Run sync to web
    from scripts.prepare_web_delivery import sync_web_assets
    sync_web_assets()
    print("✅ All assets synchronized to web/public successfully!")

if __name__ == '__main__':
    main()
