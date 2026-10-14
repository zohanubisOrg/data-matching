import re
from bs4 import BeautifulSoup

with open('scripts/sample_google_img.html', 'r', encoding='utf-8') as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')
imgs = soup.find_all('img')
print(f"Total img tags: {len(imgs)}")
for i, img in enumerate(imgs[:10]):
    src = img.get('src') or img.get('data-src') or ''
    alt = img.get('alt') or ''
    print(f"Img {i}: alt={alt[:30]} | src={src[:80]}")

scripts = soup.find_all('script')
print(f"Total scripts: {len(scripts)}")
for idx, s in enumerate(scripts):
    text = s.get_text()
    if 'Kameda' in text or '4901313938669' in text or 'Starry' in text:
        print(f"Script {idx}: contains match! Length: {len(text)}")
        urls = re.findall(r'https?://[^\s"\'<>\\]+', text)
        print(f"  URLs found: {len(urls)}")
        for u in urls[:10]:
            print("   ", u)
