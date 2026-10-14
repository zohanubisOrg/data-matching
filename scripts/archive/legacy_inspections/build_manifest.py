from __future__ import annotations

import json
from pathlib import Path
from product_mapper.ingestion.image_loader import SUPPORTED_EXTENSIONS, open_image_safely


def build_manifest():
    base_dir = Path("source-import")
    batches = {
        "G2": base_dir / "G2_original",
        "G3": base_dir / "G3_Original",
        "G4": base_dir / "G4-original",
        "G5": base_dir / "Nyt25.09.26",
    }
    
    manifest = {
        "summary": {},
        "batches": {},
    }
    
    total_images = 0
    
    for batch_name, batch_path in batches.items():
        if not batch_path.exists():
            print(f"Directory {batch_path} not found!")
            continue
        
        files = []
        for file_path in sorted(batch_path.iterdir()):
            if file_path.is_file() and file_path.suffix.casefold() in SUPPORTED_EXTENSIONS:
                files.append({
                    "batch": batch_name,
                    "filename": file_path.name,
                    "relative_path": str(file_path.relative_to(Path("."))),
                    "extension": file_path.suffix.lower(),
                    "size_bytes": file_path.stat().st_size,
                })
        
        manifest["batches"][batch_name] = {
            "folder": str(batch_path),
            "count": len(files),
            "files": files,
        }
        total_images += len(files)
        print(f"Batch {batch_name}: {len(files)} files in {batch_path}")
    
    manifest["summary"] = {
        "total_batches": len(manifest["batches"]),
        "total_images": total_images,
    }
    
    out_file = Path("output/g2_g5_manifest.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    
    print(f"Manifest written to {out_file}. Total images: {total_images}")


if __name__ == "__main__":
    build_manifest()
