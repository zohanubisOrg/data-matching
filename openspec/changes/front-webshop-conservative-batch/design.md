# Design

## Context

See proposal.md for why this delivery path exists. Observed on 2026-10-15, before implementation:

- Workbook `Rabuta_master_SKU_categories_ingredients_final.xlsx`, sheet `Audit front-v3 vs back-v2`, header row 3. Column A is Barcode, E is Record ID, W is the customer front, X is the webshop front, Y is the back. A read-only pass saw 1350 non-empty barcodes from row 4 and a banner that says 1.351 products. The runner must count rows itself.
- Five original folders are the eligible inputs. A file walk saw G1 467 JPEG including 12 paths under a removed-not-in-excel directory, G2 413 JPEG, G3 295 JPEG plus 167 HEIC, G4 119 HEIC, Nyt 14 JPEG plus 109 HEIC. Counts are inventory facts, not acceptance totals.
- `render_verified_packshot` feathers the mask 1.5 px inward, rejects a package that touches the frame, and rejects any scale above 1. That protects detail only after a human polygon exists. The reviewed-polygon wave published 64 fronts and left the rest in review.
- `separate_joined_packages` shifts the seam 8% into the package. `split_sides` decides the cut on a 900 px preview. Both can shave labels. `packshot_front` now requires an external mask, so it is not a fast production path.
- Local runtime previously had CPU-only PyTorch and no SAM checkpoint. This design does not depend on a new segmentation model.
- Column Y from `back-v2` stays. Column W stays. `front-v3` is evidence of the rejected result, not an input and not the write target.

## Goals / Non-Goals

**Goals:**

- Finish a resumable ledger and validate a 48-case, human-labelled Gemini pilot before catalog-scale enforcement.
- Prefer a slightly larger white margin over any cut into the package.
- Keep one publishing route for the new files and one embed route for column X.

**Non-Goals:**

- Retracing polygons by hand for the whole catalog.
- Installing or benchmarking SAM in this delivery.
- Upscaling, multi-pass sharpen, Shopify upload, or editing product text.
- Replacing `back-v2` or repainting column W.

## Decisions

### 1. New output folder, old folder frozen

Write accepted files to `output/catalog_pairs/tagged/front-v5/{barcode}-front.jpg`. Do not write `front-v3` in this change. A later replacement of a live folder can only copy a file whose ledger state is accepted and whose hash matches the new file. Alternative considered: overwrite `front-v3` in place. Rejected because a bad batch would destroy the only current embed source before the workbook copy is verified.

### 2. Index once, then shard by ledger row

Stage A is a single indexer. It decodes each original once with the existing orientation-safe loader, skips any path containing `removed_not_in_excel`, reads retail barcodes, and writes an index with path, SHA-256, oriented size, barcode, and rotation. Stage B matches that index to the workbook into `ledger.jsonl`. Shadow pilot mode accepts only a confirmed 48-case manifest: 12 regression cases, 12 positive controls and 24 difficult cases stratified over six package groups. Catalog scope is available only in enforce mode with approval bound to a passing benchmark. Resume requires current source/reference/config fingerprints, candidate inventory, QA evidence and output SHA-256. Workers return candidates to the parent, which owns QA, ledger/progress and promotion; shard routes share the same coordinator and 200-request pilot budget.

Alternative considered: four independent workers scanning shared folders and writing disjoint output files. Rejected because HEIC decode and barcode reads would be repeated and writers could race on a barcode or ledger state.

### 3. Front selection without a destructive split

The retail barcode locates a subject; it does not decide which face is the front. When two or more subjects are present, compare every plausible subject to the customer front in column W and, when available, the back reference in column Y. Select only a unique front winner that clears the configured absolute score and winner-margin thresholds. Equal or weak scores, missing or unreliable references, and a frame with only back/ingredient faces return to review. Never choose by left/right/near/far position, barcode side alone, or candidate iteration order. A barcode printed on the selected package is allowed. Never average or merge photos.

The frequent failure cases remain regression gates: upright bottle clusters split only through a confirmed background gap; a single rotated package, including a tray of cups, is not cut on its long axis; three-in-a-row selects the face matching column W even when it is in the middle; if no unique face matches, block the row. A barcode on the middle subject does not determine front identity. Two same-color bags may be separated only at a confirmed package boundary, never at a label edge or crease. Single-face food keeps the bag, seal, film and tray. A produce pile remains one unit. A carton fold alone is not a cut. A photo showing only the back or ingredients is never accepted as a front.

### 4. Keep complete packaging and a bounded retained envelope

Track the complete product mask/bounding box separately from the optional retained envelope. Keep every known package pixel, including clear film, windows, seals, caps, trays and pale protrusions. The envelope may retain a rectangular area of source background to protect transparent packaging; it is capped by the 18% search allowance and by the available 2400 canvas margin. Q1 measures whiteness outside the envelope, while Q2/Q3 independently validate package coverage and any retained background. Enlarging the envelope cannot hide a product, clipping or table defect. Source-edge contact is allowed only for verified background pixels; if product boundary evidence touches or is uncertain at the image edge, reject the candidate. Do not erase mask rows or columns to make that check pass.

Alternative considered: dilate a tight mask and knock pale pixels out to white. Rejected because it removed the clear rim and the seeds visible through the film.

### 5. One resample, product geometry controls scale

The complete product bbox (not the padded envelope) has a target long side of 2064 ± 2 px on the 2400 canvas and at least 48 px of canvas margin. Derive one isotropic scale from that product bbox; scale must be <=1 and aspect-ratio error <=0.5%. The retained envelope must fit the remaining margin without shrinking the product; if it cannot, return the row for review. Render RGB from the original through one Lanczos downsample onto white. JPEG quality 95, 4:4:4, once. No sharpness or contrast pass. `render_verified_packshot` may be reused only if its inward feather is removed or bypassed for this path; an inward feather fails this decision.

### 6. Q1–Q6 acceptance is distinct from batch release

The shared evaluator records explicit `PASS`, `REVIEW` or `FAIL` evidence for each Q1–Q6 gate. Python owns measurable canvas, saved-file, scale and identity evidence. Gemini owns semantic judgements on package completeness, unit count, front identity and external background by comparing the immutable oriented source, candidate, product name, W and Y. Gemini never invents pixel coverage or other numeric measurements. If an independently reviewed mask exists, Q2/Q3 retain their numeric checks; if it does not, schema-validated semantic evidence bound to the exact source/output/reference hashes may supply those judgements. Conflicting references or uncertain boundaries remain `REVIEW`. `ACCEPTED` requires all six gates to pass for current source, references, model/prompt/schema/configuration fingerprint and output hash. Curated `apptance` rows remain skipped. Batch release remains a later decision bound to the exact accepted set, hashes, grouped evaluation and stratified visual review. No workbook is embedded without that release record.

### 7. Workbooks

After validating a release record, copy the customer workbook to a run-specific output path. Preflight exact row/barcode/Record ID mapping and require every accepted row to have one X anchor. Replace only column X drawings from released `front-v5` files, and rewrite drawing ids so they are unique and sequential. Compare column W and column Y image bytes to the source workbook before and after. Write to a temporary workbook, verify the exact X set and protected W/Y bytes, then finalize. On failure, keep the source and any previous deliverable unchanged. Write the reshoot workbook for missing and incomplete-edge rows.

### 8. Stage boundaries and shared writes

The runner owns index, ledger and progress writes. Process-pool workers return per-row candidates; only the runner appends them and applies QA/promotion. Identity conflicts are never rendered. Index, pilot/render, benchmark, report, promote, audit and embed are explicit stages; default invocation is read-only audit. Embed requires a release record bound to the exact accepted set and hashes. Pilot render is capped at 48 confirmed cases. Catalog scope requires enforce mode, a passing benchmark approval and an explicit shared budget id.

### 9. Gemini QA, bounded repair and promotion

Workers write immutable per-attempt candidates under the run directory and never write to the delivery folder or claim `ACCEPTED`. The parent sends every candidate that clears hard Python gates to the configured Gemini Pro model, passing source, candidate, W/Y roles and product identity as separate labelled image parts with a Pydantic response schema. Persist the returned model version, prompt/schema versions, usage, exact input hashes and structured verdict. One retry is allowed for a transient API failure; timeout, invalid JSON, refusal, authorization error, unavailable model or budget exhaustion yields `REVIEW`. The pilot's shared cross-process budget is 200 requests and no more than two requests may be in flight.

The system permits at most three renders per barcode, always from immutable originals. Gemini may return only allowlisted repair recommendations; Python selects the recipe and available alternate source. A repair is saved as a new attempt and both QA layers run again. Ambiguous boundaries, unreliable W/Y, missing source evidence, or no safe repair recipe end as `REVIEW`. A deterministic hard Python failure cannot be overridden by Gemini. Only a final all-gates PASS can be promoted, atomically and under a per-barcode lock. Back up an existing non-curated destination with its hash before replacement. If a live writer or unexpected hash change is detected, skip promotion and report conflict. A reviewed pilot-approval manifest bound to its benchmark, model, prompt/schema and run fingerprint is required before enforce-mode auto-promotion.

### 10. Versioned quality improvement

Each pilot and later benchmark uses frozen development and holdout case manifests with source, reference, candidate and human-label hashes. Include confirmed accepted `apptance` outputs as positive cases without reprocessing them, the reviewed front-v5 failures as negative cases, and stratified ambiguous packaging cases. Keep provisional agent labels marked unverified until confirmed. Report confusion counts by reason and package group, repair success and API usage. A model, prompt or algorithm candidate cannot become the active version unless no known critical case passes and the version improves a predeclared quality/yield/cost metric on the development set without a holdout regression. Human labels are stored separately from model predictions; the loop never modifies code, prompts or thresholds automatically.

## Risks / Trade-offs

- [Gap test rejects a real front that sits tight against the back] → Row goes to reshoot instead of a shaved label. That is the accepted miss.
- [White or clear packaging blends into the background] → Core-coverage gate sends the row to incomplete-edge rather than a hollow logo.
- [Pilot labels or API budget are incomplete] → Preserve queued candidates as REVIEW; require a new shared budget id to resume a later bounded catalog batch.
- [Barcode missed on a good front-only photo] → Matcher can still attach a no-barcode frame only when the file was already filtered to catalog products and a second signal agrees (manifest lead or filename). Otherwise the row stays in reshoot. Do not guess from a similar package.
- [Excel drawing XML breaks the workbook] → Embed is a copy, with a W/Y byte check and sequential drawing ids. Failure leaves the customer file intact.

## Migration Plan

1. Snapshot nothing inside `front-v3` or `back-v2`; do not modify them.
2. Build the source index and validate all 48 confirmed labels against workbook identities and eligible originals.
3. Run the shadow pilot under its shared 200-request cap. Review its gallery, reason queue and package-group benchmark.
4. Record approval against the passing benchmark hash. Then use enforce scope to QA/promote passing images; shards use a common budget id.
5. Embed only after independent release validation; write the reshoot workbook within the run directory.
6. Rollback uses each promotion's hash-verified backup. Customer originals, `front-v3`, and `back-v2` are not part of rollback.

## Open Questions

The reviewed 48-case labels and a completed Gemini pilot are not yet available. Catalog enforce remains unavailable until they are supplied and the benchmark meets its criteria. Product target size, envelope bounds, output folder, case count and pilot request cap are locked above.
