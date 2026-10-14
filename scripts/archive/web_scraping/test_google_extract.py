import requests
import re

bc = '8850043126456'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'}
url = f'https://www.google.com/search?q={bc}&tbm=isch'
r = requests.get(url, headers=headers)
print("Response length:", len(r.text))

# Search for actual image links in Google Images JavaScript chunks
found = []
for m in re.finditer(r'(https?://[^\s"\'<>]+\.(?:jpg|jpeg|png|webp))', r.text):
    u = m.group(1)
    if 'gstatic.com' not in u and 'google.com' not in u and 'schema.org' not in u:
        found.append(u)

print(f"Direct image links found: {len(found)}")
for u in found[:5]:
    print("  ", u)
