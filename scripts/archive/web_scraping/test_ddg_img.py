import re
import requests
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
    'Referer': 'https://duckduckgo.com/'
}

def search_ddg_images(query):
    print(f"Searching DuckDuckGo Images for: {query}")
    r1 = requests.get(f'https://duckduckgo.com/?q={query}', headers=headers, timeout=6)
    vqd_match = re.search(r'vqd=([0-9-]+)', r1.text) or re.search(r'vqd="([0-9-]+)"', r1.text)
    if not vqd_match:
        print("Could not extract VQD token.")
        return []
    
    token = vqd_match.group(1)
    img_url = f'https://duckduckgo.com/i.js?l=us-en&o=json&q={query}&vqd={token}&f=,,,&p=1'
    r2 = requests.get(img_url, headers=headers, timeout=6)
    if r2.status_code == 200:
        data = r2.json()
        results = data.get('results', [])
        print(f"Found {len(results)} images!")
        for res in results[:3]:
            print(f"  Title: {res.get('title')}")
            print(f"  Image URL: {res.get('image')}")
        return results
    else:
        print(f"Error status {r2.status_code}")
        return []

if __name__ == "__main__":
    search_ddg_images("4901313938669")
    search_ddg_images("8850157516457")
