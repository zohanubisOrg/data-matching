from PIL import Image
from pathlib import Path

ROOT = Path("D:/Work/shopify")
out_dir = ROOT / "output/catalog_pairs/qa_inspector/visual_eval_batch2"
out_dir.mkdir(parents=True, exist_ok=True)

manifest_path = ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/subagent_batch_388_760/candidate_manifest.jsonl"
import json
items = [json.loads(l) for l in manifest_path.read_text(encoding="utf-8").split("\n") if l.strip()]

thumbs = []
for item in items:
    row = item["excel_row"]
    bc = item["barcode"]
    out_p = Path(item["output_path"])
    overlay_p = Path(item["overlay_path"])

    with Image.open(out_p) as img:
        # Save a compressed preview
        preview_p = out_dir / f"row_{row}_{bc}_front_preview.jpg"
        img.convert("RGB").save(preview_p, quality=88)
        
        # Make a thumbnail for combined inspection
        t = img.copy()
        t.thumbnail((400, 400))
        # pad to 400x400 white
        thumb_bg = Image.new("RGB", (400, 400), (255, 255, 255))
        thumb_bg.paste(t, ((400 - t.width) // 2, (400 - t.height) // 2))
        thumbs.append((row, bc, thumb_bg))

# Create contact sheet 2x3
grid = Image.new("RGB", (400 * 3, 400 * 2), (255, 255, 255))
for idx, (row, bc, timg) in enumerate(thumbs):
    gx = (idx % 3) * 400
    gy = (idx // 3) * 400
    grid.paste(timg, (gx, gy))

grid_path = out_dir / "batch2_6_candidates_contact_grid.jpg"
grid.save(grid_path, quality=90)
print(f"Saved contact grid to {grid_path}")
