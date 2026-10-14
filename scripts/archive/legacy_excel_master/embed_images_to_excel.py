# -*- coding: utf-8 -*-
import os
import sys
import re
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.drawing.image import Image as OpenpyxlImage
from openpyxl.utils import get_column_letter
from PIL import Image as PILImage
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

OUTPUT_DIR = r"D:\Work\shopify\output\shopify_import_final"
THUMBS_DIR = os.path.join(OUTPUT_DIR, "excel_thumbnails")

HEADER_FILL = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
REGULAR_FONT = Font(name="Calibri", size=10)
BORDER_THIN = Side(border_style="thin", color="D9D9D9")
CELL_BORDER = Border(left=BORDER_THIN, right=BORDER_THIN, top=BORDER_THIN, bottom=BORDER_THIN)


def embed_images_in_file(xlsx_path, barcode_col_name, image_col_name, cols_to_remove, output_path):
    print(f"\nProcessing {os.path.basename(xlsx_path)}...")
    df = pd.read_excel(xlsx_path)

    # Drop unwanted text image/filename columns
    for col in cols_to_remove:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Reorder columns so Image column is near the front (Column B)
    cols = list(df.columns)
    if image_col_name in cols:
        cols.remove(image_col_name)

    # Insert Image column right after Barcode or as Column B
    if barcode_col_name in cols:
        bc_idx = cols.index(barcode_col_name)
        cols.insert(bc_idx + 1, image_col_name)
    else:
        cols.insert(1, image_col_name)

    df_reordered = df.reindex(columns=cols)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Products"
    ws.views.sheetView[0].showGridLines = True

    # Write headers
    headers = list(df_reordered.columns)
    ws.append(headers)

    # Format header row
    ws.row_dimensions[1].height = 28
    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(1, col_num)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    img_col_idx = headers.index(image_col_name) + 1
    img_col_letter = get_column_letter(img_col_idx)
    bc_col_idx = headers.index(barcode_col_name) + 1

    # Write data rows
    for r_idx, row in enumerate(df_reordered.itertuples(index=False), start=2):
        row_values = list(row)
        # Leave image cell empty so only the embedded picture is shown
        row_values[img_col_idx - 1] = None
        ws.append(row_values)

        # Row height for nice thumbnail display
        ws.row_dimensions[r_idx].height = 100

        # Apply cell styling
        for c_idx in range(1, len(headers) + 1):
            c = ws.cell(r_idx, c_idx)
            c.font = REGULAR_FONT
            c.border = CELL_BORDER
            c.alignment = Alignment(vertical="center")

        # Center specific columns like Barcode, SKU, Price, Image
        ws.cell(r_idx, img_col_idx).alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(r_idx, bc_col_idx).alignment = Alignment(horizontal="center", vertical="center")

        # Embed Image
        raw_bc = str(getattr(row, barcode_col_name) or "").strip()
        if raw_bc.endswith(".0"):
            raw_bc = raw_bc[:-2]
        clean_bc = raw_bc.lstrip("0")

        thumb_file = None
        for cand in [f"{raw_bc}.jpg", f"{clean_bc}.jpg"]:
            cand_p = os.path.join(THUMBS_DIR, cand)
            if os.path.exists(cand_p):
                thumb_file = cand_p
                break

        if thumb_file:
            try:
                with PILImage.open(thumb_file) as pimg:
                    pw, ph = pimg.size

                scale = min(120.0 / pw, 120.0 / ph)
                tw = max(30, int(pw * scale))
                th = max(30, int(ph * scale))

                xl_img = OpenpyxlImage(thumb_file)
                xl_img.width = tw
                xl_img.height = th
                xl_img.anchor = f"{img_col_letter}{r_idx}"
                ws.add_image(xl_img)
            except Exception as e:
                pass

    # Auto column width
    for col_idx, col_name in enumerate(headers, start=1):
        col_letter = get_column_letter(col_idx)
        if col_idx == img_col_idx:
            ws.column_dimensions[col_letter].width = 20.0
        else:
            max_len = len(str(col_name))
            for r in range(2, min(len(df_reordered) + 2, 50)):
                v = ws.cell(r, col_idx).value
                if v:
                    max_len = max(max_len, min(len(str(v)), 40))
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    try:
        wb.save(output_path)
        print(f"Successfully saved clean file: {output_path}")
    except PermissionError:
        base, ext = os.path.splitext(output_path)
        fallback = f"{base}_Clean{ext}"
        wb.save(fallback)
        print(f"File was open in Excel. Saved fallback to: {fallback}")


def main():
    # 1. Master Online Products
    master_in = os.path.join(OUTPUT_DIR, "Master_Online_Products_Consolidated.xlsx")
    embed_images_in_file(
        xlsx_path=master_in,
        barcode_col_name="Barcode",
        image_col_name="Ảnh sản phẩm (Image)",
        cols_to_remove=["Image Filename", "Image URL", "Image File", "Has Image"],
        output_path=master_in,
    )

    # 2. All 1350 POS Products
    pos_all_in = os.path.join(OUTPUT_DIR, "POS_Active_All_1350_Products.xlsx")
    embed_images_in_file(
        xlsx_path=pos_all_in,
        barcode_col_name="Barcode",
        image_col_name="Ảnh sản phẩm (Image)",
        cols_to_remove=["Image Filename", "Image URL", "Image File", "Has Image"],
        output_path=pos_all_in,
    )


if __name__ == "__main__":
    main()
