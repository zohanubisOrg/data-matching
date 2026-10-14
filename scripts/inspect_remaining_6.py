import sys
from pathlib import Path
from PIL import Image
import zxingcpp

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from audit_front_v2 import audit_single_image

items = [
    ("4045198900905", "source-import/G3_Original/IMG_1496.jpeg"),
    ("8714573005240", "source-import/G2_original/IMG_0905.jpeg"),
    ("5060284550153", "source-import/G3_Original/IMG_1464.jpeg"),
    ("8005734101568", "source-import/G3_Original/IMG_1301.jpeg"),
    ("8716789011244", "source-import/G3_Original/IMG_5077.HEIC"),
    ("8804009000083", "source-import/G1_original/IMG_9931.jpeg"),
]

for bc, rel in items:
    p = ROOT / rel
    im = Image.open(p)
    w, h = im.size
    print(f"=== {bc} ({rel}) size={w}x{h} ===", flush=True)
    hits = zxingcpp.read_barcodes(im)
    for h_obj in hits:
        print(f"  Source barcode: {h_obj.text} pos: {h_obj.position.top_left.x}, {h_obj.position.top_left.y}", flush=True)
    front_p = ROOT / f"output/catalog_pairs/tagged/front-v2/{bc}-front.jpg"
    if front_p.exists():
        f_im = Image.open(front_p)
        f_hits = zxingcpp.read_barcodes(f_im)
        print(f"  Front-v2 size: {f_im.size}, hits on front: {[x.text for x in f_hits]}", flush=True)
        aud = audit_single_image(str(front_p))
        print(f"  Audit: {aud['severity']}, reasons: {aud['reasons']}, AR: {aud.get('aspect_ratio')}, cov: {aud.get('coverage')}", flush=True)
