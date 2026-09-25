import json, sys, os
from pathlib import Path
from PIL import Image, ImageOps
from google import genai
from google.genai import types
from io import BytesIO

sys.stdout.reconfigure(encoding='utf-8')

KEYS = [
    "AIzaSyCl8NJtBaFVjGfSSL2n5mFiCVysQWrn-UI",
    "AQ.Ab8RN6LDdgf38KYpVPhlWa3M1wrjxF758sKy04_8xSmWntDV5A"
]

TARGETS = [
    'IMG_0242.jpeg', 'IMG_0273.jpeg', 'IMG_0275.jpeg', 'IMG_0278.jpeg',
    'IMG_0279.jpeg', 'IMG_0299.jpeg', 'IMG_0304.jpeg', 'IMG_0308.jpeg',
    'IMG_0319.jpeg', 'IMG_0320.jpeg', 'IMG_0325.jpeg', 'IMG_0330.jpeg',
    'IMG_0334.jpeg', 'IMG_0335.jpeg', 'IMG_0336.jpeg', 'IMG_0353.jpeg',
    'IMG_0368.jpeg'
]

PROMPT = """Analyze this product packaging photo which contains two sides of a packaged product.
Identify:
1. Product barcode (all digits under the barcode stripes). Look carefully at both sides!
2. Brand name (e.g. Lobo, Cock Brand, Lee Kum Kee, Ngoc Lien, etc.)
3. Product official packaging name (in English / Vietnamese / original language)
4. Net weight / volume (e.g. 50g, 100g, 365g, 500ml)
5. Variant / flavor (e.g. Satay, Tom Yum, Pickled Eggplant, Hot, etc.)
6. front_box_2d: [ymin, xmin, ymax, xmax] (0-1000) bounding box for the front packaging view.
7. barcode_box_2d: [ymin, xmin, ymax, xmax] (0-1000) bounding box for the barcode region.

Return valid JSON with keys: barcode, brand, product_name, net_weight, variant, front_box_2d, barcode_box_2d."""

def analyze_upright(fname):
    path = os.path.join("G1_original", fname)
    if not os.path.exists(path):
        return None
    
    with Image.open(path) as im:
        im_t = ImageOps.exif_transpose(im)
        # Resize for Gemini
        max_dim = 1600
        w, h = im_t.size
        if max(w, h) > max_dim:
            scale = max_dim / max(w, h)
            im_t = im_t.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
        
        buf = BytesIO()
        im_t.convert("RGB").save(buf, format="JPEG", quality=90)
        img_bytes = buf.getvalue()

    client = genai.Client(api_key=KEYS[0], http_options={"timeout": 60000})
    try:
        response = client.models.generate_content(
            model="gemini-flash-lite-latest",
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                PROMPT
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Error {fname}: {e}")
        return None

def main():
    results = {}
    for fname in TARGETS:
        res = analyze_upright(fname)
        results[fname] = res
        print(f"{fname}: {res}")
    
    with open('output/g1_delivery/manual_review_21_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    main()
