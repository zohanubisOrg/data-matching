import os, sys, json, io
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')

api_key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GEMINI_API_KEYS', '').split(',')[0].strip()
client = genai.Client(api_key=api_key)


def test_image(img_name: str):
    img_path = Path("G1_original") / img_name
    with Image.open(img_path) as orig_im:
        orig_im = ImageOps.exif_transpose(orig_im)
        w, h = orig_im.size

        # Stage 1: Layout & Box Detection
        buf_low = io.BytesIO()
        orig_im.resize((1200, int(1200 * h / w))).save(buf_low, format='JPEG', quality=85)

        prompt_layout = """
        Analyze this packaging photo showing FRONT and BACK sides of an imported grocery item.
        Return JSON with coordinates [ymin, xmin, ymax, xmax] (0-1000) and rotation needed (0, 90, 180, 270 degrees clockwise) to make text right-side up:
        {
          "front_box_2d": [ymin, xmin, ymax, xmax],
          "front_rotation_to_upright": 0,
          "back_box_2d": [ymin, xmin, ymax, xmax],
          "back_rotation_to_upright": 0,
          "barcode_box_2d": [ymin, xmin, ymax, xmax]
        }
        """

        res_layout = client.models.generate_content(
            model="gemini-flash-lite-latest",
            contents=[types.Part.from_bytes(data=buf_low.getvalue(), mime_type="image/jpeg"), prompt_layout],
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
        )
        layout = json.loads(res_layout.text)
        print(f"=== {img_name} Layout ===")
        print(json.dumps(layout, indent=2))

        # Stage 2: High-Resolution Front Inspection
        front_box = layout.get("front_box_2d")
        if front_box and len(front_box) == 4:
            ymin, xmin, ymax, xmax = front_box
            left, top = max(0, int(xmin * w / 1000)), max(0, int(ymin * h / 1000))
            right, bottom = min(w, int(xmax * w / 1000)), min(h, int(ymax * h / 1000))
            crop_front = orig_im.crop((left, top, right, bottom))
            rot_f = layout.get("front_rotation_to_upright", 0)
            if rot_f != 0:
                crop_front = crop_front.rotate(-rot_f, expand=True)

            buf_f = io.BytesIO()
            crop_front.save(buf_f, format="JPEG", quality=90)

            prompt_front = """
            Inspect this high-resolution FRONT packaging photo.
            Extract:
            {
              "brand": "string",
              "literal_label_name": "exact main product title as printed on packaging",
              "full_name_en": "Standardized commercial English title: Brand + Variant + Product Name + Net Weight",
              "fuldt_navn_da": "Commercial Danish translated title",
              "variant": "Flavor or variant",
              "category": "Snacks, Noodles, Sauces, Drinks, Condiments, etc.",
              "packaging": "Bag, Box, Bottle, Can, etc.",
              "net_quantity": number or null,
              "net_unit": "g, ml, kg, L, oz",
              "unit_count": number or null
            }
            """
            res_front = client.models.generate_content(
                model="gemini-flash-lite-latest",
                contents=[types.Part.from_bytes(data=buf_f.getvalue(), mime_type="image/jpeg"), prompt_front],
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
            )
            print(f"--- Front Details ---")
            print(res_front.text)

        # Stage 3: High-Resolution Back Inspection (Nutrition, Ingredients, Allergens, Importer)
        back_box = layout.get("back_box_2d")
        if back_box and len(back_box) == 4:
            ymin, xmin, ymax, xmax = back_box
            left, top = max(0, int(xmin * w / 1000)), max(0, int(ymin * h / 1000))
            right, bottom = min(w, int(xmax * w / 1000)), min(h, int(ymax * h / 1000))
            crop_back = orig_im.crop((left, top, right, bottom))
            rot_b = layout.get("back_rotation_to_upright", 0)
            if rot_b != 0:
                crop_back = crop_back.rotate(-rot_b, expand=True)

            buf_b = io.BytesIO()
            crop_back.save(buf_b, format="JPEG", quality=92)

            prompt_back = """
            Inspect this high-resolution BACK packaging / Nutrition & Ingredients label of an imported food item in the EU.
            Extract strictly visible facts in JSON:
            {
              "ingredients_label_language": "string",
              "ingredients_en": "Full English ingredients list",
              "ingredienser_da": "Full Danish translated ingredients list",
              "allergens_label": "Literal allergen text",
              "allergens_en": "EU allergens in English",
              "allergener_da": "EU allergens in Danish",
              "may_contain_label": "May contain traces statement",
              "nutrition_basis": "per 100 g or per 100 ml",
              "energy_kj": number or null,
              "energy_kcal": number or null,
              "fat_g": number or null,
              "saturates_g": number or null,
              "carbohydrate_g": number or null,
              "sugars_g": number or null,
              "fibre_g": number or null,
              "protein_g": number or null,
              "salt_g": number or null,
              "other_nutrition_source": "string",
              "country_of_origin": "Country name (e.g. Thailand, Japan, Vietnam)",
              "origin_label_evidence": "Literal origin statement on package",
              "manufacturer": "Manufacturer name",
              "manufacturer_address": "Manufacturer address",
              "importer": "Importer company name (e.g. Asia Express Food, Beagley Copperman, etc.)",
              "importer_address": "Importer address",
              "distributor": "Distributor",
              "storage_en": "Storage instructions in English",
              "opbevaring_da": "Storage instructions in Danish",
              "preparation_en": "Preparation instructions in English",
              "tilberedning_da": "Preparation instructions in Danish",
              "warnings_label": "Warning statement",
              "claims_certifications": "Halal, Vegan, Non-GMO, etc.",
              "alcohol_vol": number or null,
              "manufacture_date": "MFG date",
              "best_before_expiry": "BBE / Expiry date",
              "lot_batch": "Lot / batch number"
            }
            """
            res_back = client.models.generate_content(
                model="gemini-flash-lite-latest",
                contents=[types.Part.from_bytes(data=buf_b.getvalue(), mime_type="image/jpeg"), prompt_back],
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
            )
            print(f"--- Back & Nutrition Details ---")
            print(res_back.text)


if __name__ == "__main__":
    test_image("IMG_0002.jpeg")
