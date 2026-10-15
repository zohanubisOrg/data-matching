#!/usr/bin/env python3
"""
scripts/inventory_engine.py
---------------------------
Core engine for Rabuta Source Image Inventory Subagents.
Safely indexes warehouse source images without modifying any source files.
Cross-references against reference catalog:
D:\\Work\\shopify\\output\\catalog_pairs\\reprocess-v4\\full-catalog-resolved-20261015\\candidates\\results.jsonl
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Set utf-8 stdout/stderr on windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import pillow_heif
from PIL import Image, ImageOps
import zxingcpp

pillow_heif.register_heif_opener()

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from product_mapper.vision.barcode_side_splitter import read_retail_barcodes
from product_mapper.vision.barcode_validator import validate_ean_upc_checksum

CATALOG_PATH = (
    ROOT
    / "output"
    / "catalog_pairs"
    / "reprocess-v4"
    / "full-catalog-resolved-20261015"
    / "candidates"
    / "results.jsonl"
)
OUTPUT_DIR = ROOT / "output" / "catalog_pairs" / "review" / "external_source_inventory"

KNOWN_FOLDERS = [
    "G1_original",
    "G2_original",
    "G3_Original",
    "G4-original",
    "Nyt25.09.26",
]


class CatalogKnowledge:
    def __init__(self):
        self.barcode_to_records: Dict[str, List[str]] = defaultdict(list)
        self.catalog_by_file: Dict[Tuple[str, str], List[Tuple[str, str]]] = defaultdict(list)
        self.manifest_by_file: Dict[Tuple[str, str], List[Tuple[str, str]]] = defaultdict(list)
        self.global_sha256_map: Dict[str, List[Tuple[str, str, str]]] = defaultdict(list)
        self.duplicate_hashes: Set[str] = set()
        self.multi_image_barcodes: Set[str] = set()

    def load_catalog(self):
        print(f"Loading reference catalog from {CATALOG_PATH}...")
        if not CATALOG_PATH.exists():
            raise FileNotFoundError(f"Catalog not found: {CATALOG_PATH}")

        barcode_counts = defaultdict(int)

        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                r = json.loads(line)
                rec_id = str(r.get("record_id", "")).strip()
                bc = str(r.get("barcode", "")).strip()
                if bc:
                    self.barcode_to_records[bc].append(rec_id)

                # Map source_candidates
                cands = r.get("source_candidates", [])
                if bc and cands:
                    barcode_counts[bc] += len(cands)

                for cand in cands:
                    base = Path(cand).name
                    for fld in KNOWN_FOLDERS:
                        if base.startswith(f"{fld}_"):
                            real_fname = base[len(fld) + 1 :]
                            self.catalog_by_file[(fld, real_fname)].append((rec_id, bc))
                            break

                # Map source_path if given
                sp = r.get("source_path")
                if sp:
                    base = Path(sp).name
                    for fld in KNOWN_FOLDERS:
                        if fld in sp:
                            self.catalog_by_file[(fld, base)].append((rec_id, bc))
                            break

        for bc, cnt in barcode_counts.items():
            if cnt > 1:
                self.multi_image_barcodes.add(bc)

        print(
            f"Catalog loaded: {len(self.barcode_to_records)} distinct barcodes, "
            f"{len(self.catalog_by_file)} filename mappings, "
            f"{len(self.multi_image_barcodes)} multi-candidate barcodes in catalog."
        )

    def load_manifests(self):
        # Additional manifests for unreadable / backup mappings
        manifest_files = [
            ("G1_original", ROOT / "output/catalog_pairs/manifest_G1_original_v2.json"),
            ("G2_original", ROOT / "output/catalog_pairs/manifest_G2_original_v2.json"),
            ("G3_Original", ROOT / "output/catalog_pairs/manifest_G3_Original_v2.json"),
            ("G4-original", ROOT / "output/catalog_pairs/manifest_G4-original_v2.json"),
            ("Nyt25.09.26", ROOT / "output/catalog_pairs/manifest_Nyt25.09.26_v2.json"),
        ]

        for folder, m_path in manifest_files:
            if m_path.exists():
                try:
                    with open(m_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        prods = data.get("products", {})
                        if isinstance(prods, dict):
                            for bc, pinfo in prods.items():
                                src = pinfo.get("source", "")
                                if src:
                                    fname = Path(src).name
                                    # rec_id may or may not be known, associate with barcode
                                    self.manifest_by_file[(folder, fname)].append(("", str(bc).strip()))
                except Exception as e:
                    print(f"Warning reading manifest {m_path}: {e}")

        # Also check output/catalog_pairs/originals
        originals_dir = ROOT / "output" / "catalog_pairs" / "originals"
        if originals_dir.exists():
            for root, dirs, files in os.walk(originals_dir):
                bc = Path(root).name
                if bc.isdigit():
                    for f in files:
                        for fld in KNOWN_FOLDERS:
                            if f.startswith(f"{fld}_"):
                                real_fname = f[len(fld) + 1 :]
                                self.manifest_by_file[(fld, real_fname)].append(("", bc))
                                break

        print(f"Manifest & originals mappings loaded: {len(self.manifest_by_file)} files mapped.")

    def precompute_hashes(self, folder_paths: List[Tuple[str, Path]]):
        print("Computing SHA-256 hashes across target folders...")
        t0 = time.time()
        count = 0
        for fld_name, fld_path in folder_paths:
            for root, dirs, files in os.walk(fld_path):
                for f in files:
                    ext = Path(f).suffix.lower()
                    if ext in [".jpg", ".jpeg", ".png", ".heic", ".heif"]:
                        full_p = Path(root) / f
                        count += 1
                        try:
                            with open(full_p, "rb") as fp:
                                h = hashlib.sha256(fp.read()).hexdigest()
                            self.global_sha256_map[h].append((fld_name, f, str(full_p)))
                        except Exception as e:
                            print(f"Error hashing {full_p}: {e}")

        for h, items in self.global_sha256_map.items():
            if len(items) > 1:
                self.duplicate_hashes.add(h)

        print(
            f"Hashed {count} files in {time.time() - t0:.2f}s. "
            f"Found {len(self.duplicate_hashes)} duplicate hash groups."
        )


def process_single_image(
    file_path: Path,
    source_folder: str,
    knowledge: CatalogKnowledge,
) -> Dict[str, Any]:
    abs_path = str(file_path.resolve())
    filename = file_path.name
    notes_list: List[str] = []

    # File size and hash
    try:
        file_size_bytes = file_path.stat().st_size
    except Exception:
        file_size_bytes = 0

    try:
        with open(file_path, "rb") as fp:
            sha256_val = hashlib.sha256(fp.read()).hexdigest()
    except Exception as e:
        sha256_val = ""
        notes_list.append(f"hash_error_{e}")

    # Check duplicate hash
    if sha256_val in knowledge.duplicate_hashes:
        dup_others = [
            f"{item[0]}/{item[1]}"
            for item in knowledge.global_sha256_map.get(sha256_val, [])
            if item[2] != abs_path
        ]
        notes_list.append(f"duplicate_hash(same_as:{','.join(dup_others)})")

    # Check subdirectory
    if "_removed_not_in_excel" in abs_path:
        notes_list.append("in_removed_not_in_excel_subdir")

    # Open image
    width = 0
    height = 0
    fmt = "UNKNOWN"
    image_open_ok = False
    im = None

    try:
        im = Image.open(file_path)
        im.load()
        width, height = im.size
        fmt = im.format or Path(file_path).suffix.upper().replace(".", "")
        image_open_ok = True
    except Exception as e:
        notes_list.append(f"unopenable_corrupt_image({e})")

    if not image_open_ok or im is None:
        return {
            "source_path": abs_path,
            "source_folder": source_folder,
            "filename": filename,
            "barcode_candidates": [],
            "matched_record_ids": [],
            "match_method": "unmatched",
            "width": 0,
            "height": 0,
            "format": fmt,
            "file_size_bytes": file_size_bytes,
            "sha256": sha256_val,
            "notes": "; ".join(notes_list),
        }

    # Resolution check
    if width < 1200 or height < 1200:
        notes_list.append(f"low_resolution_source({width}x{height})")

    # Barcode scanning
    scanned_barcodes: List[str] = []
    try:
        # 1. Retail multi-scale scan
        hits = read_retail_barcodes(im)
        for h in hits:
            clean = "".join(c for c in str(h.text or "") if c.isdigit())
            if clean and validate_ean_upc_checksum(clean):
                if clean not in scanned_barcodes:
                    scanned_barcodes.append(clean)

        # 2. Direct zxingcpp fallback if no hits
        if not scanned_barcodes:
            z_hits = zxingcpp.read_barcodes(im, try_rotate=True, try_downscale=True, try_invert=True)
            for zh in z_hits:
                clean = "".join(c for c in str(zh.text or "") if c.isdigit())
                if clean and validate_ean_upc_checksum(clean):
                    if clean not in scanned_barcodes:
                        scanned_barcodes.append(clean)
    except Exception as e:
        notes_list.append(f"barcode_scan_exception({e})")
    finally:
        try:
            im.close()
        except Exception:
            pass

    # Catalog & Filename Cross-Reference
    cat_entries = knowledge.catalog_by_file.get((source_folder, filename), [])
    if not cat_entries:
        cat_entries = knowledge.manifest_by_file.get((source_folder, filename), [])

    barcode_candidates: List[str] = []
    matched_record_ids: List[str] = []
    match_method: str = "unmatched"

    if scanned_barcodes:
        # We have scanned barcode(s) directly from the image
        matched_records_set: List[str] = []
        for s_bc in scanned_barcodes:
            for r_id in knowledge.barcode_to_records.get(s_bc, []):
                if r_id not in matched_records_set:
                    matched_records_set.append(r_id)

        if len(scanned_barcodes) == 1:
            single_bc = scanned_barcodes[0]
            barcode_candidates = [single_bc]

            if len(matched_records_set) == 1:
                matched_record_ids = matched_records_set
                match_method = "exact_barcode"
            elif len(matched_records_set) > 1:
                matched_record_ids = matched_records_set
                match_method = "ambiguous"
                notes_list.append(f"barcode_matches_multiple_catalog_records({','.join(matched_records_set)})")
            else:
                # Scanned barcode not in catalog
                if cat_entries:
                    # Catalog has a different mapping for this filename
                    cat_bcs = list(dict.fromkeys(b for _, b in cat_entries if b))
                    cat_recs = list(dict.fromkeys(r for r, _ in cat_entries if r))
                    barcode_candidates = list(dict.fromkeys([single_bc] + cat_bcs))
                    matched_record_ids = cat_recs
                    match_method = "ambiguous"
                    notes_list.append("conflict_scanned_barcode_not_in_catalog_but_filename_mapped")
                else:
                    matched_record_ids = []
                    match_method = "unmatched"
                    notes_list.append("barcode_not_in_catalog")
        else:
            # Multiple distinct barcodes scanned on one image
            barcode_candidates = scanned_barcodes
            matched_record_ids = matched_records_set
            match_method = "ambiguous"
            notes_list.append(f"multiple_barcodes_detected_in_image({','.join(scanned_barcodes)})")

    else:
        # No barcode detected directly on image
        if cat_entries:
            cat_bcs = list(dict.fromkeys(b for _, b in cat_entries if b))
            cat_recs = list(dict.fromkeys(r for r, _ in cat_entries if r))

            # Also resolve any record_ids for cat_bcs if cat_recs empty
            if not cat_recs:
                for cb in cat_bcs:
                    for cr in knowledge.barcode_to_records.get(cb, []):
                        if cr not in cat_recs:
                            cat_recs.append(cr)

            barcode_candidates = cat_bcs
            matched_record_ids = cat_recs

            if len(cat_recs) == 1:
                match_method = "filename_match"
                notes_list.append("barcode_resolved_via_catalog_filename_mapping")
            elif len(cat_recs) > 1:
                match_method = "ambiguous"
                notes_list.append(f"filename_mapped_to_multiple_records({','.join(cat_recs)})")
            elif len(cat_bcs) >= 1:
                match_method = "filename_match"
                notes_list.append("barcode_resolved_via_manifest_no_record_id")
            else:
                match_method = "unmatched"
                notes_list.append("no_barcode_detected")
        else:
            barcode_candidates = []
            matched_record_ids = []
            match_method = "unmatched"
            notes_list.append("no_barcode_detected_no_catalog_match")

    # Multi-image barcode check
    for bc in barcode_candidates:
        if bc in knowledge.multi_image_barcodes:
            notes_list.append(f"multi_source_images_for_barcode({bc})")
            break

    return {
        "source_path": abs_path,
        "source_folder": source_folder,
        "filename": filename,
        "barcode_candidates": barcode_candidates,
        "matched_record_ids": matched_record_ids,
        "match_method": match_method,
        "width": width,
        "height": height,
        "format": fmt,
        "file_size_bytes": file_size_bytes,
        "sha256": sha256_val,
        "notes": "; ".join(notes_list),
    }


def run_subagent_inventory(
    agent_name: str,
    target_folders: List[str],
    output_filename: str,
    max_workers: int = 8,
):
    print(f"=== Starting Subagent {agent_name} ===")
    print(f"Scope: {target_folders}")
    print(f"Output File: {output_filename}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / output_filename

    # Build knowledge
    knowledge = CatalogKnowledge()
    knowledge.load_catalog()
    knowledge.load_manifests()

    # Discover files
    folder_paths = []
    for fld in target_folders:
        p = ROOT / "source-import" / fld
        if not p.exists():
            raise FileNotFoundError(f"Source folder not found: {p}")
        folder_paths.append((fld, p))

    # Precompute hashes for duplicate detection
    knowledge.precompute_hashes(folder_paths)

    # Collect files to process
    tasks: List[Tuple[Path, str]] = []
    for fld_name, fld_path in folder_paths:
        for root, dirs, files in os.walk(fld_path):
            for f in sorted(files):
                ext = Path(f).suffix.lower()
                if ext in [".jpg", ".jpeg", ".png", ".heic", ".heif"]:
                    tasks.append((Path(root) / f, fld_name))

    print(f"Subagent {agent_name}: Total images to process: {len(tasks)}")

    # Process in parallel using ThreadPoolExecutor
    t0 = time.time()
    results: List[Dict[str, Any]] = []
    completed = 0
    total = len(tasks)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {
            executor.submit(process_single_image, path, fld, knowledge): (path, fld)
            for path, fld in tasks
        }

        for future in as_completed(future_to_task):
            res = future.result()
            results.append(res)
            completed += 1
            if completed % 50 == 0 or completed == total:
                elapsed = time.time() - t0
                rate = completed / max(0.1, elapsed)
                print(f"[{agent_name}] Processed {completed}/{total} images ({rate:.1f} img/s)...")

    # Sort results by source_folder, filename for determinism
    results.sort(key=lambda x: (x["source_folder"], x["filename"]))

    # Write JSONL
    print(f"Writing {len(results)} rows to {out_path}...")
    with open(out_path, "w", encoding="utf-8") as f:
        for row in results:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    elapsed = time.time() - t0
    print(f"=== Subagent {agent_name} Finished in {elapsed:.2f}s ===")
    print(f"Output saved to: {out_path}")
