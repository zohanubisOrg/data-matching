# Product Image POS Reconciliation Tool

This tool maps supplier image filenames to products in the POS workbook. POS is the source of truth for Product ID, SKU and Barcode. Supplier/source IDs are never treated as POS identifiers.

## Install on Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Optional barcode decoding:

```powershell
python -m pip install -e ".[dev,barcode]"
```

## Run

From `D:\Work\shopify`:

```powershell
python -m product_mapper.cli run `
  --images .\unique_pack1 `
  --images .\unique_pack2 `
  --pos .\Products_imported_to_Shopbox_19_08_26_with_SKU.xlsx `
  --imports .\Ten_hang_nhap.xlsx `
  --output .\output `
  --verbose
```

Defaults are both image folders, the two supplied workbooks, and `output`. `python -m product_mapper run` is also supported. To profile without matching:

```powershell
python -m product_mapper.cli profile
```

To benchmark the 748 import names against POS names without images or fuzzy scoring:

```powershell
python -m product_mapper.cli match-names-no-fuzzy --output .\output\no-fuzzy
```

The deterministic report separates safe name matches, unique POS identity resolution,
review candidates, and unmatched rows. Supplier SKU and POS identifiers are retained for
audit only; they never influence name candidate selection.

## Acceptance Criteria & Definition of Done

This project strictly adheres to the output-based Definition of Done (DoD) and 15 Pass/Fail acceptance criteria defined in [ACCEPTANCE_CRITERIA.md](file:///d:/Work/shopify/ACCEPTANCE_CRITERIA.md).

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
├── mapping.xlsx / mapping.csv# 12-column comprehensive audit trail (barcode, sku, product_id, names, supplier, supplier_sku, images, method, score, status)
├── reconciliation_report.txt# Formal reconciliation report verifying 100% input accounting
├── mapping_result.xlsx      # Comprehensive multi-sheet audit report
├── customer_review.xlsx     # Interactive review workbook with top 3 candidates
├── review_report.html       # Visual HTML report for side-by-side inspection
├── data_profile.xlsx        # Data profiling and quality analysis
└── run.log                  # Execution trace log
```

## Human Review & Feedback Loop (Rerun Capability)

1. Open `customer_review.xlsx`, select `1`, `2`, `3`, or `No Match` under `Customer Selection`.
2. Save the workbook and run the feedback loop command:

```powershell
python -m product_mapper.cli apply-review
```

This persists all approved decisions into `knowledge_base.json`. On subsequent runs, these items are matched deterministically at **Level 1 (`EXACT_HUMAN_APPROVED`)** with 100% confidence, saving human effort and allowing the system to continuously improve.

## Gold dataset

Optional `gold_dataset.csv` at project root:

```csv
image_filename,expected_product_id
heuschen_10517_sesame_oil.jpg,11633374
```

Create 50-100 rows covering duplicate names, variants, sizes, each source, and difficult cases. The current run has no gold dataset, so it must not claim accuracy.

## Troubleshooting and extension

- If a workbook schema changes, `profile` reports the missing required columns before matching.
- If `zxing-cpp` is unavailable, filename/name matching still runs and the log records barcode decoding as unavailable.
- Tune `--auto-threshold`, `--review-threshold`, and `--top-k` only after reviewing a gold dataset; lowering thresholds increases false-auto-match risk.
- Add supplier aliases only in `src/product_mapper/config.py` when the workbook provides clear evidence.
- Add future image intelligence by implementing `VisionProvider`; the default `NoOpVisionProvider` requires no API key.
