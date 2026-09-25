import sys, os, time
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
    'IMG_0242.jpeg', 'IMG_0275.jpeg', 'IMG_0279.jpeg', 'IMG_0308.jpeg',
    'IMG_0320.jpeg', 'IMG_0330.jpeg', 'IMG_0334.jpeg', 'IMG_0335.jpeg',
    'IMG_0336.jpeg', 'IMG_0353.jpeg', 'IMG_0368.jpeg'
]

def main():
    client = genai.Client(api_key=KEYS[1], http_options={"timeout": 60000})
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
            im_t.convert("RGB").save(buf, format="JPEG", quality=90)
            img_bytes = buf.getvalue()

        prompt = "Look at this packaging image (both sides). Read and output:\nBARCODE: <all digits under the barcode>\nBRAND: <brand name>\nPRODUCT_NAME: <product name>\nNET_WEIGHT: <net weight>\nVARIANT: <variant or flavor>"
        try:
            time.sleep(2)
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
