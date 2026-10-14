# Rabuta Package Preservation Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task by task.

**Goal:** Reprocess verified authentic front photographs without deleting packaging, and stop unverified outputs from passing QA.

**Architecture:** A shared renderer consumes an independently verified full-package mask. A JSONL runner binds each annotation to source hash, oriented dimensions, Record ID and barcode, then renders to a separate review directory. Existing healing entry points require the same mask rather than accepting a logo contour.

**Tech Stack:** Existing Python, Pillow, NumPy, OpenCV, pytest; no new model or dependency.

**Spec:** `scratch/Rabuta_Background_Algorithm_Review_2026-10-14.md`, accepted by user on 2026-10-14.

## Global Constraints

- Preserve workbook W and delivery files. Write candidates separately; no upload, embedding or release.
- Canvas 2400 x 2400, white; scale uniformly; report upscaling as a review limitation.
- Preserve original RGB inside verified boundary; no colour deletion, enhancement or generated text.
- Barcode alone neither selects a face nor grants PASS. Record ID and barcode are mandatory together.
- Missing source blocks; uncertain identity, face, boundary, film matting or collision requires review.

## Review Focus

- White/beige printed packaging must remain intact, even when a model returns only its logo.
- A native preview cannot silently become a high quality source.
- Incorrect mask size, multiple objects, holes or border-clipped sources must be rejected.
- Barcode collisions must block both records before saving.
- Embedded thumbnails must never yield full-resolution QA PASS.

### Task 1: Shared safe renderer

Files: `src/product_mapper/vision/package_packshot.py`, `smart_packshot.py`, `tests/test_package_packshot.py`.

Interface: `render_verified_packshot(image, mask, target_side=2400, shape='auto') -> (Image, metrics)`; `mask_from_polygon(size, points)`; `UnverifiedPackageError`.

- [ ] Write regressions for interior preservation, logo coverage rejection, mask holes/multiple objects, clipped/low-resolution source, fixed canvas and adaptive aspect ratio.
- [ ] Run RED, implement, run GREEN.
- [ ] Make legacy smart renderer require independent package mask; remove inferred-contour restoration and full-frame fallback.

### Task 2: Identity-bound queue runner

Files: `scripts/reprocess_rabuta_verified.py`, `tests/test_rabuta_reprocess.py`.

Interface: `run_reprocessing(records, annotations, output_dir, originals_dir) -> results` and CLI `--records --annotations --output-dir`.

- [ ] Test collision blocking, source hash mismatch, missing source, wrong face, real render/provenance and prevention of delivery overwrites.
- [ ] Run RED, implement, run GREEN. Inventory source candidates for all 375 queued rows without trusting audit source flags.
- [ ] Save source-sized mask, overlay, candidate and JSONL with review statuses, source/output hashes and layout metrics.

### Task 3: Retire unsafe healing / QA and verify pilot

Files: `scripts/studio_front_v3_extractor.py`, `heal_all_257_fronts.py`, `heal_webshop_quality_fronts.py`, `qa_row_by_row.py`, `qa_audit_delivery.py`, pilot manifest and documentation.

- [ ] Test thumbnail never PASS and barcode exceptions not automatic defects.
- [ ] Delegate healing render helpers to shared engine; disable destructive legacy CLI entry points with migration message.
- [ ] Replace thumbnail PASS with NOT_VERIFIED or NEEDS_MANUAL_REVIEW; remove unconditional delivery acceptance.
- [ ] Annotate available representative authentic sources; render, inspect before/after and record remaining blockers.
- [ ] Run full pytest and compile checks; verify delivery hashes unchanged.

## Execution ledger

- Baseline: 41 tests passed (Python 3.13). Existing extensive user changes are preserved; work in the current checkout because these pipeline files are untracked and absent from HEAD.
- User authorized implementation of the accepted design; execute inline, no additional approval gate or commits.
- Task 1 complete: 12 mask/layout/helper regressions; RED observed before implementation, GREEN after. Legacy renderer without reviewed mask fails closed.
- Task 2 complete: identity/source/provenance regressions; native-source inventory and four real candidate renders. Whole-workbook collision scope checked again with a one-row CLI selection.
- Task 3 complete for pipeline implementation: preview no longer PASS; delivery all-cell/W hash checks; unsafe fallback helper and connected CLI retired. Final suite 74/74; compile checks succeeded.
- Final review findings fixed with RED→GREEN: subset collision, unsafe OFF padding bypass, rotated mask provenance. No deferred review findings.
- Ruling: keep changes in current checkout, without commits — preserve pre-existing extensive changes and untracked source; cost is no isolated committed change package.
- Ruling: require independent boundary and stop legacy automatic healing — accepted preservation policy takes precedence over old barcode/contour shortcuts; cost is older unannotated callers now require migration.
- Ruling: generate four complete-source pilot candidates rather than claim a 20–30 case benchmark — several priority photos are clipped, back-only or unresolved; cost is limited coverage across packaging types, with 371 queue records unresolved.
- Source workbook and delivery unchanged: 0 cell differences, W1349 byte-identical; delivery SHA c8a58d9a294799cd4bb12c13bf32109ef8681d096875dd84ddca23d947c1eb11.
- Pilot run: 4 REPROCESSED_NEEDS_REVIEW, 230 NEEDS_MANUAL_REVIEW, 139 BLOCKED_NEEDS_SOURCE, 2 BLOCKED_IDENTITY_CONFLICT. No catalog QA PASS, no X/Y embedding or upload.
