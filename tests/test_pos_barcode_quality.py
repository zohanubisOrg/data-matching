from pathlib import Path

import pandas as pd

from product_mapper.ingestion.pos_loader import load_pos


VALID_EAN13 = "4006381333931"
VALID_GTIN14_EQUIVALENT = "04006381333931"
INVALID_EAN13 = "4006381333932"


def write_pos(path: Path, rows: list[dict]) -> None:
    defaults = {
        "Product Name": "Product",
        "Oficial Name": "Product",
        "Printer Name": "Product",
        "Bar Code": "",
        "Sku Code": "SKU",
        "Product Id": "1",
    }
    frame = pd.DataFrame([{**defaults, **row} for row in rows])
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="Ten_ban", index=False)


def test_pos_loader_reports_invalid_gtin_without_mutating_barcode(tmp_path):
    path = tmp_path / "pos.xlsx"
    write_pos(path, [{"Bar Code": INVALID_EAN13}])

    products, issues, _ = load_pos(path)

    assert products[0].barcode == INVALID_EAN13
    assert any(issue.issue_type == "invalid GTIN check digit" for issue in issues)


def test_pos_loader_reports_standards_equivalent_gtin_collision(tmp_path):
    path = tmp_path / "pos.xlsx"
    write_pos(path, [
        {"Product Id": "1", "Sku Code": "SKU-1", "Bar Code": VALID_EAN13},
        {"Product Id": "2", "Sku Code": "SKU-2", "Bar Code": VALID_GTIN14_EQUIVALENT},
    ])

    _, issues, _ = load_pos(path)

    collisions = [issue for issue in issues if issue.issue_type == "equivalent GTIN collision"]
    assert len(collisions) == 1
    assert collisions[0].count == 2


def test_pos_loader_reports_normalized_barcode_collision(tmp_path):
    path = tmp_path / "pos.xlsx"
    write_pos(path, [
        {"Product Id": "1", "Sku Code": "SKU-1", "Bar Code": "LOCAL-ABC-001"},
        {"Product Id": "2", "Sku Code": "SKU-2", "Bar Code": "LOCAL ABC 001"},
    ])

    _, issues, _ = load_pos(path)

    assert any(issue.issue_type == "normalized barcode collision" for issue in issues)
