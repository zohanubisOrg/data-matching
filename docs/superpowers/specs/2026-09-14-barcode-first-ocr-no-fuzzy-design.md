# Barcode-First OCR No-Fuzzy Design

## Goal

Make the main image reconciliation pipeline deterministic for production product photos: barcode is the primary identifier, OCR is evidence/verification and recovery support, and fuzzy-name similarity is never allowed to produce `AUTO_MATCHED`.

## Constraints

- POS remains the source of truth for Product ID, SKU and Barcode.
- No fuzzy-name or semantic similarity may decide `AUTO_MATCHED` in the main `run` pipeline.
- Uncertain, conflicting or incomplete evidence must become `NEED_REVIEW`/`UNMATCHED` instead of being guessed.
- Existing human-approved knowledge-base mappings remain highest-priority deterministic evidence.
- Existing legacy fuzzy/name-only commands may remain for benchmarking/manual workflows, but they are not used by the production image pipeline.
- No GitHub Actions workflow is added or modified for this change.

## Architecture

### 1. Evidence acquisition

Each image is processed in this order:

1. Human-approved knowledge-base mapping.
2. Multi-pass barcode decoding.
3. Optional OCR extraction with PaddleOCR 3.x.
4. Deterministic filename/OCR candidate resolution.
5. Review/unmatched fallback.

Barcode decoding runs before any name-based matching.

### 2. Barcode evidence

`BarcodeReader` performs multiple deterministic image passes using Pillow only (original, grayscale/autocontrast, upscaled variants and rotations). Every decoded value is normalized and counted. A barcode is considered strong when one value wins consensus and it is either:

- a checksum-valid GTIN-8/UPC-A/GTIN-13/GTIN-14 value, or
- a non-GTIN POS barcode that exactly matches a unique POS barcode, but this second case is treated conservatively as unvalidated evidence.

GTIN-like values with invalid check digits never auto-match.

### 3. OCR evidence

OCR is optional and pluggable. `PaddleOCRProvider` uses PaddleOCR 3.x `predict()` and stores recognized text, confidence and polygons as audit evidence. OCR does not generate similarity scores.

The OCR parser builds deterministic structured evidence from exact observed tokens and measurements. It may identify canonical product-family text, protected qualifiers/variants and normalized size/unit information. OCR results are used to:

- detect conflicts against a barcode-resolved POS product;
- generate deterministic review candidates when barcode decoding fails;
- provide auditable text evidence in reports/logs.

OCR-only matching is conservative in this phase: it may nominate a unique candidate for review, but does not auto-match unless the evidence path is an exact deterministic identity with no ambiguity and the policy explicitly allows it in a later phase.

### 4. Deterministic matching policy

The main pipeline uses this priority:

1. `exact_human_approved` -> `AUTO_MATCHED` when the approved barcode resolves uniquely.
2. `exact_barcode` -> `AUTO_MATCHED` only for a unique POS barcode with accepted validation and no detected OCR conflict.
3. `deterministic_filename` -> `AUTO_MATCHED` only when the existing no-fuzzy matcher resolves one unambiguous POS identity.
4. `deterministic_ocr_review` -> `NEED_REVIEW` with an exact deterministic candidate when barcode/filename cannot safely identify the product.
5. Otherwise -> `NEED_REVIEW` or `UNMATCHED`.

No branch in the main pipeline may return `match_method="fuzzy_name"`.

### 5. Conflict handling

Hard conflicts always block auto-match. Initial protected conflicts include:

- size mismatch;
- different protected qualifier/variant values (for example red vs green, apple vs lemon where represented in canonical tokens);
- multiple POS products sharing the same resolved barcode;
- invalid GTIN check digit;
- OCR evidence that deterministically contradicts the barcode-resolved product.

Missing OCR evidence is not itself a conflict; a valid unique barcode can still auto-match.

## Components

- `src/product_mapper/vision/barcode_utils.py`: barcode normalization and GTIN validation.
- `src/product_mapper/vision/barcode_reader.py`: multi-pass decode + consensus evidence.
- `src/product_mapper/vision/provider.py`: OCR evidence models/protocol and no-op provider.
- `src/product_mapper/vision/paddle_ocr.py`: lazy PaddleOCR 3.x provider.
- `src/product_mapper/parsing/ocr_parser.py`: deterministic OCR text/attribute extraction.
- `src/product_mapper/matching/image_deterministic.py`: deterministic image candidate helpers using existing no-fuzzy rules.
- `src/product_mapper/pipeline.py`: barcode-first orchestration; fuzzy matcher removed from the production path.
- `src/product_mapper/cli.py`: optional `--ocr-provider none|paddle` selection.
- `tests/`: unit tests for GTIN validation, barcode consensus, OCR parsing and production-pipeline policy.

## Dependencies

PaddleOCR remains optional because model/runtime installation is heavier and platform-specific. The project exposes an `ocr` optional extra for the Python package; PaddlePaddle runtime installation is documented separately according to the official PaddleOCR installation guidance. Barcode decoding continues to use optional `zxing-cpp`.

## Local verification

The intended local verification commands are:

```powershell
python -m pip install -e ".[dev,barcode]"
pytest -q

# OCR-capable environment
python -m pip install paddlepaddle==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
python -m pip install -e ".[dev,barcode,ocr]"
pytest -q

python -m product_mapper.cli run `
  --images .\unique_pack1 `
  --images .\unique_pack2 `
  --pos .\Products_imported_to_Shopbox_19_08_26_with_SKU.xlsx `
  --imports .\Ten_hang_nhap.xlsx `
  --output .\output `
  --ocr-provider paddle `
  --verbose
```

GitHub Actions is intentionally not part of validation for this work.
