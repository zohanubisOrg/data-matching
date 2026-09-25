import json, os, sys
from PIL import Image

sys.stdout.reconfigure(encoding='utf-8')

def main():
    with open('output/g1_delivery/G1_products.json', encoding='utf-8') as f:
        products = json.load(f)

    print("Checking remaining landscape items where EXIF not in (6, 8):")
    for p in products:
        orig = p.get('original_image')
        crop_rel = p.get('website_front_image')
        if not orig or not crop_rel:
            continue
        crop_path = os.path.join('output/g1_delivery', crop_rel)
        orig_path = os.path.join('G1_original', orig)
        if not os.path.exists(crop_path) or not os.path.exists(orig_path):
            continue
        with Image.open(crop_path) as c_im, Image.open(orig_path) as o_im:
            if c_im.width > c_im.height:
                orient = o_im.getexif().get(274, 1)
                if orient not in (6, 8):
                    name = p.get('product_name') or p.get('pos_product_name') or 'Unknown'
                    print(f"{orig}: EXIF={orient}, crop={c_im.size}, barcode={p.get('barcode')}, name={name}")

if __name__ == '__main__':
    main()
