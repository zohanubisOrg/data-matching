"""Inventory audit sources and render only identity-bound, reviewed package outlines.

No network fetch, workbook edit, generated content or delivery overwrite. Source
paths/dimensions refer to the EXIF-oriented image, before any optional rotation.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from product_mapper.vision.package_packshot import (
    UnverifiedPackageError, mask_from_polygon, render_verified_packshot,
)


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8-sig').splitlines() if line.strip()]


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def key(record):
    return (str(record['barcode']), str(record['record_id']), int(record['excel_row']))


def open_source(path):
    if Path(path).suffix.lower() in ('.heic', '.heif'):
        import pillow_heif
        pillow_heif.register_heif_opener()
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert('RGB')


def run_reprocessing(records, annotations, output_dir, originals_dir, source_map=None, *, catalog_records=None):
    output_dir, originals_dir = Path(output_dir).resolve(), Path(originals_dir).resolve()
    if any(p.lower() in ('front-v2','front-v3','back-v2','originals','front_photos') for p in output_dir.parts):
        raise ValueError('Output must be a new review directory, separate from sources and delivery')
    if output_dir == originals_dir or originals_dir in output_dir.parents:
        raise ValueError('Cannot save into originals')
    indexed = {}
    for annotation in annotations:
        k = key(annotation)
        if k in indexed:
            raise ValueError(f'Duplicate annotation identity: {k}')
        indexed[k] = annotation
    if len({key(r) for r in records}) != len(records):
        raise ValueError('Duplicate record identity in input')
    identities = defaultdict(set)
    for record in (catalog_records if catalog_records is not None else records):
        if record['barcode']:
            identities[str(record['barcode'])].add(str(record['record_id']))
    output_dir.mkdir(parents=True, exist_ok=False)
    results = []
    for record in records:
        bc, rid, row = key(record)
        result = {**record, 'status': 'NEEDS_MANUAL_REVIEW', 'qa_pass': False}
        candidates = []
        if bc and re.fullmatch(r'[0-9]+', bc):
            candidates = sorted(p.resolve() for p in (originals_dir/bc).glob('*')
                                if p.is_file() and p.suffix.lower() in ('.jpg','.jpeg','.png','.heic','.heif','.tif','.tiff'))
            for proposed in (source_map or {}).get(bc, {}).get('paths', []):
                path = Path(proposed)
                if not path.is_absolute():
                    path = ROOT/path
                path = path.resolve()
                if (path.is_file() and path.suffix.lower() in ('.jpg','.jpeg','.png','.heic','.heif','.tif','.tiff')
                    and not any(p.lower() in ('front-v2','front-v3','back-v2','front_photos') for p in path.parts)):
                    candidates.append(path)
            candidates = sorted(set(candidates))
        result['source_candidates'] = [str(p) for p in candidates]
        if bc and len(identities[bc]) > 1:
            result.update(status='BLOCKED_IDENTITY_CONFLICT', reason='Barcode belongs to multiple Record IDs; verify identity before rendering')
        elif not bc or not rid:
            result.update(status='BLOCKED_NEEDS_SOURCE', reason='Missing product identity')
        elif key(record) not in indexed:
            result.update(status='NEEDS_MANUAL_REVIEW' if candidates else 'BLOCKED_NEEDS_SOURCE',
                          reason='Source files are candidates only; verified identity/front/complete boundary required' if candidates else 'No verified native source; Excel previews are not restoration sources')
        else:
            annotation = indexed[key(record)]
            try:
                source = Path(annotation['source_path'])
                if not source.is_absolute():
                    source = ROOT/source
                source = source.resolve()
                if not source.is_file():
                    result.update(status='BLOCKED_NEEDS_SOURCE', reason='Annotated source file missing')
                    results.append(result)
                    continue
                if any(p.lower() in ('front-v2','front-v3','back-v2','front_photos') for p in source.parts):
                    raise UnverifiedPackageError('Damaged cutout or preview cannot be a restoration source')
                if annotation.get('identity_verified') is not True or annotation.get('face') != 'front':
                    raise UnverifiedPackageError('Authentic product identity and true front not verified')
                if annotation.get('complete_package') is not True or not annotation.get('evidence'):
                    raise UnverifiedPackageError('Complete package and review evidence required')
                if annotation.get('single_product_verified') is not True:
                    raise UnverifiedPackageError('One real sales unit must be visually verified; one connected component is insufficient')
                if annotation.get('film_matting_required'):
                    raise UnverifiedPackageError('Empty transparent film needs separate matting review')
                source_hash = sha256(source)
                if source_hash != annotation.get('source_sha256'):
                    raise UnverifiedPackageError('Source hash differs from reviewed annotation')
                image = open_source(source)
                if list(image.size) != annotation.get('source_size'):
                    raise UnverifiedPackageError('EXIF-oriented source dimensions differ from annotation')
                mask = mask_from_polygon(image.size, annotation['polygon'])
                source_mask = mask.copy()
                overlay = image.copy()
                draw = ImageDraw.Draw(overlay)
                points = [tuple(p) for p in annotation['polygon']]
                draw.line(points+[points[0]], fill=(255,0,255), width=max(2,round(max(image.size)/600)))
                rotation = annotation.get('rotation_ccw', 0)
                if rotation not in (0,90,180,270):
                    raise UnverifiedPackageError('Only explicit right-angle orientation adjustments supported')
                if rotation:
                    image = image.rotate(rotation, expand=True)
                    mask = np.rot90(mask, rotation//90).copy()
                output, layout = render_verified_packshot(image, mask, shape=annotation.get('shape','auto'))
                layout.update(render_source_size=list(image.size), rotation_ccw=rotation,
                              coordinates='EXIF-oriented source after rotation_ccw')
                stem = f'{bc}__{rid}__row{row:04d}'
                if not re.fullmatch(r'[A-Za-z0-9_-]+', stem):
                    raise UnverifiedPackageError('Identity cannot be used as a safe output filename')
                front_path = output_dir/f'{stem}-front.png'
                mask_path = output_dir/f'{stem}-mask.png'
                overlay_path = output_dir/f'{stem}-source-overlay.jpg'
                output.save(front_path)
                Image.fromarray(source_mask).save(mask_path)
                overlay.thumbnail((1600,1600), Image.Resampling.LANCZOS)
                overlay.save(overlay_path, quality=95)
                result.update(status='REPROCESSED_NEEDS_REVIEW', source_path=str(source), source_sha256=source_hash,
                              source_size=annotation['source_size'], annotation=annotation,
                              output_path=str(front_path), output_sha256=sha256(front_path),
                              mask_path=str(mask_path), mask_sha256=sha256(mask_path),
                              overlay_path=str(overlay_path), layout=layout,
                              reason='Rendered from reviewed source boundary; final visual QA and back-image review pending')
            except (KeyError, ValueError, OSError, ImportError) as exc:
                result.update(status='NEEDS_MANUAL_REVIEW', reason=f'{type(exc).__name__}: {exc}')
        results.append(result)
    with (output_dir/'results.jsonl').open('w', encoding='utf-8') as stream:
        for result in results:
            stream.write(json.dumps(result, ensure_ascii=False)+'\n')
    (output_dir/'summary.json').write_text(json.dumps({
        'records': len(results), 'statuses': dict(Counter(r['status'] for r in results)),
        'qa_pass_count': 0, 'delivery_modified': False,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records', type=Path, required=True, help='Audit JSONL; preserve barcode as string')
    parser.add_argument('--annotations', type=Path, help='Reviewed native-source package polygons JSONL')
    parser.add_argument('--output-dir', type=Path, required=True, help='Must not already exist')
    parser.add_argument('--originals-dir', type=Path, default=ROOT/'output/catalog_pairs/originals')
    parser.add_argument('--workbook', type=Path, default=ROOT/'output/catalog_pairs/Rabuta_master_final_Delivery_Embedded.xlsx')
    parser.add_argument('--source-map', type=Path, default=ROOT/'output/catalog_pairs/front_v3_source_map.json',
                        help='Historical paths are candidates only; role labels are not trusted')
    args = parser.parse_args()
    records = read_jsonl(args.records)
    import openpyxl
    workbook = openpyxl.load_workbook(args.workbook, read_only=True, data_only=True)
    ws = workbook.active
    # Bind audit identities to current workbook rather than accepting stale row offsets.
    workbook_identities = {row: (str(values[0] or '').strip(), str(values[4] or '').strip())
                           for row, values in enumerate(ws.iter_rows(min_row=4, max_col=5, values_only=True), 4)}
    for record in records:
        row = int(record['excel_row'])
        if workbook_identities.get(row) != key(record)[:2]:
            raise ValueError(f'Workbook/audit identity mismatch at row {row}')
    workbook.close()
    results = run_reprocessing(records, read_jsonl(args.annotations) if args.annotations else [],
                               args.output_dir, args.originals_dir,
                               json.loads(args.source_map.read_text(encoding='utf-8-sig')) if args.source_map.exists() else {},
                               catalog_records=[{'excel_row':row,'barcode':identity[0],'record_id':identity[1]}
                                                for row,identity in workbook_identities.items()])
    print(json.dumps(dict(Counter(r['status'] for r in results)), ensure_ascii=False))
    # Explicitly distinct from PASS: candidates and blockers require review.
    return 2 if any(r['status'] != 'REPROCESSED_NEEDS_REVIEW' for r in results) else 0


if __name__ == '__main__':
    raise SystemExit(main())
