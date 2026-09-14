# Strict No-Fuzzy Source Audit — 2026-09-14

Branch: `feat/barcode-first-ocr-no-fuzzy`

## Scope

Static source audit of the production image reconciliation path:

`image ingestion -> capture grouping -> barcode -> OCR -> deterministic identity -> human review -> export/reporting`

The customer requirement is strict: fuzzy-name similarity must never decide SKU identity. Precision is prioritized over recall; unresolved evidence must go to review.

## Verification status

This document records **source-level findings and implemented safeguards only**. No GitHub Actions workflow was used. The branch still requires fresh local `pytest` plus barcode-only/OCR-enabled dataset smoke tests before any runtime completion or accuracy claim.

Measured production accuracy remains **NOT MEASURED** until a representative gold dataset is evaluated.

## High-impact findings addressed

| Area | Source risk | Production safeguard implemented |
|---|---|---|
| Fuzzy boundary | legacy RapidFuzz utilities could be confused with production identity | strict `run` does not import/call fuzzy matcher; RapidFuzz removed from default dependencies |
| Name subset | token subset could be mistaken for identity | `safe_subset` is review-only |
| Size | 2% size tolerance could equate different SKUs | normalized size equality is exact; missing one-side size is review |
| Negative semantics | stop-word `no` could collapse `No Added Sugar` | explicit protected sugar-state canonicalization |
| Logistics parsing | `24x500ml` could hide item size | compact pack size recovered deterministically |
| Trailing identity | text after case pack could be discarded | pack expression is removed in-place; surrounding brand/variant evidence is retained |
| Domain naming | Ube/Atchara/known supplier spellings differ lexically | observed dictionary aliases only; no edit-distance alias generation |
| Duplicate POS rows | duplicate Product ID/name rows could collapse into one candidate | POS row identity is preserved independently from Product ID |
| POS barcodes | raw duplicate checks miss checksum/equivalent collisions | invalid GTIN, normalized collision, EAN/UPC/GTIN-equivalent collision reporting |
| Front/back pairing | same physical product could be processed independently | explicit capture grouping with ambiguity protection |
| Mispaired capture | strong back barcode could cause front side to be skipped | full back decode + cheap secondary-side barcode verification |
| Phone orientation | EXIF rotation could reduce barcode decode | EXIF transpose before deterministic barcode variants |
| Barcode lookup cost | repeated O(images x POS) scans | run-scoped exact/canonical barcode index |
| OCR catalog scan | OCR review could scan every POS row per image | run-scoped canonical identity + inverted token postings index |
| OCR hard conflict | malformed duplicate Product IDs could hide row conflicts | hard conflict compares POS row identity, not only Product ID |
| OCR back-label noise | ingredients/nutrition could overrule a valid barcode | barcode verification OCR uses front label only |
| OCR nutrition size | last `100 ml/100 g` could be mistaken for pack size | multiple OCR measurements become ambiguous; size is not used as hard filter |
| Human review loop | duplicate barcode remained ambiguous after manual selection | approval persists exact Product ID + SKU + Barcode tuple |
| HTML review | exported JSON had no ingestion path | deterministic JSON review importer + CLI command |
| Review workload | front/back capture could require duplicate decisions | Excel Review sheet uses one decision row per physical capture |
| Image ingestion I/O | every image was hashed + directories rescanned | one traversal; SHA-256 only for same-size duplicate candidates |
| Report semantics | old HTML showed similarity %, thresholds, “100%” labels | evidence-based paginated report without fuzzy/probability language |
| HTML scalability | every item rendered into duplicated large DOM views | data embedded once; page-size rendering/search/filter |
| Canonical output | source extension could violate `<barcode>.jpg` | matched output canonicalized to JPEG |
| Export failure | row could remain MATCHED although final image copy failed | delivery becomes ERROR; original preserved unresolved |
| Duplicate unresolved filenames | flat output folders could silently overwrite images | collision-safe unresolved destination names |
| POS accounting | unique barcode count could undercount distinct approved POS rows | matched POS identity uses Product ID + SKU + Barcode tuple |
| Accuracy claims | report inferred 100% accuracy from strict rules | accuracy explicitly `NOT MEASURED` without gold/human verification |

## Local verification gate

Run from the repository root after checking out the branch:

```powershell
python -m pip install -e ".[dev,barcode]"
pytest -q
```

Then install OCR runtime and repeat:

```powershell
python -m pip install paddlepaddle==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
python -m pip install -e ".[dev,barcode,ocr]"
pytest -q
```

Run the real dataset twice and record runtime/status distributions:

```powershell
python -m product_mapper.cli run --ocr-provider none --output .\output-barcode-only --verbose
python -m product_mapper.cli run --ocr-provider paddle --output .\output-ocr --verbose
```

Compare at minimum: runtime, capture count, `AUTO_MATCHED`, `NEED_REVIEW`, `UNMATCHED`, `ERROR`, invalid input count, copy failure count, barcode conflict reasons and OCR conflict reasons.

## Accuracy gate before customer claim

Create a gold dataset containing known difficult cases, not only easy barcode successes. It should include duplicated/equivalent POS barcodes, multiple sizes, flavor/color variants, sugar-state variants, Ube/Purple Yam, Atchara/Papaya Pickle, front/back mispairing, unreadable barcode, invalid GTIN, OCR-only recovery, duplicate filenames and duplicate Product IDs.

Only after comparing branch output against that gold set should precision/recall or production accuracy percentages be reported to the customer.
