# -*- coding: utf-8 -*-
import sys
import os
import json
import base64
import time
from pathlib import Path
from google import genai
from google.genai import types

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = r"D:\Work\shopify"
IMG_DIR = os.path.join(BASE_DIR, "source-import", "G1_original")
OUT_CACHE = os.path.join(BASE_DIR, "output", "g1_delivery", "g1_47_missing_cache.json")

# Load API keys from .env
api_keys = []
env_file = os.path.join(BASE_DIR, ".env")
if os.path.exists(env_file):
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip().startswith("GEMINI_API_KEY"):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    api_keys.append(val)

print(f"Loaded {len(api_keys)} Gemini API keys.")

missing_photos = [
    "IMG_0325.jpeg", "IMG_0330.jpeg", "IMG_0331.jpeg", "IMG_0334.jpeg", "IMG_0333.jpeg",
    "IMG_0336.jpeg", "IMG_0344.jpeg", "IMG_0349.jpeg", "IMG_0352.jpeg", "IMG_0350.jpeg",
    "IMG_0351.jpeg", "IMG_0354.jpeg", "IMG_0355.jpeg", "IMG_0353.jpeg", "IMG_0356.jpeg",
    "IMG_0357.jpeg", "IMG_0358.jpeg", "IMG_0362.jpeg", "IMG_0365.jpeg", "IMG_0373.jpeg",
    "IMG_0378.jpeg", "IMG_0385.jpeg", "IMG_0391.jpeg", "IMG_0397.jpeg", "IMG_0399.jpeg",
    "IMG_0402.jpeg", "IMG_0405.jpeg", "IMG_0406.jpeg", "IMG_0404.jpeg", "IMG_0407.jpeg",
    "IMG_0412.jpeg", "IMG_0415.jpeg", "IMG_0416.jpeg", "IMG_9924.jpeg", "IMG_9921.jpeg",
    "IMG_9931.jpeg", "IMG_9930.jpeg", "IMG_9936.jpeg", "IMG_9935.jpeg", "IMG_9961.jpeg",
    "IMG_9960.jpeg", "IMG_9976.jpeg", "IMG_9973.jpeg", "IMG_9978.jpeg", "IMG_9986.jpeg",
    "IMG_9994.jpeg", "IMG_9998.jpeg"
]

PROMPT = """You are an expert e-commerce catalog specialist for an Asian supermarket in Denmark.
Analyze this product package image and extract structured data in JSON format:
{
  "brand": "Brand name visible on package (e.g. Mae Ploy, Aroy-D, Lee Kum Kee, Nongshim)",
  "literal_label_name": "Exact text printed on the front package",
  "full_name_en": "Natural English e-commerce product name (e.g. Mae Ploy Green Curry Paste 400g)",
  "fuldt_navn_da": "Natural Danish e-commerce product name (e.g. Mae Ploy grøn karrypasta 400 g)",
  "barcode": "Digits of barcode if visible anywhere in this photo, otherwise null",
  "variant": "Flavor or variant (e.g. Green Curry, Spicy, Original)",
  "category": "One of: Snack, Saucer, Drikkevarer, Nudler, Krydderier, Konserves, Mel, Bønner, Ris, Grøntsager, Frugt, Mælk, Frostvarer, Fisk, Rejer, Diverse",
  "packaging": "Bag / Box / Bottle / Jar / Can / Pouch / Tray",
  "net_quantity": "numeric value e.g. 400, 500, 1.5 or null",
  "net_unit": "g / ml / kg / l / oz",
  "country_of_origin": "Country of origin e.g. Thailand, Vietnam, Kina, Japan, Sydkorea",
  "ingredienser_da": "Ingredients in Danish if visible or translated, else empty string",
  "ingredients_en": "Ingredients in English if visible or translated, else empty string",
  "allergener_da": "Allergens in Danish if applicable",
  "energy_kcal": "numeric kcal per 100g if visible, else null",
  "fat_g": "numeric fat grams per 100g if visible, else null",
  "carbohydrate_g": "numeric carbohydrate grams per 100g if visible, else null",
  "protein_g": "numeric protein grams per 100g if visible, else null",
  "salt_g": "numeric salt grams per 100g if visible, else null"
}
Output valid JSON only."""

results = {}
if os.path.exists(OUT_CACHE):
    try:
        with open(OUT_CACHE, "r", encoding="utf-8") as f:
            results = json.load(f)
    except Exception:
        results = {}

print(f"Already processed: {len(results)} / {len(missing_photos)}")

key_idx = 0
for p in missing_photos:
    if p in results and results[p].get("fuldt_navn_da"):
        continue
    img_path = os.path.join(IMG_DIR, p)
    if not os.path.exists(img_path):
        # try lowercase or jpg
        alt = [f for f in os.listdir(IMG_DIR) if f.lower() == p.lower()]
        if alt:
            img_path = os.path.join(IMG_DIR, alt[0])
            
    if not os.path.exists(img_path):
        print(f"File not found: {p}")
        continue
        
    print(f"Processing {p}...")
    api_key = api_keys[key_idx % len(api_keys)]
    client = genai.Client(api_key=api_key)
    
    with open(img_path, "rb") as f:
        img_bytes = f.read()
        
    try:
        mime = "image/jpeg"
        if img_path.lower().endswith(".png"):
            mime = "image/png"
        elif img_path.lower().endswith(".heic"):
            # if heic, we can read preprocessed image
            prep_path = os.path.join(BASE_DIR, "output", "shopify_import_final", "product_images", f"{Path(p).stem}.jpg")
            if os.path.exists(prep_path):
                with open(prep_path, "rb") as f2:
                    img_bytes = f2.read()
                mime = "image/jpeg"
                
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type=mime),
                PROMPT
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        res_json = json.loads(response.text)
        results[p] = res_json
        print(f"  -> Extracted: {res_json.get('brand')} | {res_json.get('fuldt_navn_da')}")
    except Exception as e:
        print(f"  -> Error on {p}: {e}")
        key_idx += 1
        
    time.sleep(0.5)

with open(OUT_CACHE, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\nDone! Total in cache: {len(results)}")
