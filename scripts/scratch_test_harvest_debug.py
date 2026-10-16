import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from product_mapper.harvest.openfoodfacts_client import OpenFoodFactsClient
from product_mapper.harvest.google_images_harvester import GoogleImagesHarvester

bc = '8850043126456'
off = OpenFoodFactsClient()
print('OFF url:', off.get_front_packshot_url(bc))

g = GoogleImagesHarvester(rate_limit_delay=(0.1, 0.5))
cands = g.search_candidates(f'"{bc}"', limit=5, use_cache=False)
print('Google cands for barcode:', len(cands))
for c in cands:
    print(' ', c.url, c.width, c.height)

# Also test DuckDuckGo image search or Serp if google images blocks anonymous requests
import requests
resp = requests.get(f'https://www.google.com/search?tbm=isch&q={bc}', headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'})
print('Google status code:', resp.status_code, 'len HTML:', len(resp.text))
if 'Our systems have detected unusual traffic' in resp.text:
    print('Google CAPTCHA detected!')
