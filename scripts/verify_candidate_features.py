import json
from pathlib import Path
from PIL import Image
import numpy as np

ROOT = Path("D:/Work/shopify")
manifest_path = ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/subagent_batch_388_760/candidate_manifest.jsonl"
items = [json.loads(l) for l in manifest_path.read_text(encoding="utf-8").split("\n") if l.strip()]

for item in items:
    row = item["excel_row"]
    bc = item["barcode"]
    name = item["product_name_en"]
    out_p = Path(item["output_path"])
    
    img = Image.open(out_p).convert("RGB")
    arr = np.asarray(img)
    non_white = np.where(np.any(arr < 250, axis=2))
    ymin, ymax = int(non_white[0].min()), int(non_white[0].max())
    xmin, xmax = int(non_white[1].min()), int(non_white[1].max())

    # Cut top 20% and bottom 20% of product
    h = ymax - ymin
    top_slice = arr[ymin:ymin+int(h*0.2), xmin:xmax]
    bot_slice = arr[ymax-int(h*0.2):ymax, xmin:xmax]

    print(f"Row {row} ({bc}) - {name}:")
    print(f"  Canvas placement: [{xmin}, {ymin}, {xmax}, {ymax}] dims {xmax-xmin}x{h}")
    print(f"  Top 20% mean RGB: {top_slice.mean(axis=(0,1)).round(1)}")
    print(f"  Bot 20% mean RGB: {bot_slice.mean(axis=(0,1)).round(1)}")
    
    # Save top slice and bot slice for verification
    top_img = Image.fromarray(top_slice)
    bot_img = Image.fromarray(bot_slice)
    eval_dir = ROOT / "output/catalog_pairs/qa_inspector/visual_eval_batch2"
    top_img.save(eval_dir / f"row_{row}_top.jpg")
    bot_img.save(eval_dir / f"row_{row}_bot.jpg")
    print(f"  Saved top/bot slices to {eval_dir.name}\n")
