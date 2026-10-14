import json, sys, os, re
from pathlib import Path
from PIL import Image, ImageOps
from google import genai
from google.genai import types
from io import BytesIO
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

KEYS = [
    "AIzaSyCl8NJtBaFVjGfSSL2n5mFiCVysQWrn-UI",
    "AQ.Ab8RN6LDdgf38KYpVPhlWa3M1wrjxF758sKy04_8xSmWntDV5A"
]

TARGETS = [
    'IMG_0230.jpeg', 'IMG_0231.jpeg', 'IMG_0242.jpeg', 'IMG_0260.jpeg',
    'IMG_0273.jpeg', 'IMG_0275.jpeg', 'IMG_0278.jpeg', 'IMG_0279.jpeg',
    'IMG_0289.jpeg', 'IMG_0299.jpeg', 'IMG_0304.jpeg', 'IMG_0308.jpeg',
    'IMG_0319.jpeg', 'IMG_0320.jpeg', 'IMG_0325.jpeg', 'IMG_0330.jpeg',
    'IMG_0334.jpeg', 'IMG_0335.jpeg', 'IMG_0336.jpeg', 'IMG_0353.jpeg',
    'IMG_0368.jpeg'
]

def clean_json_str(text: str) -> str:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def analyze_item(fname: str, client: genai.Client):
    path = os.path.join("G1_original", fname)
    if not os.path.exists(path):
        return {"error": "file not found"}
    
    with Image.open(path) as im:
        im_t = ImageOps.exif_transpose(im)
        max_dim = 1600
        w, h = im_t.size
        if max(w, h) > max_dim:
            scale = max_dim / max(w, h)
            im_t = im_t.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
        
        buf = BytesIO()
        im_t.convert("RGB").save(buf, format="JPEG", quality=92)
        img_bytes = buf.getvalue()

    prompt = """Analyze this product packaging photo showing both sides of a packaged product.
Identify all details carefully:
- barcode: The full numeric barcode (look closely at the back or side panel).
- brand: The brand name (e.g. Lobo, Cock Brand, Ngọc Liên, Lee Kum Kee, Pearl River Bridge, etc.)
- product_name: The packaging product title / description
- net_weight: Weight or volume (e.g. 100g, 365g, 500ml)
- variant: Flavor / variant if any

Respond in strict JSON format:
{
  "barcode": "string or digits",
  "brand": "string",
  "product_name": "string",
  "net_weight": "string",
  "variant": "string"
}"""

    response = client.models.generate_content(
        model="gemini-flash-lite-latest",
        contents=[
            types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
            prompt
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0
        )
    )
    raw = clean_json_str(response.text or "{}")
    try:
        return json.loads(raw)
    except Exception:
        return {"raw": raw}

def main():
    client = genai.Client(api_key=KEYS[0], http_options={"timeout": 60000})
    
    # Load POS for cross matching
    pos_data = []
    if os.path.exists("docs/G1_pos.csv"):
        df = pd.read_csv("docs/G1_pos.csv")
        for _, row in df.iterrows():
            pos_data.append({
                "sku": str(row.get("Item Number", "")).strip(),
                "name": str(row.get("Item Description", "")).strip(),
                "barcode": str(row.get("Barcode", "")).strip()
            })

    results = {}
    for fname in TARGETS:
        res = analyze_item(fname, client)
        bc = str(res.get("barcode", "")).strip()
        
        # Match POS
        pos_match = None
        for item in pos_data:
            if bc and item["barcode"] and (bc == item["barcode"] or bc in item["barcode"]):
                pos_match = item
                break
        
        res["matched_pos"] = pos_match
        results[fname] = res
        print(f"[{fname}] -> Barcode: {bc} | Brand: {res.get('brand')} | Name: {res.get('product_name')} | Weight: {res.get('net_weight')} | POS: {pos_match.get('sku') if pos_match else 'None'}")

    with open("output/g1_delivery/manual_review_resolved.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    main()
