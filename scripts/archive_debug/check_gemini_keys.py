import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
raw_keys = os.environ.get('GEMINI_API_KEYS', '') or os.environ.get('GEMINI_API_KEY', '') or os.environ.get('GOOGLE_API_KEY', '')
keys = [k.strip() for k in raw_keys.split(',') if k.strip()]
for k, v in os.environ.items():
    if (k.startswith('GEMINI_API_KEY_') or k.startswith('GOOGLE_API_KEY_')) and v.strip() not in keys:
        keys.append(v.strip())

print(f'Total keys found: {len(keys)}')

test_models = ['gemini-3.5-flash-lite', 'gemini-3.1-flash-lite', 'gemini-3.5-flash', 'gemini-3.6-flash', 'gemini-3.7-flash', 'gemini-flash-latest']

working = []
for k in keys:
    client = genai.Client(api_key=k)
    for m in test_models:
        try:
            res = client.models.generate_content(model=m, contents='Say OK')
            print(f'Key {k[:8]}... | Model {m}: OK -> {res.text.strip()}')
            working.append((k, m))
            break
        except Exception as e:
            pass

print(f'Total working key-model combinations: {len(working)}')
