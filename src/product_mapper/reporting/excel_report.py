from pathlib import Path
import json

import openpyxl
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from ..models import DataQualityIssue, MatchResult
from .serializers import flat_result

BLUE = "1F4E78"


def _sheet(wb: Workbook, name: str, headers: list[str], rows: list[list[object]]) -> None:
    ws = wb.create_sheet(name); ws.append(headers)
    for row in rows: ws.append(row)
    ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions
    for cell in ws[1]: cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor=BLUE); cell.alignment = Alignment(wrap_text=True)
    for column in ws.columns:
        letter = column[0].column_letter; width = min(55, max(12, max(len(str(x.value or "")) for x in column) + 2)); ws.column_dimensions[letter].width = width
    for row in ws.iter_rows():
        for cell in row: cell.alignment = Alignment(vertical="top", wrap_text=True)


def _candidate_columns(result: MatchResult) -> list[object]:
    values = []
    for candidate in result.top_candidates[:3]:
        values.extend([candidate.product.product_name, candidate.product.product_id, candidate.product.sku, candidate.product.barcode or "", round(candidate.score, 4)])
    while len(values) < 15: values.append("")
    return values


def write_reports(results: list[MatchResult], issues: list[DataQualityIssue], profile: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    counts = {status: sum(r.status == status for r in results) for status in ["AUTO_MATCHED", "NEED_REVIEW", "UNMATCHED", "ERROR"]}
    total = len(results); pct = lambda n: n / total if total else 0
    wb = Workbook(); wb.remove(wb.active)
    summary_headers = ["Metric", "Value"]
    summary_rows = [["Total POS products", profile.get("pos", {}).get("rows", 0)], ["Total imported products", profile.get("imports", {}).get("rows", 0)], ["Total images", total], ["Pack1 images", profile.get("images", {}).get("directories", {}).get("unique_pack1", 0)], ["Pack2 images", profile.get("images", {}).get("directories", {}).get("unique_pack2", 0)], ["Auto matched", counts["AUTO_MATCHED"]], ["Need review", counts["NEED_REVIEW"]], ["Unmatched", counts["UNMATCHED"]], ["Errors", counts["ERROR"]], ["Auto match %", pct(counts["AUTO_MATCHED"])], ["Review %", pct(counts["NEED_REVIEW"])], ["Unmatched %", pct(counts["UNMATCHED"])]]
    _sheet(wb, "Summary", summary_headers, summary_rows)
    for cell in wb["Summary"][10]: cell.number_format = "0.00%"
    auto_headers = ["Image", "Source", "Source Product ID", "Parsed Name", "POS Product Name", "Official Name", "Product ID", "SKU", "Barcode", "Confidence", "Match Method", "Evidence", "Top2 Score", "Margin"]
    auto_rows = [[r.image.filename, r.image.source, r.image.source_product_id, r.image.normalized_name, r.candidate.product.product_name if r.candidate else "", r.candidate.product.official_name if r.candidate else "", r.candidate.product.product_id if r.candidate else "", r.candidate.product.sku if r.candidate else "", r.candidate.product.barcode if r.candidate else "", r.confidence, r.match_method, "; ".join(r.evidence), r.top2_score, r.margin] for r in results if r.status == "AUTO_MATCHED"]
    _sheet(wb, "Auto Matched", auto_headers, auto_rows)
    review_headers = ["Image", "Source", "Parsed Name"] + sum(([f"Candidate {i} Name", f"Candidate {i} Product ID", f"Candidate {i} SKU", f"Candidate {i} Barcode", f"Candidate {i} Score"] for i in range(1, 4)), []) + ["Reason", "Conflicts"]
    review_rows = [[r.image.filename, r.image.source, r.image.normalized_name, *_candidate_columns(r), r.reason, "; ".join(r.candidate.conflicts if r.candidate else [])] for r in results if r.status == "NEED_REVIEW"]
    _sheet(wb, "Need Review", review_headers, review_rows)
    unmatched_rows = [[r.image.filename, r.image.source, r.image.normalized_name, r.candidate.product.product_name if r.candidate else "", r.confidence, r.reason] for r in results if r.status == "UNMATCHED"]
    _sheet(wb, "Unmatched", ["Image", "Source", "Parsed Name", "Best Candidate", "Best Score", "Reason"], unmatched_rows)
    error_rows = [[r.image.filename, "matching", "ERROR", r.error or r.reason] for r in results if r.status == "ERROR"]
    _sheet(wb, "Errors", ["Image", "Stage", "Error Type", "Error Message"], error_rows)
    quality_rows = [[i.issue_type, i.field, i.value, i.count, i.details] for i in issues]
    _sheet(wb, "Data Quality", ["Issue", "Field", "Value", "Count", "Details"], quality_rows)
    wb.save(output / "mapping_result.xlsx")

    flat = [flat_result(r) for r in results]
    import csv
    with (output / "mapping_result.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(flat[0]) if flat else ["image_path"]); writer.writeheader(); writer.writerows(flat)
    (output / "mapping_result.json").write_text(json.dumps(flat, ensure_ascii=False, indent=2), encoding="utf-8")

    customer_headers = ["Image", "Detected Product", "Matched POS Product", "Barcode", "SKU", "Confidence", "Status", "Need Customer Confirmation", "Notes"]
    customer_rows = [[r.image.filename, r.image.normalized_name, r.candidate.product.product_name if r.candidate else "", r.candidate.product.barcode if r.candidate else "", r.candidate.product.sku if r.candidate else "", r.confidence, r.status, "YES" if r.status in {"NEED_REVIEW", "UNMATCHED"} else "NO", r.reason] for r in results]
    customer_wb = Workbook(); customer_wb.remove(customer_wb.active); _sheet(customer_wb, "Customer Result", customer_headers, customer_rows); customer_wb.save(output / "customer_result.xlsx")

    review_wb = Workbook(); review_wb.remove(review_wb.active)
    review_headers = ["Image", "Detected Name", "Candidate 1", "Candidate 1 Barcode", "Candidate 2", "Candidate 2 Barcode", "Candidate 3", "Candidate 3 Barcode", "Suggested Candidate", "Customer Selection", "Customer Note"]
    review_rows = []
    for r in results:
        if r.status != "NEED_REVIEW": continue
        cs = [c for c in r.top_candidates[:3]] + [None] * 3
        review_rows.append([r.image.filename, r.image.normalized_name, cs[0].product.product_name if cs[0] else "", cs[0].product.barcode if cs[0] else "", cs[1].product.product_name if cs[1] else "", cs[1].product.barcode if cs[1] else "", cs[2].product.product_name if cs[2] else "", cs[2].product.barcode if cs[2] else "", 1 if cs[0] else "", "", ""])
    _sheet(review_wb, "Review", review_headers, review_rows)
    if review_rows:
        dv = DataValidation(type="list", formula1='"1,2,3,No Match"', allow_blank=True); review_wb["Review"].add_data_validation(dv); dv.add(f"J2:J{len(review_rows)+1}")
    review_wb.save(output / "customer_review.xlsx")

