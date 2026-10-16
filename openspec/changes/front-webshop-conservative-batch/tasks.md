# Tasks

## 1. Ledger

- [x] 1.1 Add a read-only workbook reader for `Rabuta_master_SKU_categories_ingredients_final.xlsx` that preserves barcode text, Excel row, and Record ID, and verify a test fails on a duplicate barcode instead of keeping one row.
- [x] 1.2 Index the five original folders into `output/catalog_pairs/front-v5-run/index.jsonl`, skip paths containing `removed_not_in_excel`, and verify the index records path, SHA-256, oriented size, barcode, and rotation without reading `front-v3` or `back-v2`.
- [x] 1.3 Write `ledger.jsonl` with one state per barcode row and verify the ledger count equals the workbook barcode count, including conflict rows and rows with no source.

## 2. Conservative front render

- [x] 2.1 Reopened after QA audit: a gap and barcode locate subjects but do not prove front identity. Require a unique match to W or independent reviewed evidence; equal scores and back-only frames must fail. Selector now enforces absolute score and runner-up margin; barcode-only multi-subject results return QA_RETURN.
- [x] 2.2 Preserve clear film and the rectangular background envelope. Historical check only: validate the new bounded-envelope Q1/Q3 policy before relying on this task.
- [x] 2.3 Reopened after QA audit: compute geometry from complete product bbox, enforce scale <=1, 2064±2 px product side, >=48 px margin and one resample. Strict renderer derives scale from the product mask, rejects native sides below 2064, and clamps optional envelope without scaling the product down; strict geometry tests cover target and undersized cases.
- [x] 2.4 Bypass or remove the 1.5 px inward feather in the shared renderer for this path, and verify existing publisher tests still pass and a new test shows edge pixels of the package core survive.
- [ ] 2.5 Verify all named source-photo hard cases without positional selection. A three-in-row front requires unique W evidence even when it is in the middle; barcode position cannot resolve a tie. Single rotated packs, bags, produce piles and carton folds remain intact or go to review.
- [x] 2.6 Reopened after QA audit: separate the structured Q1–Q6 acceptance gates from coarse `output_is_clean`; fixtures with wrong face, clipped packaging, or a second unit must fail the correct gate. Evaluator has individual pass/fail fixtures; worker will not use the coarse checker as acceptance evidence.
- [ ] 2.7 Separate same-color bags only at a confirmed boundary. If no unique face matches or the candidate is a text panel, send to review rather than infer from barcode distance.

## 3. First batch and subagents

- [x] 3.1 Add an explicit render stage capped at 150 catalog rows; verify a single current state per row and write only under a new run directory. CLI defaults to read-only audit and requires a new isolated run id for index/render; render is capped at 150 candidate rows.
- [ ] 3.2 Emit a labeled first-batch contact sheet and stop. Continue only after a review record binds those exact rows and hashes and records zero critical defects.
- [ ] 3.3 Keep process-pool workers on disjoint row jobs; the parent alone writes ledger/progress. Verify unique output barcodes and unchanged `front-v3`/`back-v2` hashes.

## 4. Workbooks

- [ ] 4.1 Write `output/catalog_pairs/Rabuta_customer_reshoot.xlsx` from rows in `CUSTOMER_RESHOOT` and `BLOCKED_INCOMPLETE_EDGE`, including Excel row, barcode, Record ID, product name, and reason, and verify none of those barcodes have an accepted `front-v5` file.
- [ ] 4.2 Write a run-specific workbook only after release validation. Replace X using the exact hash-bound release set; fail for a missing X anchor. Verify exact X rows, W/Y bytes and unique sequential drawing ids before finalizing the temporary copy.
- [ ] 4.3 Confirm the customer workbook path was not modified, and verify its SHA-256 is unchanged from the hash taken in task 1.1.

## 5. Full-catalog reconciliation

- [ ] 5.1 Join ledger, shard JSONL, `front-v5` files, the embedded copy, and the reshoot workbook, and verify every barcode row is in exactly one of accepted, reshoot, or identity-conflict, with no accepted row left out of column X.

## 6. Quality criteria and coverage

- [x] 6.1 Label a stratified sample of 1000 originals (`front-v5-run/coverage/labels_part_*.jsonl`) with package group, subject count, layout, front position, and hard attributes, and verify the merged label file has exactly one record per sampled id.
- [x] 6.2 Implement gates Q1–Q6 as separate pass/fail checks with the starting thresholds in the spec, and verify each gate has a passing and a failing fixture.
- [ ] 6.3 Implement Q4 against W/Y plus independent visual evidence fallback; ambiguous or missing evidence is review. Verify labeled front identity with zero wrong-face accepts, without treating position labels as inference rules.
- [ ] 6.4 Run the full pipeline on the labeled sample, write a coverage report of pass rate and failure counts per group and per gate, and verify no group has a critical-defect accept before a catalog batch is started.
- [ ] 6.5 After a catalog batch, draw at least 93 accepted outputs stratified by group for visual review, and verify the batch is released only with 0 critical defects and at most 1 minor defect.

## 7. Gemini semantic QA and controlled improvement

- [x] 7.1 Add regression coverage for missing/malformed QA manifests and allowlisted source-aligned mask loading; restore `_load_quality_evidence` and bind its manifest/mask hashes into resume fingerprints.
- [x] 7.2 Change workers to write immutable candidates only under the run directory; remove upscale fallback and prevent workers/coarse `output_is_clean` from assigning `ACCEPTED` or writing directly to `front-v5`.
- [x] 7.3 Add typed Gemini request/response adapter pinned to `gemini-3.1-pro-preview`, with labelled original/candidate/W/Y inputs, Pydantic schema, prompt/schema versions, exact input cache key and recorded returned model version/usage.
- [x] 7.4 Add shared durable 200-request budget and cross-process concurrency limit of two, counting all retries/detail calls; transient retry at most once, SDK automatic retry disabled, every API/schema/refusal/error outcome REVIEW.
- [x] 7.5 Update Q1–Q6 evaluation to combine deterministic Python evidence with Gemini semantic evidence, preserving measurements only when measured and returning FAIL or REVIEW per criterion; no model override of Python hard gates.
- [ ] 7.6 Add parent-owned orchestrator shared by main and all shard routes: render at most three candidates/barcode from immutable originals, allow two fixed repair rounds, rerun both gates each time, and preserve per-attempt evidence. Current retries only select another immutable source for allowlisted repair requests; boundary re-segmentation recipes still need implementation and review.
- [x] 7.7 Add locked, atomic per-barcode promotion after all current gates pass; preserve rollback hash, skip immutable `apptance`, abort on active writer/hash conflict and retain release-only workbook embedding.
- [x] 7.8 Add shadow-pilot, approval, enforce, benchmark and report CLI behavior. Pilot has at most 48 labeled cases (12 reviewed failures, 12 confirmed positives, 24 stratified difficult cases), 200 API request maximum and no default global promotion before recorded approval.
- [ ] 7.9 Freeze human labels, development/holdout manifests, model/prompt/algorithm identifiers and package-group reports; demonstrate no known critical false accepts before enabling an upgrade or enforce policy.
- [ ] 7.10 Verify main/shard/resume/release/embed routes share the gate; run unit suite and a bounded pilot only after all manual labels are confirmed; do not start a full-catalog run or modify/replace the customer workbook.
