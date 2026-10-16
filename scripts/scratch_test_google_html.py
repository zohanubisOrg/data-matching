import re
import requests

bc = '8850043126456'
resp = requests.get(
    f'https://www.google.com/search?tbm=isch&q="{bc}"&hl=en',
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'}
)

print('Status:', resp.status_code, 'len:', len(resp.text))
urls = re.findall(r'https?://[^\s"\'<>]+?\.(?:jpg|jpeg|png|webp)', resp.text)
print('Total raw image URLs found:', len(urls))
for u in urls[:10]:
    print(' ', u)

# Also check without quotes:
resp2 = requests.get(
    f'https://www.google.com/search?tbm=isch&q={bc}&hl=en',
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'}
)
urls2 = re.findall(r'https?://[^\s"\'<>]+?\.(?:jpg|jpeg|png|webp)', resp2.text)
print('\nWithout quotes total image URLs:', len(urls2))
for u in urls2[:10]:
    print(' ', u)

# Also check DuckDuckGo image search
import json
ddg_resp = requests.get(f'https://duckduckgo.com/?q={bc}', headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
vqd_match = re.search(r'vqd=([\d-]+)', ddg_resp.text)
if vqd_match:
    vqd = vqd_match.group(1)
    ddg_img = requests.get(f'https://duckduckgo.com/i.js?q={bc}&vqd={vqd}&o=json', headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    print('\nDDG images status:', ddg_img.status_code)
    try:
        results = ddg_img.json().get('results', [])
        print('DDG images found:', len(results))
        for r in results[:3]:
            print('  [DDG]', r.get('image'), r.get('width'), r.get('height'))
    except Exception as e:
        print('DDG json error:', e)
