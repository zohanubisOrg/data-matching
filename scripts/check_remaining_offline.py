import sys, os
from PIL import Image, ImageOps, ImageEnhance
import zxingcpp

sys.stdout.reconfigure(encoding='utf-8')

REMAINING = [
    'IMG_0242.jpeg', 'IMG_0308.jpeg', 'IMG_0319.jpeg', 'IMG_0320.jpeg',
    'IMG_0325.jpeg', 'IMG_0330.jpeg', 'IMG_0334.jpeg', 'IMG_0335.jpeg',
    'IMG_0336.jpeg', 'IMG_0353.jpeg', 'IMG_0368.jpeg'
]

def check():
    for fname in REMAINING:
        path = os.path.join("G1_original", fname)
        if not os.path.exists(path):
            continue
        with Image.open(path) as im:
            im_t = ImageOps.exif_transpose(im)
            w, h = im_t.size
            found = set()
            for rot in [0, 90, 180, 270]:
                r_im = im_t.rotate(rot, expand=True)
                for r in zxingcpp.read_barcodes(r_im):
                    if str(r.text).isdigit():
                        found.add(str(r.text))
                # Enhance
                enh = ImageEnhance.Contrast(r_im).enhance(2.0)
                for r in zxingcpp.read_barcodes(enh):
                    if str(r.text).isdigit():
                        found.add(str(r.text))
            
            print(f"{fname}: size={im_t.size}, barcodes={list(found)}")

if __name__ == '__main__':
    check()
