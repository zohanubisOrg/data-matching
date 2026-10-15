#!/usr/bin/env python3
"""
scripts/subagent_batch_761_1100_runner.py
----------------------------------------
Subagent pipeline for Batch 3 (rows 761 to 1100).
Renders candidate packshots into review/subagent_batch_761_1100/
and exports candidate manifest for independent cross-QA.
"""

import sys
import json
import hashlib
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw
import numpy as np

# Ensure utf-8 stdout
sys.stdout.reconfigure(encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from product_mapper.vision.package_packshot import mask_from_polygon, render_verified_packshot

OUT_DIR = ROOT / 'output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/subagent_batch_761_1100'
OUT_DIR.mkdir(parents=True, exist_ok=True)

def contract_polygon(poly, factor=0.985):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    return [[round(cx + (x - cx) * factor), round(cy + (y - cy) * factor)] for x, y in poly]

# Load extracted base candidate metadata
with open(ROOT / 'scripts/batch3_extracted_data.json', encoding='utf-8') as f:
    RAW_CANDIDATES = json.load(f)

# Candidate definitions
CANDIDATE_CONFIGS = [
    {
        'excel_row': 767,
        'barcode': '6970902470048',
        'record_id': 'G2-0313',
        'product_name_en': 'Sichuan Hot Pot Noodles 266 g',
        'source_path': 'output/catalog_pairs/originals/6970902470048/G2_original_IMG_0764.jpeg',
        'rotation_ccw': 0,
        'fit_to_native': False,
        'shape': 'auto',
        'apply_contract': True,
        'contract_factor': 0.985,
        'evidence': 'Direct full-resolution source inspection of G2_original_IMG_0764.jpeg: the front-facing packaging is an isolated complete sales unit with Sichuan Hot Pot Noodles brand identity and 266 g net weight clearly visible. Adjacent reverse-side companion pouch is strictly excluded. Perimeter contracted 1.5% inward to eliminate background tabletop reflection/bleed while fully preserving package artwork.',
        'review_limitations': [
            'Mild authentic studio perspective preserved.',
            'Companion reverse-side unit excluded.'
        ]
    },
    {
        'excel_row': 768,
        'barcode': '6970902471885',
        'record_id': 'G2-0314',
        'product_name_en': 'Potato Noodles with Sesame Paste 290 g',
        'source_path': 'output/catalog_pairs/originals/6970902471885/G2_original_IMG_0765.jpeg',
        'rotation_ccw': 0,
        'fit_to_native': False,
        'shape': 'auto',
        'apply_contract': True,
        'contract_factor': 0.985,
        'evidence': 'Direct full-resolution source inspection of G2_original_IMG_0765.jpeg: isolated complete sales unit with front Sesame Paste Potato Noodles branding and 290 g net weight. Companion reverse pouch excluded. 1.5% inward contraction ensures zero perimeter fringe.',
        'review_limitations': [
            'Glossy packaging specular reflections retained without synthetic inpainting.',
            'Companion unit excluded.'
        ]
    },
    {
        'excel_row': 769,
        'barcode': '6970902470185',
        'record_id': 'G2-0315',
        'product_name_en': 'Sichuan Noodles with Sour and Spicy Soup 276 g',
        'source_path': 'output/catalog_pairs/originals/6970902470185/G2_original_IMG_0766.jpeg',
        'rotation_ccw': 0,
        'fit_to_native': False,
        'shape': 'auto',
        'apply_contract': True,
        'contract_factor': 0.985,
        'evidence': 'Direct full-resolution source inspection of G2_original_IMG_0766.jpeg: single isolated front-facing sales unit of Sichuan Noodles Sour and Spicy Soup 276 g. The right-hand pouch is cleanly traced, fully excluding the companion reverse unit on the left. Contracted 1.5% inward for crisp edges.',
        'review_limitations': [
            'Studio lighting reflection preserved as authentic.',
            'Companion unit excluded.'
        ]
    },
    {
        'excel_row': 789,
        'barcode': '8936007822418',
        'record_id': 'G2-0335',
        'product_name_en': 'Bun Bo Hue fresh rice vermicelli 400 g',
        'source_path': 'output/catalog_pairs/originals/8936007822418/G2_original_IMG_0787.jpeg',
        'rotation_ccw': 0,
        'fit_to_native': False,
        'shape': 'auto',
        'apply_contract': True,
        'contract_factor': 0.985,
        'evidence': 'Direct EXIF-oriented full source inspection of G2_original_IMG_0787.jpeg: lower sales unit is BAMBOO TREE BUN BO HUE fresh rice vermicelli 400 g. Complete clear bag and sealed ends isolated with 39-point boundary contracted 1.5% to lift off tabletop and eliminate halo. Upper companion reverse unit excluded.',
        'review_limitations': [
            'Clear film reflections authentic to source.',
            'Upper reverse-facing unit excluded.'
        ]
    },
    {
        'excel_row': 1049,
        'barcode': '3661945882952',
        'record_id': 'G3-0163',
        'product_name_en': 'Plant-Based Corndogs 400 g (5 x 80 g)',
        'source_path': 'output/catalog_pairs/originals/3661945882952/G3_Original_IMG_1391.jpeg',
        'rotation_ccw': 0,
        'fit_to_native': False,
        'shape': 'square',
        'apply_contract': False,
        'evidence': 'Visually verified native source G3_Original_IMG_1391.jpeg: the right-hand pouch displays Korean Food Style CORNDOG plant-based sausage illustration and 400 g (5 x 80 g); adjacent left unit is companion reverse. Refined 32-point polygon from row1049_candidate_tight2 cleanly encloses pouch without tabletop background bleed.',
        'review_limitations': [
            'Pouch wrinkles and authentic surface reflections retained without retouching.',
            'Companion reverse pouch excluded.'
        ]
    }
]

def run():
    annotations = []
    manifest_items = []
    results_records = []

    print(f"Rendering {len(CANDIDATE_CONFIGS)} candidates for Batch 3 (rows 761 to 1100)...\n")

    for cfg in CANDIDATE_CONFIGS:
        row = cfg['excel_row']
        bc = cfg['barcode']
        rid = cfg['record_id']
        stem = f'{bc}__{rid}__row{row:04d}'
        sp = ROOT / cfg['source_path']

        raw = RAW_CANDIDATES[str(row)]
        poly = raw['polygon']
        if cfg['apply_contract']:
            poly = contract_polygon(poly, cfg.get('contract_factor', 0.985))

        with Image.open(sp) as im:
            image = ImageOps.exif_transpose(im).convert('RGB')

        src_size = list(image.size)
        src_sha = hashlib.sha256(sp.read_bytes()).hexdigest()
        rot = cfg['rotation_ccw']

        mask = mask_from_polygon(image.size, poly)
        source_mask = mask.copy()

        # Source overlay
        overlay = image.copy()
        draw = ImageDraw.Draw(overlay)
        pts = [tuple(p) for p in poly]
        draw.line(pts + [pts[0]], fill=(255, 0, 255), width=max(2, round(max(image.size) / 600)))

        # Rotate if requested
        render_img = image
        render_mask = mask
        if rot:
            render_img = render_img.rotate(rot, expand=True)
            render_mask = np.rot90(render_mask, rot // 90).copy()

        output, layout = render_verified_packshot(
            render_img, render_mask, shape=cfg.get('shape', 'auto'), fit_to_native=cfg['fit_to_native']
        )

        front_path = OUT_DIR / f'{stem}-front.png'
        mask_path = OUT_DIR / f'{stem}-mask.png'
        overlay_path = OUT_DIR / f'{stem}-source-overlay.jpg'

        output.save(front_path)
        Image.fromarray(source_mask).save(mask_path)
        overlay.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        overlay.save(overlay_path, quality=95)

        front_sha = hashlib.sha256(front_path.read_bytes()).hexdigest()
        mask_sha = hashlib.sha256(mask_path.read_bytes()).hexdigest()
        overlay_sha = hashlib.sha256(overlay_path.read_bytes()).hexdigest()

        scale = layout['upscale_factor']
        assert scale <= 1.0, f"Error: Upscaling detected for row {row}: scale={scale}"
        assert output.size == (2400, 2400), f"Error: Output canvas size {output.size} != (2400, 2400)"

        print(f"Row {row:4d} | BC: {bc:14s} | Scale: {scale:.4f} | Size: {output.size} | front_sha: {front_sha[:10]}...")

        annotation = {
            'excel_row': row,
            'barcode': bc,
            'record_id': rid,
            'source_path': str(sp.resolve()),
            'source_sha256': src_sha,
            'source_size': src_size,
            'identity_verified': True,
            'complete_package': True,
            'single_product_verified': True,
            'face': 'front',
            'rotation_ccw': rot,
            'polygon': poly,
            'evidence': cfg['evidence'],
            'review_limitations': cfg['review_limitations']
        }
        annotations.append(annotation)

        manifest_entry = {
            'excel_row': row,
            'barcode': bc,
            'record_id': rid,
            'product_name_en': cfg['product_name_en'],
            'decision': 'READY_FOR_USER_QA',
            'source_path': str(sp.resolve()),
            'source_sha256': src_sha,
            'output_path': str(front_path.resolve()),
            'output_sha256': front_sha,
            'mask_path': str(mask_path.resolve()),
            'mask_sha256': mask_sha,
            'overlay_path': str(overlay_path.resolve()),
            'overlay_sha256': overlay_sha,
            'layout_upscale_factor': scale,
            'scale_layout': f"{scale}; source {src_size[0]}x{src_size[1]}, bbox {layout['native_package_size'][0]}x{layout['native_package_size'][1]}, placed {layout['placed_size'][0]}x{layout['placed_size'][1]}",
            'visual_evidence': cfg['evidence']
        }
        manifest_items.append(manifest_entry)

        results_records.append({
            'excel_row': row,
            'barcode': bc,
            'record_id': rid,
            'product_name_en': cfg['product_name_en'],
            'status': 'REPROCESSED_NEEDS_REVIEW',
            'source_path': str(sp.resolve()),
            'source_sha256': src_sha,
            'source_size': src_size,
            'annotation': annotation,
            'output_path': str(front_path.resolve()),
            'output_sha256': front_sha,
            'mask_path': str(mask_path.resolve()),
            'mask_sha256': mask_sha,
            'overlay_path': str(overlay_path.resolve()),
            'layout': layout,
            'reason': 'Rendered from reviewed source boundary; ready for independent cross-QA visual review'
        })

    # Save outputs
    (OUT_DIR / 'annotations.jsonl').write_text(
        ''.join(json.dumps(a, ensure_ascii=False) + '\n' for a in annotations), encoding='utf-8'
    )
    (OUT_DIR / 'candidate_manifest.jsonl').write_text(
        ''.join(json.dumps(m, ensure_ascii=False) + '\n' for m in manifest_items), encoding='utf-8'
    )
    (OUT_DIR / 'results.jsonl').write_text(
        ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in results_records), encoding='utf-8'
    )
    (OUT_DIR / 'summary.json').write_text(
        json.dumps({
            'batch_range': '761..1100',
            'total_candidates_rendered': len(manifest_items),
            'status': 'READY_FOR_USER_QA',
            'upscale_guarantee': 'All candidates have upscale_factor <= 1.0 on 2400x2400 canvas',
            'delivery_modified': False,
            'candidates': [
                {'row': m['excel_row'], 'barcode': m['barcode'], 'product': m['product_name_en'], 'scale': m['layout_upscale_factor']}
                for m in manifest_items
            ]
        }, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    print(f"\nCompleted! Generated manifest with {len(manifest_items)} candidate packshots in {OUT_DIR}.")

if __name__ == '__main__':
    run()
