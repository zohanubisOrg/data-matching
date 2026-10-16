"""Reconciler module for 3-way barcode reconciliation, gap analysis, and missing SKU reporting."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from product_mapper.zohanubis.barcode_scanner import BarcodeScanResult
from product_mapper.zohanubis.sanitizer import RawPhotoRecord


@dataclass
class CatalogProduct:
    row_idx: int
    barcode: str
    record_id: str
    name_en: str
    brand: str
    category: str
    partition: str  # G1, G2, G3, G4, Nyt
    demo_image_cell: str
    verified_back_photos: List[Path] = field(default_factory=list)
    suggested_front_candidate: Optional[Path] = None
    selected_front_photo: Optional[Path] = None
    barcode_center: Optional[Tuple[float, float]] = None
    status: str = "PENDING"
    strategy: str = "STANDARD"  # STANDARD, SEQUENTIAL_PAIR, CARTON_BOX, SINGLE_SURFACE


@dataclass
class ReconciliationSummary:
    total_catalog_rows: int
    matched_count: int
    missing_count: int
    orphan_count: int
    missing_report_path: Path
    catalog_products: Dict[str, CatalogProduct]  # keyed by record_id
    orphan_photos: List[BarcodeScanResult]
    assigned_photos: Set[Path] = field(default_factory=set)


class BarcodeReconciler:
    """Performs 3-way reconciliation against Master Excel catalog."""

    def __init__(self, excel_path: Path, output_dir: Path):
        self.excel_path = excel_path
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def derive_partition_from_record_id(record_id: str) -> str:
        """Map Record ID (e.g. G1-0001, G4-0012, N25-0001) to folder partition."""
        rid = record_id.strip().upper()
        if rid.startswith("G1"):
            return "G1"
        elif rid.startswith("G2"):
            return "G2"
        elif rid.startswith("G3"):
            return "G3"
        elif rid.startswith("G4"):
            return "G4"
        elif rid.startswith("N"):
            return "Nyt"
        return "OTHER"

    def load_catalog(self) -> Dict[str, CatalogProduct]:
        """Load catalog products from Excel, keeping string barcodes intact."""
        wb = openpyxl.load_workbook(self.excel_path, data_only=True)
        ws = wb.active
        catalog: Dict[str, CatalogProduct] = {}

        # Rows start at 4
        for r in range(4, ws.max_row + 1):
            raw_bc = ws.cell(r, 1).value
            if not raw_bc:
                continue
            barcode = str(raw_bc).strip()
            # If float e.g. 8850043126456.0, strip decimal
            if barcode.endswith(".0"):
                barcode = barcode[:-2]

            name_en = str(ws.cell(r, 2).value or "").strip()
            brand = str(ws.cell(r, 4).value or "").strip()
            record_id = str(ws.cell(r, 5).value or f"ROW-{r}").strip()
            category = str(ws.cell(r, 8).value or "").strip()
            partition = self.derive_partition_from_record_id(record_id)

            prod = CatalogProduct(
                row_idx=r,
                barcode=barcode,
                record_id=record_id,
                name_en=name_en,
                brand=brand,
                category=category,
                partition=partition,
                demo_image_cell=f"W{r}",
            )
            catalog[record_id] = prod

        return catalog

    def reconcile(
        self,
        scan_results: List[BarcodeScanResult],
        catalog: Optional[Dict[str, CatalogProduct]] = None,
        customer_front_map: Optional[Dict[str, Path]] = None,
        target_partition: Optional[str] = None,
    ) -> ReconciliationSummary:
        """Reconcile scanned barcodes with catalog, resolve sequential pairs and gap analysis."""
        if catalog is None:
            catalog = self.load_catalog()

        # Build reverse lookup by barcode (both full and stripped leading zeros)
        barcode_to_prods: Dict[str, List[CatalogProduct]] = {}
        for prod in catalog.values():
            barcode_to_prods.setdefault(prod.barcode, []).append(prod)
            stripped_bc = prod.barcode.lstrip("0")
            if stripped_bc and stripped_bc != prod.barcode:
                barcode_to_prods.setdefault(stripped_bc, []).append(prod)

        # Index scans by parent directory to resolve sequential shooting pairs
        folder_scans: Dict[Path, List[BarcodeScanResult]] = {}
        for scan in scan_results:
            folder_scans.setdefault(scan.path.parent, []).append(scan)

        # Sort each directory by file name to reconstruct chronological timeline
        for f_path, s_list in folder_scans.items():
            s_list.sort(key=lambda s: s.path.name.lower())

        orphan_photos: List[BarcodeScanResult] = []

        # Process barcode scan results across each folder sequence
        for f_path, s_list in folder_scans.items():
            for idx, scan in enumerate(s_list):
                if not scan.barcodes:
                    continue

                matched_any = False
                for bc in scan.barcodes:
                    matched_prods = barcode_to_prods.get(bc)
                    if not matched_prods:
                        matched_prods = barcode_to_prods.get(bc.lstrip("0"))
                    if not matched_prods:
                        matched_prods = barcode_to_prods.get("0" + bc)

                    if matched_prods:
                        matched_any = True
                        for p in matched_prods:
                            # Register verified back photo
                            if scan.path not in p.verified_back_photos:
                                p.verified_back_photos.append(scan.path)
                                p.status = "MATCHED_BACK"

                            # Detect adjacent non-barcode candidate for sequential pairs
                            front_candidate: Optional[Path] = None
                            if idx > 0 and len(s_list[idx - 1].barcodes) == 0:
                                front_candidate = s_list[idx - 1].path
                            elif idx < len(s_list) - 1 and len(s_list[idx + 1].barcodes) == 0:
                                front_candidate = s_list[idx + 1].path

                            p.suggested_front_candidate = front_candidate

                            # Apply Strategy based on partition and shooting paradigm
                            folder_name = f_path.name.lower()
                            is_carton = "carton" in p.name_en.lower() or "thùng" in p.name_en.lower()

                            if is_carton and "g4" in folder_name:
                                p.strategy = "CARTON_BOX"
                                p.selected_front_photo = front_candidate or scan.path
                                p.barcode_center = None
                            elif "g4" in folder_name and p.partition == "G4" and not front_candidate:
                                # Fresh produce / bagged items (single-surface with barcode on bag)
                                p.strategy = "SINGLE_SURFACE"
                                p.selected_front_photo = scan.path
                                p.barcode_center = None
                            elif front_candidate and ("nyt" in folder_name or "g4" in folder_name):
                                # Candidate Sequential Pair for Nyt & G4
                                p.strategy = "SEQUENTIAL_PAIR"
                                # Leave selected_front_photo empty so Stage 3 verifies with demo ground truth!
                                p.selected_front_photo = None
                                p.barcode_center = None
                            else:
                                # G1, G2, G3 standard dual-hero (both views in 1 photo)
                                if "0380" in scan.path.name or "0381" in scan.path.name or "pranom" in p.name_en.lower():
                                    p.strategy = "STACKED_TUBS_GRID"
                                else:
                                    p.strategy = "STANDARD"
                                if p.selected_front_photo is None:
                                    p.selected_front_photo = scan.path
                                if p.barcode_center is None and bc in scan.barcode_centers:
                                    p.barcode_center = scan.barcode_centers[bc]

                if not matched_any:
                    orphan_photos.append(scan)

        # G1 Chronological Sequence Timeline Interpolation
        g1_folder_key = next((fp for fp in folder_scans if "g1" in fp.name.lower()), None)
        if g1_folder_key and (target_partition == "G1" or not target_partition):
            g1_scans = folder_scans[g1_folder_key]
            g1_prods = [p for p in catalog.values() if p.partition == "G1"]
            g1_prods.sort(key=lambda p: p.row_idx)

            scan_to_prod: Dict[Path, CatalogProduct] = {}
            for s in g1_scans:
                for p in g1_prods:
                    if p.selected_front_photo == s.path:
                        scan_to_prod[s.path] = p
                        break

            interpolated_count = 0
            for i in range(len(g1_scans)):
                s = g1_scans[i]
                if s.path in scan_to_prod:
                    continue
                prev_s, prev_idx = None, -1
                for pi in range(i - 1, -1, -1):
                    if g1_scans[pi].path in scan_to_prod:
                        prev_s, prev_idx = g1_scans[pi], pi
                        break
                next_s, next_idx = None, -1
                for ni in range(i + 1, len(g1_scans)):
                    if g1_scans[ni].path in scan_to_prod:
                        next_s, next_idx = g1_scans[ni], ni
                        break

                if prev_s and next_s:
                    prev_p = scan_to_prod[prev_s.path]
                    next_p = scan_to_prod[next_s.path]
                    scan_gap = next_idx - prev_idx
                    p_between = [p for p in g1_prods if prev_p.row_idx < p.row_idx < next_p.row_idx and not p.selected_front_photo]
                    offset_in_gap = (i - prev_idx) - 1
                    if 0 <= offset_in_gap < len(p_between) and len(p_between) == (scan_gap - 1):
                        target_p = p_between[offset_in_gap]
                        target_p.selected_front_photo = s.path
                        if s.path not in target_p.verified_back_photos:
                            target_p.verified_back_photos.append(s.path)
                        target_p.strategy = "STANDARD"
                        target_p.status = "INTERPOLATED_SEQUENCE"
                        scan_to_prod[s.path] = target_p
                        interpolated_count += 1
            if interpolated_count > 0:
                print(f"[RECONCILER] G1 Chronological Interpolator resolved {interpolated_count} sequence gaps with 100% 1-to-1 uniqueness.")

        # Track all uniquely assigned photos
        assigned_raw_photos: Set[Path] = set()
        for p in catalog.values():
            if p.selected_front_photo:
                assigned_raw_photos.add(p.selected_front_photo)
            for b in p.verified_back_photos:
                assigned_raw_photos.add(b)

        # Separate matched vs missing
        if target_partition:
            total_catalog_count = sum(1 for p in catalog.values() if p.partition == target_partition)
            matched_count = sum(1 for p in catalog.values() if p.verified_back_photos and p.partition == target_partition)
            missing_products = [p for p in catalog.values() if not p.verified_back_photos and p.partition == target_partition]
        else:
            total_catalog_count = len(catalog)
            matched_count = sum(1 for p in catalog.values() if p.verified_back_photos)
            missing_products = [p for p in catalog.values() if not p.verified_back_photos]

        missing_count = len(missing_products)

        # Write missing report
        report_path = self.output_dir / "Zohanubis_Missing_SKU_Report.xlsx"
        self._write_missing_report(
            report_path,
            missing_products,
            customer_front_map=customer_front_map,
        )

        return ReconciliationSummary(
            total_catalog_rows=total_catalog_count,
            matched_count=matched_count,
            missing_count=missing_count,
            orphan_count=len(orphan_photos),
            missing_report_path=report_path,
            catalog_products=catalog,
            orphan_photos=orphan_photos,
            assigned_photos=assigned_raw_photos,
        )

    def _write_missing_report(
        self,
        report_path: Path,
        missing_products: List[CatalogProduct],
        customer_front_map: Optional[Dict[str, Path]] = None,
    ) -> None:
        """Create a styled Excel spreadsheet detailing all unphotographed or missing SKUs."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Missing SKUs"

        headers = [
            "Record ID",
            "Barcode",
            "Product Name (EN)",
            "Brand",
            "Category",
            "Source Partition",
            "Issue Reason",
            "Recommended Action",
        ]
        ws.append(headers)

        # Header styling
        header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        thin_border = Border(
            left=Side(style="thin", color="D9D9D9"),
            right=Side(style="thin", color="D9D9D9"),
            top=Side(style="thin", color="D9D9D9"),
            bottom=Side(style="thin", color="D9D9D9"),
        )

        for col_num in range(1, len(headers) + 1):
            cell = ws.cell(1, col_num)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

        ws.row_dimensions[1].height = 28

        for idx, p in enumerate(missing_products, start=2):
            is_cust = False
            if customer_front_map:
                bc = p.barcode.strip()
                if bc in customer_front_map or bc.lstrip("0") in customer_front_map or ("0" + bc) in customer_front_map:
                    is_cust = True

            if is_cust:
                reason = "No raw studio photo found; Customer provided front packshot"
                action = "Front packshot ready for webshop. Customer to provide back photo if needed."
            else:
                reason = "No raw photo found with readable barcode"
                action = "Customer to provide photography (both Front and Back) for this SKU"

            ws.append([
                p.record_id,
                p.barcode,
                p.name_en,
                p.brand,
                p.category,
                p.partition,
                reason,
                action,
            ])
            ws.row_dimensions[idx].height = 20
            # format barcode cell as text
            ws.cell(idx, 2).number_format = "@"

            # alternating fill
            fill_color = "F2F5F9" if idx % 2 == 0 else "FFFFFF"
            row_fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type="solid")
            for col_idx in range(1, len(headers) + 1):
                c = ws.cell(idx, col_idx)
                c.fill = row_fill
                c.border = thin_border
                c.font = Font(name="Calibri", size=10)

        # Set column widths
        col_widths = {1: 14, 2: 18, 3: 45, 4: 20, 5: 18, 6: 18, 7: 35, 8: 45}
        for col_idx, width in col_widths.items():
            col_letter = openpyxl.utils.get_column_letter(col_idx)
            ws.column_dimensions[col_letter].width = width

        wb.save(report_path)
