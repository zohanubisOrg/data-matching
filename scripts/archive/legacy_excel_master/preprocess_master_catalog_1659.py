import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import openpyxl
import re

def is_valid_gs1_barcode(bc: str) -> bool:
    if not bc or not bc.isdigit():
        return False
    if len(bc) not in (8, 12, 13, 14):
        return False
    digits = [int(c) for c in bc]
    body = digits[:-1]
    check_digit = digits[-1]
    total = 0
    # Modulo-10 weights: from right to left (excluding check digit), alternates 3, 1, 3, 1...
    for i, d in enumerate(reversed(body)):
        weight = 3 if i % 2 == 0 else 1
        total += d * weight
    calc_check = (10 - (total % 10)) % 10
    return calc_check == check_digit

def normalize_barcode(val) -> str:
    if val is None:
        return ""
    val_str = str(val).strip()
    if val_str.endswith(".0"):
        val_str = val_str[:-2]
    val_str = re.sub(r'[\r\n\t]', '', val_str)
    return val_str

def preprocess_catalog():
    src_file = "source-import/new_source_from_customer/11-10-new-requirment/Esbjerg_Asian_Market_Master_1659_updated.xlsx"
    out_dir = "output/reconciliation"
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "Master_1659_Reconciled_Clean.xlsx")

    print(f"[*] Loading source master: {src_file}")
    wb = openpyxl.load_workbook(src_file, data_only=True)
    sheet = wb.active

    rows = list(sheet.iter_rows(values_only=False))
    # Rows 1 & 2 are titles/descriptions, row 3 is headers
    header_row = [cell.value for cell in rows[2]]
    data_rows = rows[3:]
    print(f"    Total rows in file: {len(data_rows)}")

    # Column index mapping (0-based)
    c_stt = 0        # STT
    c_bc = 2         # Barcode
    c_en = 3         # Full name (EN)
    c_da = 4         # Fuldt navn (DA)
    c_cat_pos = 86   # Category Name (Col 87)
    c_price = 87     # Price (Col 88)
    c_sku = 88       # SKU (Col 89)
    c_online = 91    # Trạng thái Online (Col 92)
    c_code3 = 92     # Mã nhóm 3 ký tự (Col 93)
    c_img_cdn = 93   # Link ảnh CDN Shopify (Col 94)
    c_l1 = 96        # Category Level 1 (Col 97)
    c_l2 = 97        # Category Level 2 (Col 98)

    # Imputation rules for the 4 known incomplete rows
    imputations = 0
    gs1_valid_cnt = 0
    total_with_bc = 0

    for idx, r in enumerate(data_rows):
        stt = r[c_stt].value
        raw_bc = r[c_bc].value
        clean_bc = normalize_barcode(raw_bc)
        r[c_bc].value = clean_bc

        if clean_bc:
            total_with_bc += 1
            if is_valid_gs1_barcode(clean_bc):
                gs1_valid_cnt += 1

        val_l1 = r[c_l1].value
        val_l2 = r[c_l2].value

        # Impute missing L1/L2
        if stt == 9 or clean_bc == "8852023664248":
            r[c_l1].value = "Snack"
            r[c_l2].value = "Nuts & Seeds"
            imputations += 1
        elif stt == 938 or clean_bc == "8850521950665":
            r[c_l1].value = "Bønner"
            r[c_l2].value = "Beans & Pulses"
            imputations += 1
        elif stt == 1458:
            r[c_l1].value = "Diverse"
            r[c_l2].value = "Other Asian Specialties"
            imputations += 1
        elif stt == 1621:
            r[c_l1].value = "Diverse"
            r[c_l2].value = "Other Asian Specialties"
            imputations += 1
        elif not val_l1 or not val_l2:
            # Fallback safe imputation based on Category Name
            cat_name = str(r[c_cat_pos].value or "").strip()
            if not val_l1:
                r[c_l1].value = cat_name if cat_name else "Diverse"
            if not val_l2:
                r[c_l2].value = f"General {r[c_l1].value}"
            imputations += 1

    # Verify no null values in Level 1 and Level 2
    missing_l1_after = sum(1 for r in data_rows if not r[c_l1].value or str(r[c_l1].value).strip() == "")
    missing_l2_after = sum(1 for r in data_rows if not r[c_l2].value or str(r[c_l2].value).strip() == "")

    print(f"[+] Total imputations applied: {imputations}")
    print(f"[+] Post-check: Missing Category Level 1 = {missing_l1_after}")
    print(f"[+] Post-check: Missing Category Level 2 = {missing_l2_after}")
    print(f"[+] GS1 Modulo-10 Barcodes: {gs1_valid_cnt}/{total_with_bc} valid ({gs1_valid_cnt/total_with_bc*100:.1f}%)")

    assert missing_l1_after == 0, "Level 1 still has missing values!"
    assert missing_l2_after == 0, "Level 2 still has missing values!"

    print(f"[*] Saving cleaned master workbook to: {out_file}")
    wb.save(out_file)
    print("[+] Successfully preprocessed and saved clean master!")

if __name__ == "__main__":
    preprocess_catalog()
