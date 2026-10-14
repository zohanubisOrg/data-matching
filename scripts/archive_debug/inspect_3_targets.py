import sys, os, json
from PIL import Image, ImageOps
from google import genai
from google.genai import types
from io import BytesIO

sys.stdout.reconfigure(encoding='utf-8')

KEY = "AIzaSyCl8NJtBaFVjGfSSL2n5mFiCVysQWrn-UI"

TARGETS = ['IMG_0399.jpeg', 'IMG_9935.jpeg', 'IMG_9938.jpeg']

def main():
    client = genai.Client(api_key=KEY, http_options={"timeout": 60000})
    for fname in TARGETS:
        path = os.path.join("G1_original", fname)
        if not os.path.exists(path):
            continue
        with Image.open(path) as im:
            im_t = ImageOps.exif_transpose(im)
            w, h = im_t.size
            if max(w, h) > 1600:
                scale = 1600 / max(w, h)
                im_t = im_t.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
            buf = BytesIO()
            im_t.convert("RGB").save(buf, format="JPEG", quality=92)
            img_bytes = buf.getvalue()

        prompt = """Inspect this packaging image showing both sides of a packaged product.
Read every piece of text on the packaging carefully and provide:
1. All digits under the barcode (look at back/bottom/sides)
2. Brand name
3. Full product packaging title (Vietnamese/English/original)
4. Net weight / volume
5. Flavor / variant

Format your answer as:
BARCODE: <digits>
BRAND: <brand>
PRODUCT_NAME: <name>
NET_WEIGHT: <weight>
VARIANT: <variant>"""

        try:
            res = client.models.generate_content(
                model="gemini-flash-lite-latest",
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                    prompt
                ]
            )
            print(f"=== {fname} ===")
            print(res.text.strip())
        except Exception as e:
            print(f"=== {fname} === ERROR: {e}")

if __name__ == '__main__':
    main()
