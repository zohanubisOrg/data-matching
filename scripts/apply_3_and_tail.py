import json, sys, os
from pathlib import Path
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8')

THE_3_ITEMS = {
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

    for fname, info in THE_3_ITEMS.items():
        bc = info["barcode"]
        stem = Path(fname).stem
        old_no_bc = front_dir / f"NO_BARCODE_{stem}.jpeg"
        new_bc_file = front_dir / f"{bc}.jpeg"
        
        orig_img_path = Path("G1_original") / fname
        if orig_img_path.exists():
            with Image.open(orig_img_path) as im:
                im_t = ImageOps.exif_transpose(im)
                w, h = im_t.size
                if w > h:
                    front_crop = im_t.crop((0, 0, w//2, h))
                else:
                    front_crop = im_t.crop((0, 0, w, h//2))
                if front_crop.width > front_crop.height:
                    front_crop = front_crop.transpose(Image.Transpose.ROTATE_270)
                front_crop.convert("RGB").save(new_bc_file, format="JPEG", quality=95)
                print(f"✅ Created {new_bc_file.name}")
        
        if old_no_bc.exists():
            try:
                os.remove(old_no_bc)
                print(f"🗑️ Deleted legacy: {old_no_bc.name}")
            except Exception:
                pass
        
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

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

    import pandas as pd
    excel_path = delivery_dir / "G1_products.xlsx"
    try:
        pd.DataFrame(products).to_excel(excel_path, index=False)
    except Exception:
        pass

    from scripts.prepare_web_delivery import sync_web_assets
    sync_web_assets()
    print("✅ All 3 items resolved and synced to web!")

if __name__ == '__main__':
    main()
