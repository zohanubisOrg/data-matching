from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from ..models import DataQualityIssue, POSProduct
from ..vision.barcode_utils import canonical_gtin14, is_gtin_like, normalize_barcode, validate_gtin


def _collision_issues(products: list[POSProduct]) -> list[DataQualityIssue]:
    issues: list[DataQualityIssue] = []

    normalized_groups: dict[str, list[POSProduct]] = defaultdict(list)
    gtin_groups: dict[str, list[POSProduct]] = defaultdict(list)
    for product in products:
        raw = product.barcode or ""
        normalized = normalize_barcode(raw)
        if not normalized:
            continue
        normalized_groups[normalized].append(product)
        canonical = canonical_gtin14(normalized)
        if canonical:
            gtin_groups[canonical].append(product)
        elif is_gtin_like(normalized) and not validate_gtin(normalized):
            issues.append(
                DataQualityIssue(
                    issue_type="invalid GTIN check digit",
                    field="barcode",
                    value=raw,
                    details=f"POS row kept unchanged; invalid checksum for {normalized}.",
                )
            )

    for normalized, rows in normalized_groups.items():
        raw_values = {product.barcode or "" for product in rows}
        if len(rows) > 1 and len(raw_values) > 1:
            issues.append(
                DataQualityIssue(
                    issue_type="normalized barcode collision",
                    field="barcode",
                    value=normalized,
                    count=len(rows),
                    details="Different raw POS barcodes normalize to the same exact lookup key.",
                )
            )

    for canonical, rows in gtin_groups.items():
        raw_values = {normalize_barcode(product.barcode) for product in rows}
        if len(rows) > 1 and len(raw_values) > 1:
            issues.append(
                DataQualityIssue(
                    issue_type="equivalent GTIN collision",
                    field="barcode",
                    value=canonical,
                    count=len(rows),
                    details="Multiple POS rows use standards-equivalent GTIN representations; auto-match must remain ambiguous.",
                )
            )
    return issues


def load_pos(path: Path) -> tuple[list[POSProduct], list[DataQualityIssue], dict]:
    frame = pd.read_excel(path, sheet_name="Ten_ban", dtype=str, keep_default_na=False)
    frame.columns = [str(column).strip() for column in frame.columns]
    required = {"Product Name", "Oficial Name", "Printer Name", "Bar Code", "Sku Code", "Product Id"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"POS sheet missing columns: {sorted(missing)}")

    products: list[POSProduct] = []
    for row in frame.to_dict("records"):
        products.append(POSProduct(
            product_id=str(row["Product Id"]).strip(),
            sku=str(row["Sku Code"]).strip(),
            barcode=str(row["Bar Code"]).strip() or None,
            category=str(row.get("Category Name", "")).strip(),
            product_name=str(row["Product Name"]).strip(),
            official_name=str(row["Oficial Name"]).strip(),
            printer_name=str(row["Printer Name"]).strip(),
            stock_price=str(row.get("Stock Price", "")).strip(),
            selling_price=str(row.get("Selling Price", "")).strip(),
            unit=str(row.get("Unit", "")).strip(),
        ))

    issues: list[DataQualityIssue] = []
    for field, label in (
        ("product_id", "missing Product ID"),
        ("sku", "missing SKU"),
        ("barcode", "missing barcode"),
    ):
        count = sum(not getattr(product, field) for product in products)
        if count:
            issues.append(DataQualityIssue(issue_type=label, field=field, count=count))

    for field, label in (
        ("product_id", "duplicate Product ID"),
        ("sku", "duplicate SKU"),
        ("barcode", "duplicate barcode"),
    ):
        counts = Counter(getattr(product, field) for product in products if getattr(product, field))
        for value, count in counts.items():
            if count > 1:
                issues.append(DataQualityIssue(issue_type=label, field=field, value=value, count=count))

    for field, label in (
        ("product_name", "duplicate Product Name"),
        ("official_name", "duplicate Official Name"),
    ):
        counts = Counter(getattr(product, field) for product in products if getattr(product, field))
        for value, count in counts.items():
            if count > 1:
                issues.append(DataQualityIssue(issue_type=label, field=field, value=value, count=count))

    issues.extend(_collision_issues(products))

    duplicate_counts: dict[str, int] = {}
    for column in frame.columns:
        values = frame[column].astype(str).str.strip()
        duplicate_counts[column] = int(values[values != ""].duplicated(keep=False).sum())

    return products, issues, {
        "rows": len(products),
        "columns": list(frame.columns),
        "null_counts": {
            column: int((frame[column].astype(str).str.strip() == "").sum())
            for column in frame.columns
        },
        "dtypes": {column: str(frame[column].dtype) for column in frame.columns},
        "duplicate_rows_by_field": duplicate_counts,
        "sample_records": frame.head(3).to_dict("records"),
    }
