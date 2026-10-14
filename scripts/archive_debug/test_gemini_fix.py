import os
import io
import json
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image

load_dotenv()
api_key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
client = genai.Client(api_key=api_key)

tofu_im = Image.open('source-import/Nyt25.09.26/Tofu.jpg')
buf = io.BytesIO()
tofu_im.resize((1000, int(1000 * tofu_im.height / tofu_im.width))).save(buf, format='JPEG', quality=85)

prompt = "Locate the primary retail packaging object in this image. Return strictly JSON: {\"front_box_2d\": [ymin, xmin, ymax, xmax], \"front_rotation\": 0, \"brand_and_name\": \"string\"}. Note: coordinates 0-1000 MUST include the ENTIRE retail product from top to bottom (do not truncate)."

resp = client.models.generate_content(
    model='models/gemini-3.8-flash',
    contents=[
        types.Part.from_bytes(data=buf.getvalue(), mime_type='image/jpeg'),
        prompt
    ],
    config=types.GenerateContentConfig(response_mime_type='application/json')
)
print("Response:", resp.text)
