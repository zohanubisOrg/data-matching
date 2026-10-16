# Front-v5 Quality Acceptance Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute sequentially unless the user later explicitly authorizes delegation.

**Goal:** Fix the six audited acceptance defects so that every accepted front has reproducible Q1–Q6 evidence, and no workbook is exported before the batch has passed visual release review.

**Architecture:** Keep the existing indexer, selector, renderer, ledger and Excel embedder. Add one focused quality module shared by rendering, resume validation and final export. Bind reusable results and release decisions to immutable inputs, the implementation/configuration fingerprint and output hashes; a folder name or an old progress entry is insufficient.

**Tech Stack:** Existing Python, Pillow, NumPy, OpenCV, zxing-cpp, pillow-heif, openpyxl and pytest. No new image model, service or framework.

**Spec:** Existing planning references under `openspec/changes/front-webshop-conservative-batch/`: `proposal.md`, `design.md`, `tasks.md`, and `specs/catalog-image-quality/conservative-front-batch/spec.md`. This document records the audit remediation decisions; reconcile the existing artifacts in Task 1 before implementation. Do not create another OpenSpec change or introduce Spec Kit.

## Handoff and authorization

- User instruction on 2026-10-16: prepare the fix plan and STOP so the user can switch models.
- The user has now authorized implementation of this plan. Preserve current untracked implementation files and all other work. Do not commit, push or upload.
- A legacy `scripts/run_front_v5_batch.py` process was observed running during implementation and holding `front-v5-run/progress.jsonl` open. It later exited; the old run was only inspected read-only and hashed afterward. Do not reuse its old acceptance states as current Q1–Q6 evidence or write into its output paths. Do not start a second production batch or embed a workbook in this plan execution.
- This is one ordered native plan. Do not spawn agents solely because older design text mentions four render workers/subagents. Process-pool execution in the existing script is distinct from agent delegation.
- Existing checked task boxes are historical implementation claims, not proof that the revised acceptance contract has passed.

## Audit baseline, observed in the preceding turn

| Evidence | Observation |
| --- | --- |
| Catalog ledger | 1,350 rows: 671 ACCEPTED, 430 CUSTOMER_RESHOOT, 150 BLOCKED_INCOMPLETE_EDGE, 97 QA_RETURN, 2 BLOCKED_IDENTITY |
| Recheck all 671 accepted files with current `output_is_clean` | 411 pass; 260 fail: 150 table/cardboard, 52 strip, 44 second-product, 14 canvas-size |
| Acceptance origin | 412 renderer results and 259 `pre-approved from apptance`; current QA rejects 82 and 178 respectively |
| Progress log | 14 entries with recorded scale greater than 1; do not equate historical entries with a fresh release verdict |
| Existing regression run | `python -m pytest tests/test_conservative_front.py tests/test_package_packshot.py tests/test_rabuta_publish.py -q`: 67 passed |
| Existing workbook copy | 671 X images, no missing/extra accepted rows; W/Y embedded image bytes match source; source hash matches recorded hash |
| Labels | `coverage/labels_1000.jsonl`: 1,000 entries, 1,000 unique ids; `matrix.json` describes group composition, not measured algorithm accuracy |

After the legacy process exited, a read-only audit observed 1,350 rows: 403 ACCEPTED, 404 QA_RETURN, 466 CUSTOMER_RESHOOT, 75 BLOCKED_INCOMPLETE_EDGE, and 2 BLOCKED_IDENTITY. All 403 accepted rows lacked recorded Q1–Q6 gates/output hashes in the legacy ledger and therefore fail current reuse/release validation. A read-only manifest with workbook/index/ledger and accepted-image hashes is at `%TEMP%\front-v5-quality-acceptance-fixes-sdd\verification-baseline.json`; the implementation has not modified these old outputs.

These numbers describe a snapshot, not acceptance of the 411 files that pass the old checker. The checker misses semantic defects.

## Implementation progress (2026-10-16)

- Implemented: Q1–Q6 evaluator with fail-closed missing evidence; worker acceptance uses the evaluator and verifies the encoded JPEG; manual review evidence can be supplied per barcode under `RUN_DIR/qa/` with source-core/product/envelope PNG masks; evidence manifests and mask hashes invalidate resume.
- Implemented: input/config/source-inventory fingerprints, output-hash resume checks, curated `apptance` treated as selection only, product-bbox geometry at 2064 px with no upscale, removed border-mask erasure, strict front score floor/margin, runner read-only audit default and isolated first-150 run stage, release validator, mandatory release for atomic workbook embed, and missing-X-anchor rejection.
- Verification: focused tests pass (111 passed) and Python compile checks pass. A read-only join against the 1,000-label file matched 628 rows; 372 labels have no ledger source/barcode match. The legacy ledger has no Q1 evidence for any label and all 403 legacy ACCEPTED rows fail current hash/gate/fingerprint validation. The baseline workbook hash still matches its captured snapshot. No new render batch or workbook embed was run.
- Still open: complete real-image clipping/wrong-face regression fixtures, grouped benchmark across all 1,000 labels, end-to-end evidence/resume and Excel fixture tests, and independent first-batch plus >=93 accepted-image visual review. The legacy 403 accepted rows remain stale and unreleased. Candidate rows without independently supplied evidence stay `QA_RETURN`.

Confirmed cases to pin as regressions:

- `4902856453527`, Excel row 77: accepted output contains a cut strip of a bottle.
- `8858731200853`, row 23: accepted output shows the ingredient/nutrition face, but current canvas QA passes.
- `8850157516457`, row 4: accepted output fails the current second-product gate.
- Synthetic 2,000-square panel renders at scale 1.032 and passes current canvas QA.
- Synthetic 2,000-pixel product plus 18% background padding is recorded as native side 2,720; product renders around 1,518 pixels and passes current QA.
- Synthetic narrow cap touches the source boundary across 20 of 400 pixels; selector clears two mask rows and returns it instead of rejecting.
- Two identical candidate faces with equal matching scores are resolved to the first candidate rather than returned as ambiguous.

## Global Constraints

- Source workbook: `source-import/new_source_from_customer/14-10-new-requirment-final/Rabuta_master_SKU_categories_ingredients_final.xlsx`. Read actual row count; retain barcode text, Excel row and Record ID.
- Production originals come from the five existing source folders. Do not use front-v3, back-v2 or workbook thumbnails as production RGB sources.
- Preserve customer workbook bytes, original photographs, front-v3 and back-v2. Tests and validation write only to temporary or new run-specific locations.
- Canvas 2400×2400 RGB; real product long side 2064 ± 2 px; minimum canvas margin 48 px; scale <= 1; aspect-ratio error <= 0.5%; rotations only multiples of 90 degrees.
- Preserve the complete unit of sale, including pale caps, seals, clear film, windows and trays. Never erase a detected product boundary to make a clipping check pass.
- One JPEG encoding at quality 95 with 4:4:4 for newly rendered files. Validate the saved JPEG, not just the in-memory image.
- Selection by the customer is explicit evidence of preference, not an automatic pass of technical gates. Do not alter curated files in `apptance`.
- Report catalog coverage separately from quality. A low yield is acceptable when the alternative is a critical-defect accept; no artificial coverage target.
- Use Windows PowerShell at `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`, `login=false`, for exec calls. No destructive cleanup of shared folders.

## Contract decisions to reconcile in Task 1

1. Preserve the existing Q3 allowance for a rectangular retained background that protects clear packaging. Define separate **complete product mask/bbox** and **allowed retained envelope**. Q1 whiteness is measured outside that envelope; the envelope must independently pass Q2/Q3 and cannot simply be enlarged to hide defects. Record retained-background area in reports.
2. The existing 18% padding is a maximum search/context allowance, not mandatory rendered padding. Mandatory 18% on both sides of a 2064 px product would require 2807 px before canvas margins and cannot fit 2400. Retain necessary packaging inside the complete product bbox, constrain optional background to the available canvas margin, and reject when all hard geometry conditions cannot coexist. Do not reduce product occupancy or remove film silently.
3. `ACCEPTED` means all Q1–Q6 passed for the current evidence and file hash. It does not mean the batch is released. Export requires a separate release record for the exact accepted set.
4. Front match must exceed both the absolute score floor and the runner-up margin. Start with the declared constants: appearance minimum 0.12/margin 0.06, SIFT minimum 0.08/margin 0.05. Any adjustment needs a versioned grouped evaluation, never a one-image exception. No ambiguous position-based fallback.
5. Lack of a reliable front reference is a review state. Lack of Y must not produce an invented comparison pass: require separately recorded visual evidence that the chosen face is the front before accepting that row.
6. Never label a score derived from the selected mask itself as independent proof of complete packaging. Use reviewed source boundaries for evaluation; uncertain pale/transparent boundaries must return to review.

## File ownership

| File | Responsibility/change |
| --- | --- |
| `src/product_mapper/vision/conservative_front.py` | Selection evidence, ambiguity, clipping and native product geometry; preserve existing callers through explicit optional evidence parameters where needed |
| New `src/product_mapper/vision/front_v5_quality.py` | Q1–Q6 checks and structured measurements; no rendering or file publishing |
| `src/product_mapper/vision/front_v5_ledger.py` | Input/output fingerprints, resume eligibility, explicit curated selection records and release validation |
| `src/product_mapper/vision/front_v5_workers.py` | Pass source/reference/geometry evidence to QA; save once, validate actual file, return complete evidence |
| `scripts/run_front_v5_batch.py` | Explicit run stages, retry/resume policy, first-150 stop, reports and release-bound export |
| `scripts/embed_front_v5.py` | Export preflight and exact X-row reconciliation; retain existing W/Y protection |
| New `scripts/audit_front_v5_acceptance.py` | Read-only current-result audit, grouped benchmark report and seeded visual sample manifest |
| `tests/test_conservative_front.py` | Selector/renderer regressions; remove permissive assertions for known false accepts |
| New `tests/test_front_v5_quality.py`, `tests/test_front_v5_resume.py`, `tests/test_front_v5_release.py`, `tests/test_embed_front_v5.py` | Gate boundaries, invalidation, curated inputs, release and workbook safety |

Do not restructure the entire vision module or change the legacy polygon scripts unless a verified caller compatibility issue requires it.

## Review Focus

- Changed/deleted source or output after an accepted run must invalidate reuse and release (Task 3).
- A missing Y reference, equal-score faces or a back-only original must not silently become a confident front (Task 5).
- Clear film and a narrow pale cap at the photo boundary must not disappear while the colored mask still looks complete (Task 4).
- A user-selected PNG/JPEG replaced with different bytes must not reuse an old destination by existence or file size (Task 3).
- A missing X anchor or failure during workbook writing must not produce a successful partial release or overwrite the previous deliverable (Task 6).

## Task 1: Reconcile the measurable contract and freeze baseline evidence

**Files:** existing change proposal/design/spec/tasks listed above; audit fixtures under a new run-specific evidence directory; no production output replacement.

- [ ] Read current sources and the three existing spec files; reconcile the six contract decisions above in the existing planning artifacts. Remove older farthest-face/middle-barcode position rules that conflict with Q4. Reopen affected completed task boxes with an audit explanation; do not erase history or mark the repairs done.
- [x] Run the baseline test set as part of final focused verification and capture source workbook, implementation, index, ledger and accepted-output hashes outside the repository. Hashes are in `%TEMP%\front-v5-quality-acceptance-fixes-sdd\verification-baseline.json`.
- [ ] Preserve small regression fixtures for the named real failures and positive controls, with source hash, reviewed complete bbox/mask, expected front identity and expected gate result. Do not rely on an ignored `output/` folder being present in CI; tests requiring large private originals must explicitly skip and the local benchmark must require them.

**Acceptance:** one consistent product/envelope definition, unchanged protected input hashes, fixtures with explicit expected results. No algorithm or production files changed by this task's baseline run.

## Task 2: Make all acceptance routes use Q1–Q6 evidence

**Interfaces:** add `evaluate_front(image: Image.Image, evidence: dict) -> dict` in `front_v5_quality.py`. Return `passed: bool` and `gates`, keyed exactly `Q1`..`Q6`, each with `passed`, `reason`, `measurements`. Missing required evidence fails the relevant gate. Evidence contains product/envelope masks in canvas coordinates, reviewed source completeness information, face scores/review reference, geometry, catalog identity and source hash.

- [ ] Write failing tests for each gate's passing and failing boundary, including 64×64 corners, a 1 px product margin, a 1.01 scale, a disconnected fragment above 1% product area, duplicate/equal-sized products, holes over 0.5%, wrong filename barcode and absent completeness evidence.
- [ ] Implement Q1: RGB/size, >=99.5% outside-envelope pixels with every channel >=250, each 64×64 corner mean >=253. Implement Q2: source completeness, >=99.5% coverage of independent package core, holes <=0.5%, and >=90% background along any separation cut. Implement Q3: one complete sale unit, rectangular retained fill >=90%, otherwise residual background <=9% of product area, and no detached piece >1%. Apply the reconciled envelope limits from Task 1.
- [ ] Implement Q4 using Task 5 evidence, Q5 using Task 4 geometry and encoded-file properties, Q6 using catalog identity plus output filename and conflict status. Do not treat an unmeasured condition as passed.
- [ ] Keep `output_is_clean(image)` as a coarse compatibility check if callers need it; document that it cannot authorize acceptance alone. Worker and final audit must require the structured evaluator.
- [ ] Run `python -m pytest tests/test_front_v5_quality.py tests/test_conservative_front.py -q`; all new rejection cases and positive controls must pass. A pure-white image must fail, even when placed in `apptance`.

## Task 3: Fix stale resume and curated-image bypass

**Interfaces:** ledger helpers `build_run_fingerprint(workbook_sha256: str, implementation_hashes: dict, config: dict) -> str`, `can_reuse_result(result: dict, expected: dict) -> bool`, and `load_apptance_records(apptance_dir, front_dir=None)` retained for caller compatibility but without implicit acceptance. Result evidence includes input hashes (source/W/Y or explicit missing values), run fingerprint, geometry, gate measurements and output SHA-256.

- [ ] Write failing resume tests for implementation/configuration/W/Y/source changes, missing or modified outputs, legacy log rows without hashes, newly added source files, and previously rejected rows with newly available candidates. Add curated-image tests for blank images, wrong canvas, PNG updates and JPEG updates with the same file size.
- [ ] Index reuse must compare source inventory and hashes, not `len(indexed) >= 1000`. Reuse accepted output only when evidence is current, output hash matches and QA remains valid. A changed QA version rechecks existing files; rerender from originals only when render inputs/selection changed. Unchanged terminal failures may be reused only for the identical candidate set/config, with an explicit retry option.
- [ ] Preserve `apptance` as user selection input. Bind explicit selection provenance to barcode, Record ID and selected file hash. Never re-encode a JPEG merely to copy it; normalize from the original if required and available, otherwise send a technically invalid curated image to review without modifying its source.
- [ ] Validate curated images with the same gates and record missing source/geometry proof as review, not an invented success. Use the catalog barcode for the destination; verify normalized variants cannot bypass identity conflicts.
- [ ] Run `python -m pytest tests/test_front_v5_resume.py tests/test_front_v5_quality.py -q`. Same inputs reuse valid bytes; any relevant change invalidates the affected acceptance/release.

## Task 4: Fix clipping and real-product geometry

**Interfaces:** keep `render_panel(...) -> tuple[Image.Image, dict]`; metrics must distinguish `source_product_bbox`, `source_envelope_bbox`, `canvas_product_bbox`, `canvas_envelope_bbox`, `native_long_side` (product only), `scale`, `placed_size` and rotation. Preserve the existing `select_front_package` tuple contract; expose optional selection evidence for worker/QA without breaking existing tests/callers.

- [ ] Add failing tests for the 20/400-pixel clipped cap, pale/transparent protrusions, a 2,000 px product with 18% background, exact 2064 px and just-below-threshold native products, and scale in `(1, 1.05]`. Assert genuine background touching the source edge is allowed.
- [ ] Remove the mask-border erasure escape. If actual package completeness cannot be established, reject/review; padding cannot restore a package already cut by the camera frame.
- [ ] Calculate scale from complete product bbox: 2064/native product long side. Reject scale >1. Fit the allowed envelope around that product with >=48 px canvas margin; reject an impossible layout instead of silently shrinking the product. Copy original pixels once with the same scale on both axes.
- [ ] Validate saved geometry and JPEG through Task 2 before accepting. Preserve source RGB within the allowed envelope; do not whiten transparent material to satisfy Q1.
- [ ] Run `python -m pytest tests/test_conservative_front.py tests/test_front_v5_quality.py tests/test_package_packshot.py tests/test_rabuta_publish.py -q`. Positive pale-cap/film controls must remain intact; legacy renderer/publisher behavior must remain compatible.

## Task 5: Require defensible front selection and grouped evaluation

**Files:** selector, worker, audit script and corresponding regression tests.

- [ ] Write failing tests for equal high scores, scores below the floor despite a large gap, high scores with insufficient runner-up gap, back score equal/higher than front, missing Y, unreliable W and three subjects whose front is in the middle. Assert a barcode on a verified front is allowed.
- [ ] Use one shared score-decision helper in the selector for both `_mask_matching_reference` and `_best_reference_subject`. Enforce absolute floor AND margin; remove the 0.04/0.02 relaxation. Record score method, winner, runner-up, front/back comparisons and explicit review evidence. Do not choose by position on an ambiguous fallback.
- [ ] Add the named real wrong-face case with a reviewed expectation. Change `test_audit_false_accepts_fail_the_qa_gate` so every known defective fixture must fail its specified gate; a rectangular crop must not waive a wrong-face or completeness failure.
- [ ] Implement audit CLI `python scripts/audit_front_v5_acceptance.py --run-dir <new-run> --labels <labels-file>` to evaluate the current files and write per-gate/per-group counts, wrong-face accepts, clipped accepts, multi-product accepts, reviewed minor defects and coverage. Use deterministic ordering and record seeds/hashes.
- [ ] Evaluate all 1,000 labeled originals. Verify whether labels describe source subjects or full package boundaries; add independent annotations where needed rather than pretending existing labels prove masks. Split tuning/validation by product identity/source hash to avoid duplicate-source leakage; disclose prior exposure, since the existing 1,000 images are not proven unseen data.
- [ ] Run the relevant tests, then the grouped benchmark. No group may introduce a critical-defect accept. Report recall/yield separately; do not tune thresholds until a few chosen examples look good and call the suite accepted.

## Task 6: Enforce first-batch review and release-bound export

**Interfaces:** add `validate_release(ledger: list[dict], release: dict, run_fingerprint: str) -> None` to ledger helpers. Release JSON binds accepted-set digest, per-output hashes, run fingerprint, review sample ids/seed, per-group counts, reviewer decisions and approval of the first 150 rows. The validator raises on any missing/stale/mismatched evidence.

- [ ] Write failing tests: export without release, one critical sample defect, more than one minor defect, changed accepted set/output bytes, insufficient sample, unreviewed first batch, missing X anchor and failed workbook write. All must prevent successful export.
- [ ] Give the runner explicit stages `--stage index|render|audit|embed`, defaulting to read-only `audit`. A new run's render stops after the first 150 ledger rows and emits source/W/Y/output comparisons with barcode labels. Remaining rendering requires a recorded clean first-batch review bound to those exact files; do not auto-create a positive review.
- [ ] Sample at least 93 accepted outputs by group after auto QA, with at least eight from each group having >=30 accepted outputs. Record human/independent visual decisions: zero critical and at most one minor defect. If fewer than 93 outputs exist, review all and explicitly report that the specified sample target is unmet; do not claim the stated 95% quality confidence.
- [ ] Any critical defect blocks release and returns the affected group's accepted candidates to review. A changed algorithm or file invalidates the associated review. Automated gates alone cannot manufacture visual approval.
- [ ] Embed only the release-bound set into a new run-specific workbook copy. Preflight exact row/identity mapping; fail on missing X anchors rather than silently dropping accepted rows. Write to a temporary destination, verify W/Y bytes and exact X set/unique sequential drawing ids, then finalize atomically. Reconcile before publishing; protect the previous deliverable on errors.
- [ ] Run `python -m pytest tests/test_front_v5_release.py tests/test_embed_front_v5.py tests/test_front_v5_resume.py -q`. Use temporary workbooks and image fixtures; do not call the live production runner as a unit test.

## Task 7: Final verification and handoff

- [ ] Run focused suite: `python -m pytest tests/test_conservative_front.py tests/test_front_v5_quality.py tests/test_front_v5_resume.py tests/test_front_v5_release.py tests/test_embed_front_v5.py tests/test_package_packshot.py tests/test_rabuta_publish.py -q`.
- [ ] Inspect repository CI/config for supported lint/type checks and full tests; run relevant checks and report pre-existing failures, unavailable tools or skipped real-image fixtures explicitly. Do not install tools merely to create an unrelated new check.
- [ ] Re-audit the old accepted set read-only; distinguish stale acceptance, technical failure, semantic failure and user selection. Do not delete or overwrite it. Produce a fresh candidate set in a new run directory and require Task 6 review before embedding.
- [ ] Verify all catalog rows have exactly one current ledger state; accepted rows have matching file/evidence hashes and Q1–Q6 pass; review/reshoot/conflict rows cannot enter the release set. Verify workbook source/front-v3/back-v2 hashes stayed unchanged.
- [ ] Report before/after coverage and measured quality by group/gate, all six finding resolutions, sample results and remaining reshoots. Revise existing task boxes only on fresh evidence. Do not say “95% quality” based on unit tests or the old canvas checker.
- [ ] Stop at the user's authorized boundary. Do not commit, upload Shopify, deploy, archive the change or replace existing delivery paths without explicit authorization for that action.

## Definition of done

All six audited defects have regression coverage; no acceptance path bypasses the shared gates; old results cannot survive changed evidence silently; no critical-defect accept appears in grouped validation or the release sample; every workbook X image is in the validated release set; protected sources remain byte-identical. Missing visual review means implementation may be ready, but the batch remains unreleased.

## Planning self-review

- Finding mapping: stale reuse -> Task 3; wrong face -> Task 5; clipping -> Task 4; scale/occupancy -> Task 4; curated bypass -> Tasks 2–3; automatic embed -> Task 6.
- Q1/Q3 and padding/occupancy contradictions have explicit reconciliation decisions in Task 1.
- All five Review Focus cases have named owning tasks and expected failure behavior.
- Existing `output_is_clean` remains a coarse compatibility function; `evaluate_front` owns acceptance; `validate_release` owns permission to export. These are distinct contracts.
- Implementation is authorized by the user's follow-up request. Batch release remains blocked until Task 6 human review is recorded.
