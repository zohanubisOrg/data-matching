# Design: Native-source rebuild for the full Rabuta catalog

## Context

See proposal.md for scope and motivation. The five supplied critical files are regression examples, not a repair queue. Retain the existing change directory name only for link compatibility.

Read-only observations on 2026-10-15:
- Five original folders contain 1,584 image files, including 395 HEIC. 1,570 have a stored long side at least 3,000 px; 14 have 2,560 px. File dimensions do not establish focus, product coverage or SKU count.
- G1 includes 12 files under _removed_not_in_excel; quarantine from automatic eligibility pending identity reconciliation, without deleting them.
- front-v3 has 1,352 images, 1,298 at 2400 square. This is not an authoritative row denominator.
- The old manifest has 1,151 existing local references, six missing local paths and 34 web references. Manifests disagree on rotation/front status; use them as matching leads.
- Existing remediation enlarges thumbnails and can paste entire rectangular photos. Its low-Laplacian branch incorrectly identifies damaged masks as user-curated blur. Later loops re-encode live JPEGs and use saturated aggregate scores.
- package_packshot.py and publish_rabuta_fronts.py have useful source/mask/publication safeguards; reuse and extend these rather than introduce another live writer.

Evidence: output/catalog_pairs/critical_front_v3_cases_20261015.json and its Markdown companion contain hashes and visual observations, not accepted masks or full-resolution sharpness certification.

## Goals / Non-Goals

Goals: complete catalog reconciliation, immutable native sources, correct complete retail units, one publishing route and per-record decisions.

Non-goals: invent missing packaging/text, assume large photos are sharp, use lookalikes, repeat ten JPEG enhancements, alter originals/W/Y/back-v2, delete sources or upload Shopify products.

## Decisions

### 1. Resolve the catalog denominator and identity first

Use Rabuta_master_final_Delivery_Embedded.xlsx as the declared catalog authority; verify existence, sheet/columns and identities against audit workbooks before publishing. Resolve discrepancies explicitly; do not choose authority by newest filename or largest row count.

Processing key is (record_id, excel_row, barcode-as-text), retaining leading zeroes. Reconcile every row against current fronts, all five original folders and previous QA. Report missing sources, conflicts, verified existing images and unresolved records. The five examples and old 375-row queue never filter full-run eligibility. P3/PASSED_PERFECT give no exemption.

Retain barcode filenames only after collision reconciliation. Different products sharing a barcode cannot overwrite each other. Duplicate workbook rows genuinely representing one SKU can share an accepted image if explicitly reconciled.

### 2. Inventory and match immutable originals

Record full path, SHA-256, dataset, native dimensions, EXIF, format, color profile and exclusion status. Deduplicate by hash without deleting files; retain all views as candidates. Decode full-resolution primary HEIC, normalize orientation exactly once, retain source-coordinate transforms, and use a color-managed sRGB working image without an intermediate thumbnail JPEG.

Match with manifest leads, barcode detections, W references and visual/OCR packaging evidence. Barcode is neither automatic front proof nor automatic rejection. Ambiguity requires identity/front review, not silent filename matching.

### 3. Select the whole retail instance before segmentation

Detect all instances/faces; photos can contain one, two, three or more views. Do not assume equal halves, front-left ordering or a gap between products.

For touching bottles, use an instance-specific box and positive points across cap, shoulders, label, sides and base; negative points exclude adjacent bottles/background. A seam is only a hint, never a destructive rectangular cut. A connected mask is not proof of one retail unit.

Benchmark a promptable instance model such as SAM 2.1 against the reviewed-mask workflow; retain manual correction when needed. Pin implementation/checkpoint after environment and benchmark verification; a model name grants no QA acceptance.

The target includes all retail packaging: tray plus film plus food, sealed bag plus contents/label/margins, or bottle plus cap/body/base. Graphics or food inside a tray are not independently selectable packshot targets.

### 4. Refine boundaries on native source pixels

Remap a coarse inference MASK to native coordinates and refine uncertain boundaries there. Never use the low-resolution inference RGB as production source. Use trimap/matting for film/glass; benchmark a method such as ViTMatte rather than uniformly feather every edge.

Preserve opaque interior source pixels and label detail. White packaging remains foreground. Do not erase brown food, sauce or amber glass with global HSV/brightness rules. Distinguish real openings from segmentation holes; contour filling cannot prove the extent or identity of a package.

Merged-neighbor masks return to instance selection. Clipped or occluded outlines require another photograph; no adequate alternate means BLOCKED_NEEDS_SOURCE. Potentially adequate sources with uncertain boundaries use NEEDS_MASK_REVIEW. Never generate hidden caps, wrappers, missing sides, label text or artwork.

### 5. Gate native product detail and render once

Measure native package ROI and local label readability, not global photo megapixels. Rank candidates by verified identity/face, complete coverage, focus, glare and native product pixels.

For canvas C=2400 and occupancy o, requested scale=C*o/max(native_width,native_height). Require scale<=1. Initial occupancy values: tall .88, horizontal .89, square .84, irregular .83; record and visually validate the choice. At .85 occupancy the product long side needs 2040 native pixels. Layout numbers are not proof of focus.

If the desired layout needs enlargement, select another source or mark BLOCKED_NEEDS_SOURCE; never silently stretch, crop or invent detail. Glare-clipped or unfocused sources fail even when dimensions suffice.

Render each candidate from its immutable source, combining required geometry into one final resampling where possible. Save a lossless master; encode final high-quality, full-chroma JPEG once. Optional conservative denoise/sharpen must preserve local readability/color and pass halo/clipping checks against source. Never repeatedly enhance previous output.

### 6. Separate QA, provenance and publication states

States include INDEXED, NEEDS_IDENTITY_REVIEW, NEEDS_FRONT_REVIEW, NEEDS_MASK_REVIEW, BLOCKED_NEEDS_SOURCE, CANDIDATE_NEEDS_QA, VERIFIED_EXISTING, READY_TO_PUBLISH, PUBLISHED and FAILED. Publication and visual acceptance are separate fields. Record reasons and deciding evidence.

Every accepted image requires exact identity/packaging, intended front or documented single-face exception, one complete unit, no neighbor contamination, correct orientation, preserved label/interior detail, adequate matting/background, genuine native resolution/focus and compliant layout without invention/upscale. Compare source, overlay and output at native/100% zoom. W is identity evidence, not full-resolution quality evidence. OCR/Laplacian flag review; neither aggregate sharpness nor a white 8px border proves PASS. Store per-image reviewer/evidence.

Protect user-selected images using explicit selection provenance, not blur or geometry heuristics. All such records still receive QA; build alternatives separately and retain originals/framing pending explicit replacement resolution. Preserve already verified outputs when they meet every gate.

### 7. Benchmark, then cover the full catalog

Pilot 30-50 representative SKUs plus held-out cases. Include all five user examples, earlier Udon/seaweed/Dagupan/Ajinomoto failures, actual three-touching-bottle photos, touching bags, glass, white trays/caps, transparent film, dark/brown packaging, single-face labels, insufficient sources and already-good images.

No critical identity/front/package/neighbor errors may remain among accepted pilot candidates. Insufficient-source cases need honest blocking, not false acceptance. A correctly blocked clipped-source case satisfies the regression behavior but is not image QA PASS. The five examples alone do not prove three-touching-bottle separation; add a dedicated fixture.

After pilot acceptance, process every authoritative catalog row in resumable batches keyed by source hash, identity, mask, config and model version. Changed inputs invalidate prior candidates. Resume only verified results; never re-encode live JPEGs. Final report accounts for every row with approved/preserved, blocked, review or failed disposition.

### 8. One guarded publisher and a separate comparison workbook

Canonical delivery remains front-v3. Candidate/mask/QA/rollback files are technical evidence, not another final catalog or HD_Studio_Front_Images workflow. Reuse the guarded publisher and retire/block direct live saves in remediation scripts. Snapshot before publishing, compare expected live hashes, stage validated bytes, atomically replace individual files and journal batch rollback. Refuse changed user files.

Create a separate comparison workbook from the authoritative workbook, updating accepted X images only. Preserve original W/Y embedded media bytes, anchors and product fields; verify invariants before/after. Do not rebuild W/Y using 115px thumbnails or silently replace original/delivery workbooks. Validate drawing relationships and unique nonvisual IDs. Thumbnails aid navigation, never replace full-resolution deliverables/QA. A locked workbook yields pending/failed export, not success or a different authority.

## Risks / Trade-offs

- [Touching or occluded packages] -> instance-specific review and alternate views; never reconstruct hidden geometry.
- [White/clear retail packaging] -> full-unit definition, native mask review and material-aware matting.
- [Large but blurred source] -> package/text-level checks and alternate capture or blocked status.
- [Stale mappings/collisions] -> workbook identity reconciliation before publication.
- [GPU/model/dependency limits] -> actual-environment benchmark, reviewed-mask/manual fallback, unchanged quality gates.
- [Self-scoring bias] -> per-image visual evidence with explicit unresolved dispositions.

## Implementation update — 2026-10-15

- Confirmed `package_packshot.py` is the shared rendering boundary used by the verified reprocessor, studio extractor and existing repair scripts; `publish_rabuta_fronts.py` is the guarded live writer. The shared renderer now blocks scales above 1.0. The focused renderer, reprocessor and publisher suite passes 45 tests.
- Local runtime has Ultralytics 8.4.176 and CPU-only PyTorch; SAM/SAM2 packages and checkpoints were not present. A small YOLO11n-seg benchmark found duplicate/overlapping bottle detections on the three-touching-bottle fixture, no detections on one critical package photo, and unrelated table/book classes on other package photos. Those proposals were not used for production masks.
- After user acceptance of the 47-record pilot, the authoritative 1,351-row ledger was run using all 70 exact-source-hash reviewed polygon annotations. The current run produced 64 full-resolution candidates; six annotations were blocked because the native package ROI would require enlargement. Remaining rows retain explicit review, missing-source, or identity-conflict states. All candidates remain unaccepted pending visual QA.
- The initial run input carried stale artifact paths from an earlier run. A regression test exposed the leak; the runner now clears previous candidate provenance before each row is processed. A clean second run has no stale output paths: 64 result rows have outputs, 0 other rows do.
- Current `front-v3` still matches its pre-run backup manifest exactly. No candidate has been published. Automatic instance selection, local focus/readability gates, resumable checkpoints, publication and comparison-workbook export remain open.

## Migration Plan

1. Freeze baselines and reconcile the entire catalog/source inventory.
2. Implement/reuse candidate rendering and one publisher with regression tests; keep live sources/fronts unchanged during development.
3. Run representative and held-out pilot; select parameters from observed quality.
4. Process all rows; preserve verified/user-selected assets and record blocked/review cases.
5. Publish only accepted replacements, then export the comparison workbook and reconcile every row.
6. Roll back failed batches only through the run journal and expected hashes, preserving unrelated edits and all sources.
