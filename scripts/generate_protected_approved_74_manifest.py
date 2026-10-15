"""Generate protected manifest for 74 approved catalog front images.

Prohibits any overwrite on these 74 files.
"""
from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().lower()

def main():
    root = Path(r"D:\Work\shopify")
    front_v3 = root / r"output\catalog_pairs\tagged\front-v3"
    out_manifest_path = root / r"output\catalog_pairs\reprocess-v4\protected_approved_74.jsonl"
    
    # 1. 69 user approved candidates
    p1 = root / r"output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/candidates/qa_passed_user_approved_69_20261015.jsonl"
    items_69 = [json.loads(line) for line in p1.read_text(encoding="utf-8").splitlines() if line.strip()]
    
    # 2. 3 native scale published images
    p2 = root / r"output/catalog_pairs/reprocess-v4/publication_native_scale_six_20261015/publication.json"
    pub2 = json.loads(p2.read_text(encoding="utf-8"))
    target_barcodes_2 = {"8720301103324", "8852018101277", "5011308306362"}
    items_3 = [c for c in pub2.get("changes", []) if str(c.get("barcode")) in target_barcodes_2]
    
    # 3. 2 additional QA pass annotations
    p3 = root / r"output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/candidates/qa_passed_additional_annotations_398_458_20261015.jsonl"
    items_2 = [json.loads(line) for line in p3.read_text(encoding="utf-8").splitlines() if line.strip()]

    print(f"Loaded: 69 approved ({len(items_69)}), 3 native scale ({len(items_3)}), 2 additional QA ({len(items_2)})")
    
    records = []
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    # Process 69 items
    for it in items_69:
        bc = str(it["barcode"])
        row = int(it["excel_row"])
        rec_id = str(it["record_id"])
        fname = f"{bc}-front.jpg"
        live_path = front_v3 / fname
        if not live_path.is_file():
            # Check if png
            png_path = front_v3 / f"{bc}-front.png"
            if png_path.is_file():
                live_path = png_path
                fname = png_path.name
            else:
                raise FileNotFoundError(f"Cannot find live file for {bc} in {front_v3}")
        
        current_hash = sha256_file(live_path)
        records.append({
            "barcode": bc,
            "excel_row": row,
            "record_id": rec_id,
            "sku": it.get("sku", ""),
            "product_name_en": it.get("product_name_en", ""),
            "brand": it.get("brand", ""),
            "file_name": fname,
            "live_file_path": str(live_path),
            "current_sha256": current_hash,
            "candidate_sha256": it.get("output_sha256", ""),
            "source_sha256": it.get("source_sha256", ""),
            "mask_sha256": it.get("mask_sha256", ""),
            "protection_status": "LOCKED_APPROVED",
            "protection_rule": "STRICTLY_PROHIBIT_OVERWRITE",
            "group": "user_approved_69",
            "approval_source": "qa_passed_user_approved_69_20261015.jsonl",
            "qa_verdict": "PASS",
            "locked_at": now_iso
        })

    # Process 3 items
    for it in items_3:
        bc = str(it["barcode"])
        row = int(it["excel_row"])
        rec_id = str(it["record_id"])
        fname = it.get("name", f"{bc}-front.jpg")
        live_path = front_v3 / fname
        if not live_path.is_file():
            raise FileNotFoundError(f"Cannot find live file for {bc} in {front_v3}")
            
        current_hash = sha256_file(live_path)
        records.append({
            "barcode": bc,
            "excel_row": row,
            "record_id": rec_id,
            "sku": "",
            "product_name_en": "",
            "brand": "",
            "file_name": fname,
            "live_file_path": str(live_path),
            "current_sha256": current_hash,
            "candidate_sha256": it.get("candidate_sha256", ""),
            "source_sha256": it.get("source_sha256", ""),
            "mask_sha256": it.get("mask_sha256", ""),
            "protection_status": "LOCKED_APPROVED",
            "protection_rule": "STRICTLY_PROHIBIT_OVERWRITE",
            "group": "publication_native_scale_3",
            "approval_source": "publication_native_scale_six_20261015/publication.json",
            "qa_verdict": "PASS",
            "locked_at": now_iso
        })

    # Process 2 items
    for it in items_2:
        bc = str(it["barcode"])
        row = int(it["excel_row"])
        rec_id = str(it["record_id"])
        fname = f"{bc}-front.jpg"
        live_path = front_v3 / fname
        if not live_path.is_file():
            raise FileNotFoundError(f"Cannot find live file for {bc} in {front_v3}")
            
        current_hash = sha256_file(live_path)
        records.append({
            "barcode": bc,
            "excel_row": row,
            "record_id": rec_id,
            "sku": it.get("sku", ""),
            "product_name_en": it.get("product_name_en", ""),
            "brand": it.get("brand", ""),
            "file_name": fname,
            "live_file_path": str(live_path),
            "current_sha256": current_hash,
            "candidate_sha256": it.get("output_sha256", ""),
            "source_sha256": it.get("source_sha256", ""),
            "mask_sha256": it.get("mask_sha256", ""),
            "protection_status": "LOCKED_APPROVED",
            "protection_rule": "STRICTLY_PROHIBIT_OVERWRITE",
            "group": "additional_qa_pass_2",
            "approval_source": "qa_passed_additional_annotations_398_458_20261015.jsonl",
            "qa_verdict": "PASS",
            "locked_at": now_iso
        })

    # Sort by excel_row
    records.sort(key=lambda x: x["excel_row"])
    
    print(f"Total compiled protected records: {len(records)}")
    assert len(records) == 74, f"Expected 74 records, got {len(records)}"
    
    # Check uniqueness
    bcs = [r["barcode"] for r in records]
    assert len(set(bcs)) == 74, "Duplicate barcodes found in manifest!"

    # Write jsonl
    out_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_manifest_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            
    print(f"Successfully generated protected manifest: {out_manifest_path}")

if __name__ == "__main__":
    main()
