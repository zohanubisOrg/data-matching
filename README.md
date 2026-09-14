# Product Image POS Reconciliation Tool

This tool reconciles supplier/store product images against the POS workbook. POS is the source of truth for Product ID, SKU and Barcode. Supplier/source IDs are never treated as POS identifiers.

The production `run` pipeline is now **strict no-fuzzy**: fuzzy-name similarity is never allowed to create `AUTO_MATCHED`. The priority is human-approved mapping -> validated exact barcode -> deterministic canonical filename -> deterministic OCR review candidate -> review/unmatched.

## Install on Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

For barcode decoding:

```powershell
python -m pip install -e ".[dev,barcode]"
```

For optional PaddleOCR 3.x evidence extraction, install the PaddlePaddle CPU runtime first, then the project OCR extra:

```powershell
python -m pip install paddlepaddle==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
python -m pip install -e ".[dev,barcode,ocr]"
```

PaddleOCR is optional. Barcode-only/local deterministic matching works without it.

## Strict production matching policy

The `run` command uses this decision order:

1. **Human-approved knowledge base** -> exact deterministic match when the approved barcode resolves uniquely.
2. **Barcode-first** -> multi-pass `zxing-cpp` decoding, normalization, GTIN checksum validation and exact POS lookup.
3. **Deterministic filename** -> existing no-fuzzy canonical rules only, with ambiguous POS identities downgraded to review.
4. **OCR evidence** -> PaddleOCR extracts visible text/scores/polygons; exact canonical token/family/size rules nominate review candidates.
5. **Review / unmatched** -> uncertain, conflicting or incomplete evidence is never guessed.

Important safety rules:

- A GTIN-like barcode with a bad check digit is never auto-matched.
- A decoded barcode missing from POS or duplicated in POS goes to `NEED_REVIEW`.
- A non-GTIN barcode can be shown as an exact review candidate but is not auto-matched by the production policy.
- If OCR deterministically identifies a different product from a checksum-valid barcode result, the record goes to `NEED_REVIEW`.
- OCR-only candidates are review candidates in this phase; OCR does not silently decide SKU identity.
- `rapidfuzz` remains in legacy/manual name-matching utilities, but the production `run` pipeline does not import or call the fuzzy image matcher.

## Run

From the repository root:

### Barcode-first, OCR disabled

```powershell
python -m product_mapper.cli run `
  --images .\unique_pack1 `
  --images .\unique_pack2 `
  --pos .\Products_imported_to_Shopbox_19_08_26_with_SKU.xlsx `
  --imports .\Ten_hang_nhap.xlsx `
  --output .\output `
  --ocr-provider none `
  --verbose
```

### Barcode-first + PaddleOCR evidence

```powershell
python -m product_mapper.cli run `
  --images .\unique_pack1 `
  --images .\unique_pack2 `
  --pos .\Products_imported_to_Shopbox_19_08_26_with_SKU.xlsx `
  --imports .\Ten_hang_nhap.xlsx `
  --output .\output `
  --ocr-provider paddle `
  --verbose
```

Defaults are both image folders, the two supplied workbooks, `output`, and `--ocr-provider none`. `python -m product_mapper run` is also supported.

`--auto-threshold` and `--review-threshold` are retained for CLI/API compatibility but are intentionally ignored by the strict production `run` path. They are not allowed to turn similarity into an auto-match.

To profile without matching:

```powershell
python -m product_mapper.cli profile
```

To benchmark the import names against POS names without images or fuzzy scoring:

```powershell
python -m product_mapper.cli match-names-no-fuzzy --output .\output\no-fuzzy
```

The deterministic report separates safe name matches, unique POS identity resolution, review candidates, and unmatched rows. Supplier SKU and POS identifiers are retained for audit only; they never influence name candidate selection.

The legacy `match-names` command is still available for historical/manual benchmarking. It is separate from the strict production image pipeline and must not be used as evidence that an image is the same SKU.

## Local verification

No GitHub Actions workflow is required for this change. Run locally:

```powershell
python -m pip install -e ".[dev,barcode]"
pytest -q
```

For OCR-enabled verification:

```powershell
python -m pip install paddlepaddle==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
python -m pip install -e ".[dev,barcode,ocr]"
pytest -q
```

Then run a barcode-only smoke test and an OCR-enabled smoke test against the real image folders.

## Acceptance Criteria & Definition of Done

This project strictly adheres to the output-based Definition of Done (DoD) and 15 Pass/Fail acceptance criteria defined in `ACCEPTANCE_CRITERIA.md`.

Key principles:
- **100% Accounted For**: Every input image and POS product has a clear, tracked status.
- **100% Accuracy in Matched Dataset**: Uncertain or ambiguous matches are separated into `REVIEW`/`UNMATCHED`. Zero tolerance for silent wrong matches.
- **Canonical Barcode Filenames**: All matched images are copied to `output/matched-images/<barcode>.jpg`.
- **Identity Preservation**: Original Barcode and SKU from POS are never modified or synthesized.

## Outputs & Deliverables

The run creates the complete customer delivery package in `output`:

```text
output/
├── matched-images/ & images/# Canonical <barcode>.jpg images ready for website import
├── unmatched-images/        # Original unresolved/review images preserved (zero data loss)
├── review/                  # Ambiguous images needing customer confirmation
├── unmatched/               # Images without matching candidates
├── result.xlsx / result.csv # Canonical 7-column client deliverable (Barcode | SKU | Original Name | Final Name | Original Image | Final Image | Status)
├── mapping.xlsx / mapping.csv# Comprehensive audit trail
├── reconciliation_report.txt# Formal reconciliation report verifying 100% input accounting
├── mapping_result.xlsx      # Comprehensive multi-sheet audit report
├── customer_review.xlsx     # Interactive review workbook with top candidates
├── review_report.html       # Visual HTML report for side-by-side inspection
├── data_profile.xlsx        # Data profiling and quality analysis
└── run.log                  # Execution trace log
```

## Human Review & Feedback Loop (Rerun Capability)

1. Open `customer_review.xlsx`, select a candidate or `No Match` under `Customer Selection`.
2. Save the workbook and run:

```powershell
python -m product_mapper.cli apply-review
```

This persists approved decisions into `knowledge_base.json`. On subsequent runs these items are matched deterministically at `exact_human_approved` priority, avoiding repeat manual work.

## Gold dataset

Optional `gold_dataset.csv` at project root:

```csv
image_filename,expected_product_id
heuschen_10517_sesame_oil.jpg,11633374
```

Create 50-100 rows covering duplicate names, variants, sizes, each source, barcode failures, OCR failures and difficult cases. Until a representative gold dataset is evaluated, do not claim a measured production accuracy percentage.

## Troubleshooting and extension

- If a workbook schema changes, `profile` reports missing required columns before matching.
- If `zxing-cpp` is unavailable, the log records barcode decoding as unavailable and the pipeline continues with deterministic filename/OCR evidence.
- If PaddleOCR is unavailable, use `--ocr-provider none` or install a compatible PaddlePaddle runtime plus the `ocr` extra.
- If PaddleOCR fails on an individual image, the image remains auditable and falls back to deterministic review/unmatched behavior; OCR failure never creates a match.
- Add supplier aliases only where workbook/domain evidence supports them.
- Expand protected product attributes only from observed product-domain evidence; do not use edit-distance guesses to create aliases.
