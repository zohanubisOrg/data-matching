from pathlib import Path
from collections import Counter

import pandas as pd

from ..models import DataQualityIssue, POSProduct


def load_pos(path: Path) -> tuple[list[POSProduct], list[DataQualityIssue], dict]:
    frame = pd.read_excel(path, sheet_name="Ten_ban", dtype=str, keep_default_na=False)
    frame.columns = [str(c).strip() for c in frame.columns]
    required = {"Product Name", "Oficial Name", "Printer Name", "Bar Code", "Sku Code", "Product Id"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"POS sheet missing columns: {sorted(missing)}")
    products = []
    for row in frame.to_dict("records"):
        products.append(POSProduct(
            product_id=str(row["Product Id"]).strip(), sku=str(row["Sku Code"]).strip(),
            barcode=str(row["Bar Code"]).strip() or None, category=str(row.get("Category Name", "")).strip(),
            product_name=str(row["Product Name"]).strip(), official_name=str(row["Oficial Name"]).strip(),
            printer_name=str(row["Printer Name"]).strip(), stock_price=str(row.get("Stock Price", "")).strip(),
            selling_price=str(row.get("Selling Price", "")).strip(), unit=str(row.get("Unit", "")).strip(),
        ))
    issues = []
    for field, label in [("product_id", "missing Product ID"), ("sku", "missing SKU"), ("barcode", "missing barcode")]:
        count = sum(not getattr(p, field) for p in products)
        if count: issues.append(DataQualityIssue(issue_type=label, field=field, count=count))
    for field, label in [("product_id", "duplicate Product ID"), ("sku", "duplicate SKU"), ("barcode", "duplicate barcode")]:
        counts = Counter(getattr(p, field) for p in products if getattr(p, field))
        for value, count in counts.items():
            if count > 1: issues.append(DataQualityIssue(issue_type=label, field=field, value=value, count=count))
    for field, label in [("product_name", "duplicate Product Name"), ("official_name", "duplicate Official Name")]:
        counts = Counter(getattr(p, field) for p in products if getattr(p, field))
        for value, count in counts.items():
            if count > 1: issues.append(DataQualityIssue(issue_type=label, field=field, value=value, count=count))
    duplicate_counts = {}
    for column in frame.columns:
        values = frame[column].astype(str).str.strip()
        duplicate_counts[column] = int(values[values != ""].duplicated(keep=False).sum())
    return products, issues, {"rows": len(products), "columns": list(frame.columns), "null_counts": {c: int((frame[c].astype(str).str.strip() == "").sum()) for c in frame.columns}, "dtypes": {c: str(frame[c].dtype) for c in frame.columns}, "duplicate_rows_by_field": duplicate_counts, "sample_records": frame.head(3).to_dict("records")}
