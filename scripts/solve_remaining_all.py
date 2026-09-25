import sys, os, json, time
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance
import zxingcpp
from google import genai
from google.genai import types
from io import BytesIO
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

KEYS = [
    "AIzaSyCl8NJtBaFVjGfSSL2n5mFiCVysQWrn-UI",
    "AQ.Ab8RN6LDdgf38KYpVPhlWa3M1wrjxF758sKy04_8xSmWntDV5A"
]

TARGETS_3 = ['IMG_0399.jpeg', 'IMG_9935.jpeg', 'IMG_9938.jpeg']
TAIL_27 = [
    'IMG_9969.jpeg', 'IMG_9970.jpeg', 'IMG_9971.jpeg', 'IMG_9972.jpeg',
    'IMG_9973.jpeg', 'IMG_9976.jpeg', 'IMG_9977.jpeg', 'IMG_9978.jpeg',
    'IMG_9979.jpeg', 'IMG_9980.jpeg', 'IMG_9981.jpeg', 'IMG_9982.jpeg',
    'IMG_9983.jpeg', 'IMG_9984.jpeg', 'IMG_9986.jpeg', 'IMG_9987.jpeg',
    'IMG_9988.jpeg', 'IMG_9989.jpeg', 'IMG_9990.jpeg', 'IMG_9991.jpeg',
    'IMG_9993.jpeg', 'IMG_9994.jpeg', 'IMG_9995.jpeg', 'IMG_9996.jpeg',
    'IMG_9997.jpeg', 'IMG_9998.jpeg', 'IMG_9999.jpeg'
]

ALL_TARGETS = TARGETS_3 + TAIL_27

def validate_ean_upc_checksum(digits: str) -> bool:
    if not digits.isdigit() or len(digits) not in (8, 12, 13, 14):
        return False
    check_digit = int(digits[-1])
    payload = digits[:-1]
    if len(digits) == 8:
        weights = [3, 1] * 3 + [3]
    elif len(digits) == 12:
        weights = [3, 1] * 5 + [3]
    elif len(digits) == 13:
        weights = [1, 3] * 6
    elif len(digits) == 14:
        weights = [3, 1] * 6 + [3]
    else:
        return False
    calc_sum = sum(int(d) * w for d, w in zip(payload, weights))
    calc_check = (10 - (calc_sum % 10)) % 10
    return calc_check == check_digit

def scan_offline_zxing(im_t):
    w, h = im_t.size
    crops = [
        im_t,
        im_t.crop((0, 0, w//2, h)),
        im_t.crop((w//2, 0, w, h)),
        im_t.crop((0, 0, w, h//2)),
        im_t.crop((0, h//2, w, h)),
    ]
    for c in crops:
        for rot in [0, 90, 180, 270]:
            r_im = c if rot == 0 else c.rotate(rot, expand=True)
            for r in zxingcpp.read_barcodes(r_im):
                t = str(r.text).strip()
                if t.isdigit() and validate_ean_upc_checksum(t):
                    return t
            enh = ImageEnhance.Contrast(r_im).enhance(2.0)
            for r in zxingcpp.read_barcodes(enh):
                t = str(r.text).strip()
                if t.isdigit() and validate_ean_upc_checksum(t):
                    return t
    return None

def main():
    print(f"Analyzing {len(ALL_TARGETS)} images...")
    
    # Load POS database
    pos_data = []
    if os.path.exists("docs/G1_pos.csv"):
        df = pd.read_csv("docs/G1_pos.csv")
        for _, row in df.iterrows():
            pos_data.append({
                "sku": str(row.get("Item Number", "")).strip(),
                "name": str(row.get("Item Description", "")).strip(),
                "barcode": str(row.get("Barcode", "")).strip()
            })

    client = genai.Client(api_key=KEYS[1], http_options={"timeout": 60000})

    results = {}
    for fname in ALL_TARGETS:
        path = os.path.join("G1_original", fname)
        if not os.path.exists(path):
            continue
        
        with Image.open(path) as im:
            im_t = ImageOps.exif_transpose(im)
            
            # 1. Try offline barcode
            bc = scan_offline_zxing(im_t)
            
            # 2. Extract vision info
            w, h = im_t.size
            if max(w, h) > 1600:
                scale = 1600 / max(w, h)
                im_t_scaled = im_t.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
            else:
                im_t_scaled = im_t
            
            buf = BytesIO()
            im_t_scaled.convert("RGB").save(buf, format="JPEG", quality=90)
            img_bytes = buf.getvalue()
        
        prompt = "Look at this packaging image (both sides). Read and output:\nBARCODE: <all digits under the barcode stripes>\nBRAND: <brand name>\nPRODUCT_NAME: <product name>\nNET_WEIGHT: <net weight>\nVARIANT: <variant or flavor>"
        
        vision_info = {}
        for attempt in range(2):
            try:
                time.sleep(1.5)
                res = client.models.generate_content(
                    model="gemini-flash-lite-latest",
                    contents=[
                        types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                        prompt
                    ]
                )
                text = res.text.strip()
                for line in text.splitlines():
                    if line.startswith("BARCODE:"):
                        digits = "".join(filter(str.isdigit, line.replace("BARCODE:", "")))
                        if digits and (validate_ean_upc_checksum(digits) or len(digits) in (8, 12, 13)):
                            vision_info["vision_barcode"] = digits
                    elif line.startswith("BRAND:"):
                        vision_info["brand"] = line.replace("BRAND:", "").strip()
                    elif line.startswith("PRODUCT_NAME:"):
                        vision_info["product_name"] = line.replace("PRODUCT_NAME:", "").strip()
                    elif line.startswith("NET_WEIGHT:"):
                        vision_info["net_weight"] = line.replace("NET_WEIGHT:", "").strip()
                    elif line.startswith("VARIANT:"):
                        vision_info["variant"] = line.replace("VARIANT:", "").strip()
                break
            except Exception as e:
                time.sleep(3)
        
        final_bc = bc or vision_info.get("vision_barcode", "")
        # POS Match
        pos_match = None
        for item in pos_data:
            if final_bc and item["barcode"] and (final_bc == item["barcode"] or final_bc in item["barcode"]):
                pos_match = item
                break
        
        results[fname] = {
            "barcode": final_bc,
            "brand": vision_info.get("brand", ""),
            "product_name": vision_info.get("product_name", ""),
            "net_weight": vision_info.get("net_weight", ""),
            "variant": vision_info.get("variant", ""),
            "pos_sku": pos_match["sku"] if pos_match else "",
            "pos_product_name": pos_match["name"] if pos_match else "",
            "status": "CONFIRMED" if final_bc else "MANUAL_CHECK"
        }
        print(f"[{fname}] -> BC: {final_bc} | Brand: {vision_info.get('brand')} | Name: {vision_info.get('product_name')} | Weight: {vision_info.get('net_weight')} | POS: {results[fname]['pos_sku']}")

    with open("output/g1_delivery/manual_all_tail_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("Done analysis of all remaining targets!")

if __name__ == '__main__':
    main()
