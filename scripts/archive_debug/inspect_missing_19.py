import json, sys

sys.stdout.reconfigure(encoding='utf-8')

files_to_check = [
    'IMG_0362.jpeg', 'IMG_0365.jpeg', 'IMG_0373.jpeg', 'IMG_0378.jpeg',
    'IMG_0391.jpeg', 'IMG_0397.jpeg', 'IMG_0399.jpeg', 'IMG_0402.jpeg',
    'IMG_0404.jpeg', 'IMG_0405.jpeg', 'IMG_0406.jpeg', 'IMG_0407.jpeg',
    'IMG_0412.jpeg', 'IMG_0415.jpeg', 'IMG_0416.jpeg', 'IMG_9921.jpeg',
    'IMG_9924.jpeg', 'IMG_9930.jpeg', 'IMG_9935.jpeg'
]

with open('output/g1_delivery/G1_products.json', 'r', encoding='utf-8') as f:
    products = json.load(f)

p_dict = {p.get('original_image'): p for p in products}

results = {}
for f in files_to_check:
    item = p_dict.get(f, {})
    results[f] = {
        "barcode": item.get('barcode', ''),
        "brand": item.get('brand', ''),
        "product_name": item.get('product_name', ''),
        "net_weight": item.get('net_weight', ''),
        "variant": item.get('variant', ''),
    }

print(json.dumps(results, ensure_ascii=False, indent=2))
