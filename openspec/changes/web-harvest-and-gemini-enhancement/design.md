# Technical Design: Web Packshot Harvesting & Gemini Enhancement

## Context

The catalog currently has 722 SKUs flagged for customer reshoot. The existing pipeline in `audit_and_export_reshoot_list.py` uses verified packshots from `output/shopify-zohanubis-image/webshop_front_hd/Front/` to mark items as `PASS`. By establishing an automated harvesting engine that saves verified images directly into this folder under the canonical naming `{barcode}-front.jpg`, existing downstream reporting, Excel generation, and Shopify CSV export tools integrate seamlessly without architectural disruption.

## Goals / Non-Goals

**Goals:**
- Automate multi-tier queries for the 722 reshoot SKUs across OpenFoodFacts, wholesale distributors, and Google Images (deep full-resolution extraction).
- Implement Gemini Vision semantic audit to ensure 100% brand, flavor, and packaging fidelity.
- Standardize approved images to 2048x2048 px square canvases with pure white backgrounds (`#FFFFFF`) and 84% product dimension scaling.
- Implement a candidate retry queue and backtracking mechanism that safely aborts to the reshoot list if validation fails.
- Guarantee production-level sharpness through a 4-layer HD quality pipeline (Bilateral Denoise, Lanczos-4 resampling, Unsharp Masking, Chroma 4:4:4, and post-save Laplacian metrics $\ge 50.0$).
- Automatically re-reconcile and update both Excel deliverables and Shopify CSV exports.

**Non-Goals:**
- Full deep-learning background matting for noisy background scenes (if an image is not already on a studio white/transparent background and cannot be cleanly auto-cropped, it is aborted to reshoot).
- Generative label redraw (no AI hallucination of text/ingredients; only non-destructive super-resolution and unsharp contrast enhancement).

## Decisions

### 1. Multi-Tier Query Orchestration & Google Images Deep Extraction
- **Decision**: Query OpenFoodFacts API first (Tier 1), then distributor search endpoints (Tier 2), and finally Google Images image queries with strict quotes `"{barcode}"` and large size filter `tbs=isz:l` (Tier 3).
- **Deep Extraction Rationale**: When scraping Google Images, ignore small base64/gstatic thumbnails ($150\text{–}200\text{ px}$) and extract original host URLs ($1000\text{–}2500\text{ px}$) from embedded JavaScript payloads (`AF_initDataCallback`).
- **Alternatives Considered**: Using Google thumbnails and attempting massive AI generative upscaling. Rejected because generative upscaling hallucinates non-existent label text and barcode lines.

### 2. Candidate Queue & Backtracking Architecture
- **Decision**: Maintain a queue of up to 3 candidate images per SKU. If Candidate 1 fails Gemini verification or aspect ratio checks, the engine backtracks to Candidate 2, then Candidate 3. If all fail, the engine attempts query mutation (`"{brand}" "{variant}" "{net_qty}"`). If still unresolved, it safely aborts and keeps the SKU in the Reshoot deliverable.
- **Rationale**: Guarantees zero false positives. A false positive on an e-commerce store causes customer disputes; an aborted SKU simply remains in the reshoot list for physical photography.

### 3. Dual-Anchor Validation (Aspect Ratio + Gemini Vision)
- **Decision**: Extract Column W demo thumbnail bytes to establish a ground truth aspect ratio ($W/H$). Discard any candidate whose bounding box aspect ratio deviates by $> 25\%$. Pass surviving candidates to Gemini Vision with a structured JSON schema verifying Brand, Variant, and Net Quantity.
- **Rationale**: Quick programmatic aspect ratio checking eliminates 70% of mismatched candidates (e.g., tall bottles vs flat bags) before spending Gemini API tokens.

### 4. Lightweight Canvas Standardization (2048 x 2048 px)
- **Decision**: Because official distributor packshots are already pre-matted on white or transparent backgrounds, the pipeline detects product bounding boxes via thresholding (RGB $< 248$ or Alpha $> 10$), crops tightly, and composites onto a 2048x2048 white canvas with:
  $$\text{target\_dimension} = 2048 \times 0.84 = 1720\text{ px}$$
- **Rationale**: Avoids unnecessary neural network matting passes that risk trimming thin bottle necks or transparent film packaging.

### 5. 4-Layer High-Definition Quality Enhancement Pipeline
- **Decision**: Enforce a strict multi-stage sharpening and encoding pipeline:
  1. *Artifact suppression*: Bilateral filtering suppresses JPEG blocking artifacts on solid color packaging without blurring edge boundaries.
  2. *Anti-aliased scaling*: Mathematical Lanczos-4 resampling (`Image.Resampling.LANCZOS`) to scale cleanly to $2048 \times 2048\text{ px}$.
  3. *Typography sharpening*: Adaptive Unsharp Masking (`radius=1.2`, `amount=130%`, `threshold=2`) sharpens nutritional facts, ingredient text, and logos.
  4. *Lossless Chroma encoding*: Save with JPEG `quality=95` and `subsampling=0` (Chroma 4:4:4) to eliminate color bleed on red and green packaging graphics.
  5. *Post-save automated inspection*: Re-read file from disk and compute Laplacian blur variance. If score $< 50.0$, the file is automatically purged and the item reverts to the Reshoot list.

### 6. Canonical Output Integration
- **Decision**: Save approved images strictly as `webshop_front_hd/Front/{barcode}-front.jpg`.
- **Rationale**: Matches the exact file discovery pattern of `audit_and_export_reshoot_list.py`, ensuring 100% interoperability with existing Excel and Shopify scripts.

## Risks / Trade-offs

- **[Risk] Search engine rate limits or IP blocks during Tier 3 queries** → *Mitigation*: Cache all search results locally, add random jitter delays (1.5s–3.0s), and prioritize Tier 1 OpenFoodFacts where no rate limits apply.
- **[Risk] Packaging redesigns (New vs Old packaging versions)** → *Mitigation*: The Column W demo image acts as the canonical visual reference; if the color palette or packaging drastically differs, Gemini flags low confidence and defaults to reshoot.
- **[Risk] Low-resolution images blown up to 2048 px appearing blurry** → *Mitigation*: Pre-filter rejects any input $< 600\text{ px}$, and post-save Laplacian gate ($\ge 50.0$) automatically deletes blurry outputs.
