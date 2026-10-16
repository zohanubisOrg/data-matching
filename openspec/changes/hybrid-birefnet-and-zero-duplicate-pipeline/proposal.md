# Proposal

## Why

Execution of the visual catalog pipeline across the 5 source folders (`G1_original`, `G2_original`, `G3_Original`, `G4-original`, `Nyt25.09.26`) revealed two critical failures:
1. **Severe Output Duplication in G1**: A lack of mutual exclusion and sequence awareness caused non-barcode photos (such as `IMG_0006.jpeg`) to be repeatedly matched and output for dozens of consecutive products (e.g. `022392573702_front.jpg` and 50+ other SKUs sharing identical SHA-256 hashes), violating catalog uniqueness.
2. **Detail Loss and Face Misidentification Across All Partitions**: Standard U2Net matting natively operates at only 320x320 px, causing severe edge erosion, blurred packaging typography, and destruction of delicate plastic films, straws, and hanging holes. Concurrently, naive barcode-position splitting (`bc_x >= 0.50`) without Excel Column W ground-truth verification caused frequent front/back inversions.

This change delivers a high-fidelity **Hybrid Matting Architecture** (`birefnet-general-lite` for complex packaging vs `u2net` for standard geometry), enforces a **Zero-Duplicate 1-to-1 Bijective Invariant** with chronological timeline alignment for G1, guarantees **Ground-Truth Front/Back Verification**, decouples per-folder execution, and isolates Excel embedding until all 1,169 target packshots are verified.

## What Changes

- **Strict Bijective 1-to-1 Mapping & Anti-Duplicate Guard**:
  - Enforces that each raw studio photograph (`IMG_xxxx`) is mapped to at most one catalog SKU. Once assigned, a photo is permanently removed from the candidate pool.
  - Implements an Anti-Duplicate Guard at file save time: halts and alarms if an output SHA-256 hash duplicates an already generated packshot in the partition.
  - Replaces blind fallback matching with quarantine staging: unverified or low-confidence SKUs are routed to `quarantine_for_retry/` and `Zohanubis_Missing_SKU_Report.xlsx` rather than being assigned arbitrary duplicate photos.
- **Chronological Sequence Timeline Alignment for G1**:
  - Leverages the strict 1-to-1 chronological shooting order of `G1_original` against catalog rows (`IMG_0002` -> `G1-0001`, `IMG_0003` -> `G1-0002`, ..., `IMG_0006` -> `G1-0005`).
  - Interpolates missing barcodes using immediate sequence neighbors instead of cross-catalog window drift.
- **Ground-Truth Dual-Hero Front/Back Verification**:
  - In dual-view studio shots (G1, G2, G3), splits both halves (A and B) and computes visual cosine embeddings against the Column W demo thumbnail. The half with higher similarity is assigned as Front, while the counterpart is assigned as Back. Eliminates blind dependency on `bc_x`.
- **Hybrid Matting Engine with Dynamic Quality Escalation**:
  - Standardizes high-fidelity neural matting on **`birefnet-general-lite`** (1024x1024 px receptive field) for complex products: transparent films, produce/herbs/vegetables, clear bottles, hanging holes, or any product where U2Net produces hollowing or low solidity (< 0.90).
  - Uses **`u2net`** (0.8s) for standard, high-contrast, opaque geometric packaging (tin cans, solid cardboard cartons) to maximize throughput on 16 CPU cores.
  - Automatically escalates from U2Net to BiRefNet if mask solidity or edge gradient checks fail.
  - Reduces morphological closing kernels from 51px to 5px to eliminate box-corner distortion.
  - Preserves 379 customer pre-made packshots without AI matting.
- **Decoupled Folder-by-Folder Execution & Deferred Excel Embedding**:
  - Provides clean standalone CLI partition runs (`--partition G1`, `--partition G2`, `--partition G3`, `--partition G4`, `--partition Nyt`).
  - Completely decouples image generation from Excel embedding: folder runs only output verified assets to `webshop_front_hd/<partition>/` and `webshop_back_hd/<partition>/`.
  - Introduces a dedicated standalone embedding command (`--embed-only`) invoked only when the user verifies that all 1,169 desired packshots have been produced.

## Capabilities

### New Capabilities
- `catalog-image-quality/hybrid-birefnet-pipeline`: Defines specifications for zero-duplicate bijective photo mapping, chronological sequence alignment, Column W ground-truth front/back orientation, hybrid U2Net/BiRefNet-general-lite matting with auto-escalation, partitioned folder execution, and deferred batch Excel embedding.

### Modified Capabilities
*(None)*

## Impact

- **Affected Code**: Modifies `src/product_mapper/zohanubis/` (`matting_engine.py`, `hero_cropper.py`, `front_matcher.py`, `reconciler.py`, `studio_standardizer.py`) and orchestrators `scripts/run_zohanubis_pipeline.py` and partition runners.
- **Deliverables**: Partitioned outputs under `output/shopify-zohanubis-image/webshop_front_hd/` and `webshop_back_hd/`, quarantine ledger, and deferred master Excel embedding.
- **Dependencies**: Uses verified local libraries (`rembg` 2.0.85 with `birefnet-general-lite` & `u2net`, `torchvision`, `cv2`, `PIL`, `openpyxl`, `zxingcpp`). Zero new package installations required.
