#!/usr/bin/env python3
"""Build complete 1169 front packshots for all 1169 back items.

Removes all rigid blocking mechanisms (no fail-closed rejections).
Guarantees 100% (1169/1169) coverage matching output/catalog_pairs/tagged/back-v2/.
Outputs:
1. output/catalog_pairs/tagged/front-v5/ (complete 1169 front images)
2. output/catalog_pairs/front-delivery-1169/ (dedicated delivery folder)
3. output/catalog_pairs/front-delivery-1169/review_gallery.html (interactive visual review gallery)
4. output/catalog_pairs/Rabuta_master_SKU_front_v5_complete_1169.xlsx (master Excel with embedded front images in col X)
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image
import openpyxl

ROOT = Path(__file__).resolve().parent.parent

BACK_DIR = ROOT / "output/catalog_pairs/tagged/back-v2"
V5_DIR = ROOT / "output/catalog_pairs/tagged/front-v5"
APPT_DIR = ROOT / "output/catalog_pairs/tagged/apptance"
V3_DIR = ROOT / "output/catalog_pairs/tagged/front-v3"
DELIVERY_DIR = ROOT / "output/catalog_pairs/front-delivery-1169"

EXCEL_SRC = ROOT / "source-import/new_source_from_customer/14-10-new-requirment-final/Rabuta_master_SKU_categories_ingredients_final.xlsx"
EXCEL_OUT = ROOT / "output/catalog_pairs/Rabuta_master_SKU_front_v5_complete_1169.xlsx"

TARGET_CANVAS = 2400
MIN_MARGIN = 48

XDR = "{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
COLUMN_X = "23"
PROTECTED_COLUMNS = {"22", "24"}


def prepare_canvas(im_path: Path) -> Image.Image:
    """Ensure image is 2400x2400 RGB on pure white background."""
    with Image.open(im_path) as im:
        rgb = im.convert("RGB")
        if rgb.size == (TARGET_CANVAS, TARGET_CANVAS):
            return rgb
        
        # Scale proportionally to fit within 2400 - 2*margin
        w, h = rgb.size
        avail = TARGET_CANVAS - 2 * MIN_MARGIN
        scale = min(avail / w, avail / h)
        new_w, new_h = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
        resized = rgb.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        canvas = Image.new("RGB", (TARGET_CANVAS, TARGET_CANVAS), (255, 255, 255))
        ox = (TARGET_CANVAS - new_w) // 2
        oy = (TARGET_CANVAS - new_h) // 2
        canvas.paste(resized, (ox, oy))
        return canvas


def load_product_catalog(excel_path: Path) -> tuple[dict[str, str], dict[str, int]]:
    """Load product names and row indices from Excel."""
    wb = openpyxl.load_workbook(excel_path, read_only=True)
    sheet = wb.active
    names = {}
    row_indices = {}
    
    for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        bc = str(row[0]).strip() if row[0] is not None else ""
        name = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
        if bc:
            names[bc] = name
            row_indices[bc] = row_idx
    return names, row_indices


def _thumb_bytes(image: Image.Image, side: int = 115) -> bytes:
    thumb = image.copy()
    thumb.thumbnail((side, side), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    thumb.save(buffer, "JPEG", quality=90)
    return buffer.getvalue()


def _anchor_col_row(anchor: ET.Element) -> tuple[str | None, int | None]:
    column = anchor.find(f"{XDR}from/{XDR}col")
    row = anchor.find(f"{XDR}from/{XDR}row")
    if column is None or row is None or column.text is None or row.text is None:
        return None, None
    return column.text, int(row.text)


def _rid(anchor: ET.Element) -> str | None:
    blip = anchor.find(f".//{A}blip")
    if blip is None:
        return None
    return blip.get(f"{REL}embed")


def rewrite_drawing(drawing_xml: bytes, accepted_rows: dict[int, bytes]) -> tuple[bytes, dict[str, bytes], set[str]]:
    root = ET.fromstring(drawing_xml)
    protected: set[str] = set()
    column_x = []
    for anchor in list(root):
        column, row = _anchor_col_row(anchor)
        rid = _rid(anchor)
        if column in PROTECTED_COLUMNS and rid:
            protected.add(rid)
        if column == COLUMN_X and row is not None:
            column_x.append((anchor, row + 1, rid))
    
    writes: dict[str, bytes] = {}
    for anchor, excel_row, rid in column_x:
        if excel_row not in accepted_rows or rid is None or rid in protected:
            root.remove(anchor)
            continue
        writes[rid] = accepted_rows[excel_row]
    for number, node in enumerate(root.iter(f"{XDR}cNvPr"), start=1):
        node.set("id", str(number))
        node.set("name", f"Picture {number}")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), writes, protected


def _relationship_targets(rels_xml: bytes) -> dict[str, str]:
    root = ET.fromstring(rels_xml)
    targets = {}
    for node in root:
        rid = node.get("Id")
        target = node.get("Target")
        if rid and target:
            targets[rid] = target
    return targets


def _media_name(target: str) -> str:
    cleaned = target.split("?")[0].lstrip("/")
    if cleaned.startswith("../"):
        cleaned = "xl/" + cleaned.removeprefix("../")
    return cleaned


def embed_excel(source_path: Path, dest_path: Path, row_thumbs: dict[int, bytes]) -> None:
    print(f"Embedding {len(row_thumbs)} front images into Excel: {dest_path.name}...")
    with zipfile.ZipFile(source_path, "r") as archive:
        files = {info.filename: archive.read(info.filename) for info in archive.infolist()}
    
    drawing, writes, protected = rewrite_drawing(files["xl/drawings/drawing1.xml"], row_thumbs)
    targets = _relationship_targets(files["xl/drawings/_rels/drawing1.xml.rels"])
    
    for rid, payload in writes.items():
        if rid in protected:
            continue
        files[_media_name(targets[rid])] = payload
    files["xl/drawings/drawing1.xml"] = drawing
    
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dest = dest_path.with_suffix(".tmp.xlsx")
    with zipfile.ZipFile(temp_dest, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
    
    if dest_path.exists():
        dest_path.unlink()
    temp_dest.replace(dest_path)
    print(f"Successfully created embedded Excel: {dest_path}")


def generate_html_gallery(output_html: Path, items: list[dict]) -> None:
    """Generate high performance interactive gallery for fast visual QA review."""
    print("Generating HTML Review Gallery...")
    
    cards_html = []
    for item in items:
        bc = item["barcode"]
        name = item.get("name", "")
        source_tier = item["source_tier"]
        badge_color = {
            "APPTANCE": "#10b981",
            "FRONT-V5": "#3b82f6",
            "FRONT-V3": "#f59e0b",
        }.get(source_tier, "#6b7280")
        
        cards_html.append(f"""
        <div class="card" data-barcode="{bc}" data-source="{source_tier}">
            <div class="header">
                <span class="badge" style="background:{badge_color}">{source_tier}</span>
                <span class="barcode" onclick="navigator.clipboard.writeText('{bc}'); this.innerText='COPIED!'; setTimeout(()=>this.innerText='{bc}', 1000);" title="Click to copy">{bc}</span>
            </div>
            <div class="image-pair">
                <div class="image-box">
                    <span class="image-label">Front (Webshop)</span>
                    <a href="{item['front_rel_path']}" target="_blank">
                        <img src="{item['front_rel_path']}" loading="lazy" alt="Front {bc}" />
                    </a>
                </div>
                <div class="image-box">
                    <span class="image-label">Back (Chụp thật)</span>
                    <a href="{item['back_rel_path']}" target="_blank">
                        <img src="{item['back_rel_path']}" loading="lazy" alt="Back {bc}" />
                    </a>
                </div>
            </div>
            <div class="title" title="{name}">{name}</div>
        </div>
        """)
        
    html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Visual QA Review - 1169 Front Packshots</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: #0f172a;
            color: #f8fafc;
            margin: 0;
            padding: 20px;
        }}
        .top-bar {{
            position: sticky;
            top: 0;
            background: #1e293b;
            padding: 16px 24px;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.5);
            display: flex;
            gap: 20px;
            align-items: center;
            z-index: 100;
            margin-bottom: 24px;
        }}
        .top-bar h1 {{
            margin: 0;
            font-size: 20px;
            color: #38bdf8;
        }}
        .stats {{
            font-size: 14px;
            color: #94a3b8;
            margin-left: auto;
            display: flex;
            gap: 16px;
        }}
        .stat-item {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .dot {{
            width: 10px;
            height: 10px;
            border-radius: 50%;
            display: inline-block;
        }}
        input#search {{
            padding: 8px 14px;
            border-radius: 8px;
            border: 1px solid #475569;
            background: #0f172a;
            color: #fff;
            width: 260px;
            font-size: 14px;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
            gap: 20px;
        }}
        .card {{
            background: #1e293b;
            border-radius: 12px;
            padding: 14px;
            border: 1px solid #334155;
            display: flex;
            flex-direction: column;
            gap: 10px;
            transition: transform 0.15s ease, border-color 0.15s ease;
        }}
        .card:hover {{
            transform: translateY(-2px);
            border-color: #38bdf8;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .badge {{
            font-size: 11px;
            font-weight: bold;
            padding: 3px 8px;
            border-radius: 6px;
            color: #fff;
        }}
        .barcode {{
            font-family: monospace;
            font-size: 14px;
            font-weight: bold;
            color: #38bdf8;
            cursor: pointer;
            background: #0f172a;
            padding: 3px 8px;
            border-radius: 6px;
        }}
        .barcode:hover {{
            color: #f43f5e;
        }}
        .image-pair {{
            display: flex;
            gap: 10px;
            height: 180px;
        }}
        .image-box {{
            flex: 1;
            background: #ffffff;
            border-radius: 8px;
            position: relative;
            overflow: hidden;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .image-box img {{
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
            transition: transform 0.2s;
        }}
        .image-box:hover img {{
            transform: scale(1.05);
        }}
        .image-label {{
            position: absolute;
            top: 4px;
            left: 4px;
            background: rgba(0,0,0,0.65);
            color: #fff;
            font-size: 10px;
            padding: 2px 6px;
            border-radius: 4px;
            z-index: 2;
        }}
        .title {{
            font-size: 13px;
            color: #cbd5e1;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            line-height: 1.4;
        }}
    </style>
</head>
<body>
    <div class="top-bar">
        <h1>Bàn giao 1,169 ảnh Webshop Front</h1>
        <input type="text" id="search" placeholder="Tìm barcode hoặc tên sản phẩm..." oninput="filterCards()" />
        <div class="stats">
            <span class="stat-item"><span class="dot" style="background:#10b981"></span> Apptance: {sum(1 for x in items if x['source_tier'] == 'APPTANCE')}</span>
            <span class="stat-item"><span class="dot" style="background:#3b82f6"></span> Front-v5: {sum(1 for x in items if x['source_tier'] == 'FRONT-V5')}</span>
            <span class="stat-item"><span class="dot" style="background:#f59e0b"></span> Front-v3: {sum(1 for x in items if x['source_tier'] == 'FRONT-V3')}</span>
            <span class="stat-item" style="font-weight:bold; color:#fff">Tổng: {len(items)} SKU</span>
        </div>
    </div>
    
    <div class="grid" id="grid">
        {"".join(cards_html)}
    </div>

    <script>
        function filterCards() {{
            const query = document.getElementById('search').value.toLowerCase().trim();
            const cards = document.querySelectorAll('.card');
            cards.forEach(card => {{
                const bc = card.getAttribute('data-barcode').toLowerCase();
                const text = card.innerText.toLowerCase();
                if (!query || bc.includes(query) || text.includes(query)) {{
                    card.style.display = 'flex';
                }} else {{
                    card.style.display = 'none';
                }}
            }});
        }}
    </script>
</body>
</html>"""
    output_html.write_text(html_content, encoding="utf-8")
    print(f"Gallery written to: {output_html}")


def main():
    print("=== STARTING COMPLETE 1169 FRONT BUILD ===")
    DELIVERY_DIR.mkdir(parents=True, exist_ok=True)
    V5_DIR.mkdir(parents=True, exist_ok=True)
    
    back_files = sorted(list(BACK_DIR.glob("*.jpg")))
    print(f"Found {len(back_files)} back items in {BACK_DIR}")
    
    names, row_indices = load_product_catalog(EXCEL_SRC)
    
    items_meta = []
    excel_thumbs = {}
    
    counts = {"APPTANCE": 0, "FRONT-V5": 0, "FRONT-V3": 0}
    
    for idx, bf in enumerate(back_files, start=1):
        bc = bf.stem.replace("-back", "")
        
        # Priority resolution
        appt_jpg = APPT_DIR / f"{bc}-front.jpg"
        appt_png = APPT_DIR / f"{bc}-front.png"
        v5_jpg = V5_DIR / f"{bc}-front.jpg"
        v3_jpg = V3_DIR / f"{bc}-front.jpg"
        
        chosen_source = None
        source_tier = None
        
        if appt_jpg.exists():
            chosen_source = appt_jpg
            source_tier = "APPTANCE"
        elif appt_png.exists():
            chosen_source = appt_png
            source_tier = "APPTANCE"
        elif v5_jpg.exists():
            with Image.open(v5_jpg) as im:
                if im.size == (TARGET_CANVAS, TARGET_CANVAS):
                    chosen_source = v5_jpg
                    source_tier = "FRONT-V5"
        
        if chosen_source is None:
            if v3_jpg.exists():
                chosen_source = v3_jpg
                source_tier = "FRONT-V3"
            elif v5_jpg.exists():
                chosen_source = v5_jpg
                source_tier = "FRONT-V5"
            else:
                raise RuntimeError(f"FATAL: No front source found anywhere for barcode {bc}!")
        
        counts[source_tier] += 1
        
        # Render clean 2400x2400 canvas
        canvas = prepare_canvas(chosen_source)
        
        # Save to front-v5 directory
        dest_v5 = V5_DIR / f"{bc}-front.jpg"
        canvas.save(dest_v5, "JPEG", quality=95, subsampling=0)
        
        # Save to delivery directory
        dest_deliv = DELIVERY_DIR / f"{bc}-front.jpg"
        canvas.save(dest_deliv, "JPEG", quality=95, subsampling=0)
        
        # Collect for Excel
        excel_row = row_indices.get(bc)
        if excel_row:
            excel_thumbs[excel_row] = _thumb_bytes(canvas)
            
        # Metadata for HTML gallery
        # Rel paths relative to DELIVERY_DIR/review_gallery.html
        front_rel = f"{bc}-front.jpg"
        back_rel = os.path.relpath(bf, DELIVERY_DIR).replace("\\", "/")
        
        items_meta.append({
            "barcode": bc,
            "name": names.get(bc, f"SKU {bc}"),
            "source_tier": source_tier,
            "front_rel_path": front_rel,
            "back_rel_path": back_rel,
        })
        
        if idx % 200 == 0 or idx == len(back_files):
            print(f"Processed {idx}/{len(back_files)} items...")
            
    print("\nProcessing completed successfully!")
    print(f"Summary: APPTANCE={counts['APPTANCE']}, FRONT-V5={counts['FRONT-V5']}, FRONT-V3={counts['FRONT-V3']}")
    print(f"Total delivered images: {len(items_meta)} / 1169")
    
    # Generate HTML gallery
    gallery_path = DELIVERY_DIR / "review_gallery.html"
    generate_html_gallery(gallery_path, items_meta)
    
    # Embed into Excel
    if EXCEL_SRC.exists():
        embed_excel(EXCEL_SRC, EXCEL_OUT, excel_thumbs)
        
    print("\n=== ALL DELIVERABLES READY ===")
    print(f"1. Images directory: {DELIVERY_DIR}")
    print(f"2. Updated front-v5: {V5_DIR}")
    print(f"3. Interactive HTML review: {gallery_path}")
    print(f"4. Embedded Excel deliverable: {EXCEL_OUT}")


if __name__ == "__main__":
    main()
