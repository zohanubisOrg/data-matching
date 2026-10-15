"""Snapshot current front-v3 and revert 5 defective images back to pre-overwrite originals.

Targets:
- 4045198753174 (row 850, G2-0401)
- 7178600000140 (row 886, G2-0437)
- 5017689097905 (row 894, G2-0445)
- 6922163623848 (row 926, G3-0025)
- 8855790000028 (row 970, G3-0080)
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().lower()

def main():
    root = Path(r"D:\Work\shopify")
    target_dir = root / r"output\catalog_pairs\tagged\front-v3"
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = root / f"output/catalog_pairs/backups/front-v3_revert_defective_5_{timestamp}"
    
    print(f"Target directory: {target_dir}")
    print(f"New Snapshot Backup directory: {backup_dir}")
    
    # Pre-checks
    if not target_dir.is_dir():
        raise RuntimeError(f"Target dir does not exist: {target_dir}")
    
    target_files = sorted(target_dir.glob("*-front.jpg"))
    print(f"Found {len(target_files)} front files in target dir.")
    if len(target_files) != 1352:
        print(f"WARNING: Expected 1352 files, found {len(target_files)}")

    # 1. Snapshot all 1352 files before reverting
    backup_dir.mkdir(parents=True, exist_ok=False)
    backup_files_dir = backup_dir / "files"
    backup_files_dir.mkdir(parents=True, exist_ok=False)
    
    print("Creating snapshot backup of all files...")
    snapshot_manifest = {
        "target_dir": str(target_dir),
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "purpose": "Pre-revert snapshot before reverting 5 defective images (rows 850, 886, 894, 926, 970)",
        "files": []
    }
    
    for idx, f in enumerate(target_files, 1):
        digest = sha256_file(f)
        dest = backup_files_dir / f.name
        shutil.copy2(f, dest)
        dest_digest = sha256_file(dest)
        if dest_digest != digest:
            raise RuntimeError(f"Backup copy verification failed for {f.name}: {digest} != {dest_digest}")
        snapshot_manifest["files"].append({
            "name": f.name,
            "sha256": digest,
            "bytes": f.stat().st_size
        })
        if idx % 200 == 0 or idx == len(target_files):
            print(f"  Backed up {idx}/{len(target_files)} files...")
            
    snapshot_path = backup_dir / "snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Snapshot written to {snapshot_path}")

    # 2. Definitions of 5 items to revert
    b1_dir = root / r"output\catalog_pairs\backups\front-v3_pending_userqa_850_886_894_20261015_205220\files"
    b2_dir = root / r"output\catalog_pairs\backups\front-v3_pending_userqa_926_970_20261015_205338\files"
    
    revert_items = [
        {
            "name": "4045198753174-front.jpg",
            "excel_row": 850,
            "record_id": "G2-0401",
            "barcode": "4045198753174",
            "source_backup_path": str(b1_dir / "4045198753174-front.jpg"),
            "expected_restored_sha256": "1fed118e706e95a20e92c07f37c20d3b26bbf070f3898f298b186cc4695c725d",
            "defective_sha256": "785336c0659f6f73650a9d405a610429803127ec7513d0aa965ce4e7861ca334",
        },
        {
            "name": "7178600000140-front.jpg",
            "excel_row": 886,
            "record_id": "G2-0437",
            "barcode": "7178600000140",
            "source_backup_path": str(b1_dir / "7178600000140-front.jpg"),
            "expected_restored_sha256": "c4cb349979177e0cafb287753139d41e5ebb5444950408e08bf67800c07edf7f",
            "defective_sha256": "048a1c88a62e33dbd9235301ff30287b307f9a637feb20d451057e824852e718",
        },
        {
            "name": "5017689097905-front.jpg",
            "excel_row": 894,
            "record_id": "G2-0445",
            "barcode": "5017689097905",
            "source_backup_path": str(b1_dir / "5017689097905-front.jpg"),
            "expected_restored_sha256": "49ff4be4c514bf7de4117c6e7c49b33196a205771fcc715b6cbc49d83cf14fc1",
            "defective_sha256": "f87bc998326c06fd54c384dda86ae8ceb2ac5041c9efb5fdb3449aa498254057",
        },
        {
            "name": "6922163623848-front.jpg",
            "excel_row": 926,
            "record_id": "G3-0025",
            "barcode": "6922163623848",
            "source_backup_path": str(b2_dir / "6922163623848-front.jpg"),
            "expected_restored_sha256": "8098e6af397c81f64db7c68eabcc6b9eb15ab78ec54c865844414478eb165050",
            "defective_sha256": "4808cadf0e98a30fbb4f556710fc47a15797d5ec7dc8aefadddc83676441828f",
        },
        {
            "name": "8855790000028-front.jpg",
            "excel_row": 970,
            "record_id": "G3-0080",
            "barcode": "8855790000028",
            "source_backup_path": str(b2_dir / "8855790000028-front.jpg"),
            "expected_restored_sha256": "7524af88043148175db85c4ac53782aee0df3eace1c319f306c85546d88e1573",
            "defective_sha256": "77ae92d5f9d5190d9b774f2fa51d8a184db8f6e8c57c31db415700e0b0a99946",
        },
    ]

    # Verify source backup files exist and match expected hashes before copying
    for item in revert_items:
        src_path = Path(item["source_backup_path"])
        if not src_path.is_file():
            raise FileNotFoundError(f"Source file not found: {src_path}")
        src_hash = sha256_file(src_path)
        if src_hash != item["expected_restored_sha256"]:
            raise RuntimeError(f"Source hash mismatch for {item['name']}: {src_hash} != {item['expected_restored_sha256']}")
        print(f"Pre-check PASS: {item['name']} source verified ({src_hash[:12]}...)")

    # 3. Perform Revert: copy original files to target_dir atomically
    print("\nExecuting Revert to target_dir...")
    revert_journal_entries = []
    
    for item in revert_items:
        dest_file = target_dir / item["name"]
        current_hash = sha256_file(dest_file)
        if current_hash != item["defective_sha256"]:
            print(f"WARNING: Current hash {current_hash} differs from recorded defective hash {item['defective_sha256']}")
        
        # Staging copy then atomic replace
        staging_file = target_dir / f".{item['name']}.revert_tmp"
        shutil.copy2(item["source_backup_path"], staging_file)
        staged_hash = sha256_file(staging_file)
        if staged_hash != item["expected_restored_sha256"]:
            staging_file.unlink()
            raise RuntimeError(f"Staged copy hash mismatch for {item['name']}")
        
        # Replace
        os.replace(staging_file, dest_file)
        
        # Verify in-place
        final_hash = sha256_file(dest_file)
        if final_hash != item["expected_restored_sha256"]:
            raise RuntimeError(f"Revert failed! Final hash {final_hash} != {item['expected_restored_sha256']}")
        
        print(f"REVERT SUCCESS: {item['name']} (Row {item['excel_row']}, {item['barcode']}) -> SHA256: {final_hash}")
        
        revert_journal_entries.append({
            "name": item["name"],
            "excel_row": item["excel_row"],
            "barcode": item["barcode"],
            "record_id": item["record_id"],
            "pre_revert_defective_sha256": current_hash,
            "post_revert_restored_sha256": final_hash,
            "restored_from": item["source_backup_path"],
            "revert_status": "RESTORED_AND_VERIFIED",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        })

    # 4. Write revert_journal.json
    journal = {
        "status": "REVERTED_AND_VERIFIED",
        "action": "REVERT_DEFECTIVE_5_IMAGES",
        "target_dir": str(target_dir),
        "backup_dir": str(backup_dir),
        "reverted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total_reverted": len(revert_journal_entries),
        "entries": revert_journal_entries
    }
    
    journal_path = backup_dir / "revert_journal.json"
    journal_path.write_text(json.dumps(journal, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # Also write a copy to output/catalog_pairs/revert_journal.json for direct visibility
    top_journal_path = root / r"output\catalog_pairs\revert_journal.json"
    top_journal_path.write_text(json.dumps(journal, indent=2, ensure_ascii=False), encoding="utf-8")
    
    print(f"\nJournal written to:\n  - {journal_path}\n  - {top_journal_path}")
    print("\nALL 5 DEFECTIVE IMAGES REVERTED AND VERIFIED SUCCESSFULLY!")

if __name__ == "__main__":
    main()
