# Barcode-First OCR No-Fuzzy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the production image pipeline barcode-first and deterministic, with optional PaddleOCR evidence and zero fuzzy-name authority over `AUTO_MATCHED`.

**Architecture:** Acquire exact evidence first (human mapping, barcode, OCR), normalize it, then resolve products using deterministic rules. Existing fuzzy utilities remain available only outside the production `run` path. OCR is optional and conservative: it verifies or nominates review candidates rather than guessing.

**Tech Stack:** Python 3.12+, Pydantic, Pillow, zxing-cpp (optional), PaddleOCR 3.x (optional), pytest.

**Spec:** `docs/superpowers/specs/2026-09-14-barcode-first-ocr-no-fuzzy-design.md`

## Global Constraints

- Do not add or modify GitHub Actions workflows.
- Do not allow fuzzy-name similarity to produce `AUTO_MATCHED` in `pipeline.run`.
- Preserve POS barcode/SKU values exactly; never synthesize them.
- Ambiguous/conflicting evidence goes to review/unmatched.
- Keep PaddleOCR optional and lazily imported.

---

### Task 1: Barcode validation and multi-pass evidence

**Files:**
- Create: `src/product_mapper/vision/barcode_utils.py`
- Modify: `src/product_mapper/vision/barcode_reader.py`
- Create: `tests/test_barcode_evidence.py`

**Interfaces:**
- Produces `normalize_barcode(value: object) -> str`, `is_gtin_like(value: str) -> bool`, `validate_gtin(value: str) -> bool`.
- `BarcodeReader.analyze(path)` continues exposing `.barcode` for compatibility and adds auditable decoded-value metadata through `ImageAttributes`.

- [ ] Write tests for EAN/UPC/GTIN check digits, leading-zero preservation, invalid check digits, duplicate decode consensus and ambiguous multiple values.
- [ ] Implement barcode normalization/check-digit validation.
- [ ] Refactor barcode reader to run deterministic Pillow variants and choose consensus without fuzzy logic.
- [ ] Run `pytest tests/test_barcode_evidence.py -q` locally.

### Task 2: OCR evidence provider

**Files:**
- Modify: `src/product_mapper/vision/provider.py`
- Create: `src/product_mapper/vision/paddle_ocr.py`
- Modify: `pyproject.toml`
- Create: `tests/test_ocr_provider.py`

**Interfaces:**
- `OCRLine(text: str, confidence: float, polygon: list[list[float]])`.
- `ImageAttributes` gains `ocr_lines`, `barcode_candidates`, `barcode_checksum_valid`, `warnings` while retaining `barcode`.
- `PaddleOCRProvider.analyze(path: Path) -> ImageAttributes` lazily imports `PaddleOCR`, calls `predict()`, and extracts `rec_texts`, `rec_scores`, `rec_polys` from result JSON.

- [ ] Write provider extraction tests using fake PaddleOCR result objects; no model download in tests.
- [ ] Extend evidence models/protocol.
- [ ] Implement PaddleOCR provider with lazy import and defensive result parsing.
- [ ] Add optional `ocr = ["paddleocr>=3,<4"]` dependency.
- [ ] Run `pytest tests/test_ocr_provider.py -q` locally.

### Task 3: Deterministic OCR parsing and image candidate resolution

**Files:**
- Create: `src/product_mapper/parsing/ocr_parser.py`
- Create: `src/product_mapper/matching/image_deterministic.py`
- Modify: `src/product_mapper/matching/no_fuzzy.py`
- Create: `tests/test_image_deterministic.py`

**Interfaces:**
- Public wrappers in `no_fuzzy.py`: `canonical_product_identity(value)` and `protected_qualifier_conflict(left_tokens, right_tokens)`.
- `parse_ocr_identity(lines) -> OCRIdentity` returns canonical text/tokens/family/item size.
- `match_filename_deterministic(image, products) -> MatchResult | None` maps only unambiguous no-fuzzy matches.
- `find_ocr_review_candidates(lines, products, top_k=3) -> list[MatchCandidate]` uses exact canonical token/family/size/qualifier rules only.

- [ ] Write tests for exact/canonical filename resolution, ambiguous POS identities, size conflicts, qualifier conflicts and OCR review candidates.
- [ ] Expose safe no-fuzzy identity wrappers.
- [ ] Implement OCR parser and deterministic candidate helpers.
- [ ] Run `pytest tests/test_image_deterministic.py tests/test_no_fuzzy_matching.py -q` locally.

### Task 4: Barcode-first production pipeline

**Files:**
- Modify: `src/product_mapper/pipeline.py`
- Modify: `src/product_mapper/cli.py`
- Create: `tests/test_barcode_first_pipeline.py`

**Interfaces:**
- `run(..., ocr_provider: str = "none")` accepts `none|paddle`.
- `--ocr-provider none|paddle` forwards to `run`.
- Main pipeline priority: human-approved -> barcode -> deterministic filename -> OCR review -> unmatched.

- [ ] Write tests with monkeypatched barcode/OCR providers proving barcode runs before name resolution and fuzzy matcher is never invoked.
- [ ] Implement provider factory and barcode-first orchestration.
- [ ] Block invalid GTIN, duplicate barcode and deterministic OCR conflicts from auto-match.
- [ ] Ensure OCR-only candidates remain `NEED_REVIEW` in this phase.
- [ ] Run `pytest tests/test_barcode_first_pipeline.py -q` locally.

### Task 5: Documentation and regression coverage

**Files:**
- Modify: `README.md`
- Modify: `tests/test_matching.py` only if legacy expectations conflict with the production-path separation.

- [ ] Document local install/run commands for barcode-only and OCR modes.
- [ ] Document that `run` is strict no-fuzzy while legacy `match-names` remains a separate benchmark/manual command.
- [ ] Run full local suite: `pytest -q`.
- [ ] Run one barcode-only dataset smoke test and one OCR-enabled smoke test locally when PaddleOCR runtime is installed.
