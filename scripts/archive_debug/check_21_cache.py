import json, sys
sys.stdout.reconfigure(encoding='utf-8')

def main():
    with open('output/g1_delivery/g1_vision_cache.json', encoding='utf-8') as f:
        cache = json.load(f)

    items = [
        'IMG_0230.jpeg', 'IMG_0231.jpeg', 'IMG_0242.jpeg', 'IMG_0260.jpeg',
        'IMG_0273.jpeg', 'IMG_0275.jpeg', 'IMG_0278.jpeg', 'IMG_0279.jpeg',
        'IMG_0289.jpeg', 'IMG_0299.jpeg', 'IMG_0304.jpeg', 'IMG_0308.jpeg',
        'IMG_0319.jpeg', 'IMG_0320.jpeg', 'IMG_0325.jpeg', 'IMG_0330.jpeg',
        'IMG_0334.jpeg', 'IMG_0335.jpeg', 'IMG_0336.jpeg', 'IMG_0353.jpeg',
        'IMG_0368.jpeg'
    ]

    for it in items:
        v = cache.get(it, {})
        print(f"{it}: barcode='{v.get('barcode')}', name='{v.get('product_name')}', brand='{v.get('brand')}', weight='{v.get('net_weight')}', variant='{v.get('variant')}'")

if __name__ == '__main__':
    main()
