import json
from pathlib import Path
from PIL import Image
import numpy as np

ROOT = Path("D:/Work/shopify")

# Let's inspect the 5 candidates
items = [
    {
        "row": 850,
        "barcode": "4045198753174",
        "name": "Fried red onion 200 g",
        "source": ROOT / "output/catalog_pairs/originals/4045198753174/G2_original_IMG_0867.jpeg",
        "candidate": ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/render_native_scale_refined_850_886_894_v2/4045198753174__G2-0401__row0850-front.png",
        "mask": ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/render_native_scale_refined_850_886_894_v2/4045198753174__G2-0401__row0850-mask.png"
    },
    {
        "row": 886,
        "barcode": "7178600000140",
        "name": "Mild curry paste 270 g",
        "source": ROOT / "output/catalog_pairs/originals/7178600000140/G2_original_IMG_0911.jpeg",
        "candidate": ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/render_native_scale_refined_850_886_894_v2/7178600000140__G2-0437__row0886-front.png",
        "mask": ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/render_native_scale_refined_850_886_894_v2/7178600000140__G2-0437__row0886-mask.png"
    },
    {
        "row": 894,
        "barcode": "5017689097905",
        "name": "Boiled chickpeas in salted water 400 g",
        "source": ROOT / "output/catalog_pairs/originals/5017689097905/G2_original_IMG_0919.jpeg",
        "candidate": ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/render_native_scale_refined_850_886_894_v2/5017689097905__G2-0445__row0894-front.png",
        "mask": ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/render_native_scale_refined_850_886_894_v2/5017689097905__G2-0445__row0894-mask.png"
    },
    {
        "row": 926,
        "barcode": "6922163623848",
        "name": "Oolong Tea 50 g",
        "source": ROOT / "output/catalog_pairs/originals/6922163623848/G3_Original_IMG_1198.jpeg",
        "candidate": ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/render_native_scale_scan_926_970_v2/6922163623848__G3-0025__row0926-front.png",
        "mask": ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/render_native_scale_scan_926_970_v2/6922163623848__G3-0025__row0926-mask.png"
    },
    {
        "row": 970,
        "barcode": "8855790000028",
        "name": "Energy Drink 250 ml (Carabao)",
        "source": ROOT / "output/catalog_pairs/originals/8855790000028/G3_Original_IMG_1263.jpeg",
        "candidate": ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/render_native_scale_scan_926_970_v2/8855790000028__G3-0080__row0970-front.png",
        "mask": ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/render_native_scale_scan_926_970_v2/8855790000028__G3-0080__row0970-mask.png"
    }
]

# Let's create a combined thumbnail / contact sheet to inspect them side by side
thumb_size = (600, 600)
contact = Image.new("RGB", (600 * len(items), 600 * 2), (255, 255, 255))

for i, it in enumerate(items):
    src_img = Image.open(it["source"])
    src_thumb = src_img.copy()
    src_thumb.thumbnail(thumb_size)
    # paste centered in top slot
    x_offset = i * 600 + (600 - src_thumb.width) // 2
    y_offset = (600 - src_thumb.height) // 2
    contact.paste(src_thumb, (x_offset, y_offset))
    
    cand_img = Image.open(it["candidate"])
    cand_thumb = cand_img.copy()
    cand_thumb.thumbnail(thumb_size)
    cx_offset = i * 600 + (600 - cand_thumb.width) // 2
    cy_offset = 600 + (600 - cand_thumb.height) // 2
    contact.paste(cand_thumb, (cx_offset, cy_offset))

out_contact = ROOT / "output/catalog_pairs/review/qa_inspect_5_problematic.jpg"
contact.save(out_contact, quality=90)
print(f"Saved contact sheet to {out_contact}")
