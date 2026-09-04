from pathlib import Path
import pandas as pd

from ..models import SupplierProduct

SHEETS = ["EUR", "SEK", "Hàng mua tại Đan Mạch"]


def load_imports(path: Path) -> tuple[list[SupplierProduct], dict]:
    records = []; sheet_meta = {}
    for sheet in SHEETS:
        frame = pd.read_excel(path, sheet_name=sheet, dtype=str, keep_default_na=False)
        frame.columns = [str(c).strip() for c in frame.columns]
        sheet_meta[sheet] = {"rows": len(frame), "columns": list(frame.columns), "null_counts": {c: int((frame[c].astype(str).str.strip() == "").sum()) for c in frame.columns}, "dtypes": {c: str(frame[c].dtype) for c in frame.columns}, "sample_records": frame.head(3).to_dict("records")}
        for row in frame.to_dict("records"):
            records.append(SupplierProduct(name=str(row["Tên hàng (đầy đủ theo hóa đơn)"]).strip(), supplier=str(row["Nhà cung cấp"]).strip(), supplier_sku=str(row.get("SKU nhà cung cấp", "")).strip() or None, sheet=sheet))
    return records, {"rows": len(records), "sheets": SHEETS, "sheet_details": sheet_meta}
