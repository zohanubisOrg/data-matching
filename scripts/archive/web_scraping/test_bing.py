import requests
import re

def search_bing(query):
    url = f"https://www.bing.com/images/search?q={query}&form=HDRSC2&first=1"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36'
    }
    r = requests.get(url, headers=headers, timeout=10)
    print(f"Bing status for {query}: {r.status_code}")
    
    # In Bing, full-res image URLs are inside murl in the json metadata of each thumbnail
    murls = re.findall(r'murl&quot;:&quot;(http[^&]+)&quot;', r.text)
    if not murls:
        murls = re.findall(r'"murl":"(http[^"]+)"', r.text)
    print(f"  Found {len(murls)} images!")
    for m in murls[:3]:
        print("   ", m)
    return murls

if __name__ == "__main__":
    search_bing("4901313938669")
    search_bing("8850157516457")
    search_bing("8850043330273")
