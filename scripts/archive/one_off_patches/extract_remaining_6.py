# -*- coding: utf-8 -*-
import sys
import os
import json
import time
from pathlib import Path
from google import genai
from google.genai import types

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = r"D:\Work\shopify"
IMG_DIR = os.path.join(BASE_DIR, "source-import", "G1_original")
OUT_CACHE = os.path.join(BASE_DIR, "output", "g1_delivery", "g1_47_missing_cache.json")

# Valid API key from .env (the first one)
api_key = None
env_file = os.path.join(BASE_DIR, ".env")
if os.path.exists(env_file):
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip().startswith("GEMINI_API_KEY") and "AIza" in line:
                api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                break

print(f"Using working API key: {api_key[:10]}...")

missing_photos = [
    "IMG_0355.jpeg", "IMG_0353.jpeg", "IMG_0378.jpeg", "IMG_0385.jpeg", "IMG_0405.jpeg", "IMG_0406.jpeg"
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
Output valid JSON only. Do not output a list, output a single JSON object."""

results = {}
if os.path.exists(OUT_CACHE):
    try:
        with open(OUT_CACHE, "r", encoding="utf-8") as f:
            results = json.load(f)
    except Exception:
        results = {}

client = genai.Client(api_key=api_key)

for p in missing_photos:
    img_path = os.path.join(IMG_DIR, p)
    if not os.path.exists(img_path):
        alt = [f for f in os.listdir(IMG_DIR) if f.lower() == p.lower()]
        if alt:
            img_path = os.path.join(IMG_DIR, alt[0])
            
    if not os.path.exists(img_path):
        print(f"File not found: {p}")
        continue
        
    print(f"Processing {p}...")
    with open(img_path, "rb") as f:
        img_bytes = f.read()
        
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                    PROMPT
                ],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            res_json = json.loads(response.text)
            if isinstance(res_json, list):
                res_json = res_json[0]
            results[p] = res_json
            print(f"  -> Extracted: {res_json.get('brand')} | {res_json.get('fuldt_navn_da')}")
            break
        except Exception as e:
            print(f"  -> Attempt {attempt+1} error on {p}: {e}")
            time.sleep(2)
        
    time.sleep(1)

with open(OUT_CACHE, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\nDone! Total in cache: {len(results)}")
