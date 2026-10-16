# Design

## Context

See `proposal.md` for background and motivation. The existing visual pipeline suffered from:
- Silent duplicate reuse: Unmatched photos like `IMG_0006.jpeg` were repeatedly matched to 39+ consecutive products across the catalog due to lack of mutual exclusion and low matching thresholds.
- U2Net detail degradation: 320x320 internal mask resolution caused fuzzy edges, rounded box corners, and destruction of thin plastic wraps and hanging sombrero holes.
- Inverted front/back splitting: Guessing front vs back purely by barcode horizontal position (`bc_x >= 0.50`) without Excel Column W ground-truth comparison caused inverted views.
- Unnecessary Excel locking: Re-embedding images into a 25MB Excel workbook during every folder run caused slow turnaround and file lock conflicts.

Host Hardware Profile:
- CPU: 16 cores (AMD/Intel x86_64).
- Memory: 32 GB RAM.
- GPU: No CUDA device available (`CPUExecutionProvider` in ONNX Runtime).

## Goals / Non-Goals

**Goals:**
- Eliminate 100% of duplicate output images across all 5 partitions with strict 1-to-1 bijective mapping and SHA-256 hash collision prevention.
- Deliver crisp packaging boundaries, sharp rectangular box corners, and intact transparent films/hanging loops using `birefnet-general-lite`.
- Achieve high execution speed (~20-30 minutes per folder) using an intelligent Hybrid Matting architecture (U2Net for simple, BiRefNet for complex with dynamic auto-escalation).
- Ensure 100% correct front-view orientation by comparing both image halves directly against Column W demo thumbnails.
- Provide clean folder-by-folder CLI execution (`--partition <name>`) with deferred standalone Excel embedding (`--embed-only`).

**Non-Goals:**
- Modifying customer pre-made packshots (379 images bypass matting entirely).
- Full-catalog single-command overnight execution (user explicitly requested running and auditing folder-by-folder first).
- Modifying original raw photography or master Excel source data.

## Decisions

### 1. Hybrid Neural Matting with Dynamic Auto-Escalation
- **Choice**: Dual-engine pipeline combining `u2net` (fast screening) and `birefnet-general-lite` (1024px high-fidelity).
- **Categorization Heuristics**:
  - *Direct BiRefNet Routing*: Products in fresh produce, herbs, vegetables, mushrooms, clear liquids, transparent noodles/wrappers, or products with hanging handles/loops bypass U2Net and are matted directly with BiRefNet-general-lite.
  - *Standard U2Net Routing*: Opaque tin cans, cardboard boxes, and solid containers are processed with U2Net (0.84s).
  - *Dynamic Auto-Escalation*: If U2Net output yields solidity < 0.90, multi-component count > 1, or excessive border transparency, the image is automatically re-matted with BiRefNet-general-lite.
- **Alternatives Considered**:
  - *BiRefNet-general (2048px) for all items*: Rejected because inference takes 32s/image on CPU, requiring ~12 hours for the catalog.
  - *U2Net only with OpenCV post-processing*: Rejected because upscaling 320px masks fundamentally cannot restore lost sharp edges or fine text.

### 2. Strict Bijective (1-to-1) Photo Allocation & Anti-Duplicate Guard
- **Choice**: Enforce mutual exclusion in memory (`assigned_raw_photos: Set[Path]`).
  - Once a raw photo is claimed by a SKU, it is immediately removed from all future candidate pools.
  - In `StudioStandardizer` / file save routine, compute SHA-256 of the output 2048x2048 image. Maintain `partition_output_hashes: Dict[str, str]` (hash -> barcode). If a duplicate hash is detected, abort file save, log defect, and quarantine the SKU.
- **Alternatives Considered**:
  - *Allowing shared multi-pack photos*: Rejected because user confirmed every product in G1 has a distinct studio photograph.

### 3. Chronological Sequence Alignment for G1
- **Choice**: Implement `G1SequenceTimelineResolver`.
  - For G1, studio photography sequence (`IMG_0001` to `IMG_0460`) maps 1-to-1 with catalog rows (`G1-0001` to `G1-0460`).
  - If a barcode scan fails on `IMG_0006`, resolve its SKU via linear interpolation between the preceding verified item (`G1-0004` on `IMG_0005`) and the subsequent verified item (`G1-0007` on `IMG_0008`).
  - This eliminates cross-catalog sequence drift entirely.

### 4. Two-Half Ground-Truth Visual Orientation (Dual-Hero)
- **Choice**: For dual-view photographs in G1, G2, G3:
  1. Detect seam between objects and split into Half A (left/top) and Half B (right/bottom).
  2. Compute visual embeddings for Half A and Half B using MobileNetV3.
  3. Compare cosine similarity against the Column W demo thumbnail.
  4. Designate `argmax(similarity(Half A, Demo), similarity(Half B, Demo))` as Front, and the counterpart as Back.
  5. Barcode center `bc_x` is retained only as a secondary confirmation factor, not the sole decider.

### 5. Decoupled Partition CLI & Deferred Excel Embedding
- **Choice**:
  - `run_zohanubis_pipeline.py --partition <G1|G2|G3|G4|Nyt>`: Processes only the designated folder, saves files to `webshop_front_hd/<partition>/` and `webshop_back_hd/<partition>/`, logs metrics, and exits. Zero Excel modification.
  - `run_zohanubis_pipeline.py --embed-only`: Scans all partition directories, validates deliverable count, and executes a single atomic Excel embedding pass into `Rabuta_master_SKU_categories_zohanubis.xlsx`.

## Risks / Trade-offs

- **[Risk] High CPU load during BiRefNet execution** → **Mitigation**: Limit concurrent worker processes to 4-5 on the 16-core CPU, with single-threaded BLAS/OpenCV (`OPENBLAS_NUM_THREADS=1`) to prevent memory thrashing.
- **[Risk] G1 timeline skips if photographer skipped a row** → **Mitigation**: Validate interpolated SKU names against demo image visual similarity; if similarity < 0.60, stage into quarantine rather than forcing an incorrect match.
- **[Risk] Slower runtime than pure U2Net** → **Mitigation**: U2Net handles ~50% of simple products at 0.8s; BiRefNet handles ~50% at 12s. Average throughput is ~6-7s per SKU, completing a 400-item folder in under 30 minutes.
