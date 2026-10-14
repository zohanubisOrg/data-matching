import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import re
import pandas as pd

def clean_bc(x):
    if pd.isna(x) or not x:
        return ''
    s = str(x).strip()
    if s.endswith('.0'):
        s = s[:-2]
    m = re.search(r'(\d{6,14})', s)
    if m:
        return m.group(1).lstrip('0')
    return s.lstrip('0')

def main():
    df_audit = pd.read_excel('output/reconciliation/Shopify_Live_Catalog_Full_Audit.xlsx')
    missing_sku = df_audit[df_audit['SKU_Audit_Status'] == 'MISSING'].copy()
    print(f"Total products missing SKU on Shopify: {len(missing_sku)}")

    # Load 1659 master with header=2
    df_1659 = pd.read_excel('output/shopify_import_final/Master_All_1659_Products_With_Images.xlsx', header=2, dtype=str)
    print(f"Loaded Master 1659 rows: {len(df_1659)}")
    
    # Map by barcode
    lookup_1659 = {}
    for idx, row in df_1659.iterrows():
        raw_bc = row.get('Barcode')
        cbc = clean_bc(raw_bc)
        if cbc:
            lookup_1659[cbc] = row

    print(f"Indexed {len(lookup_1659)} clean barcodes from Master 1659")

    matched_count = 0
    match_details = []

    for idx, r in missing_sku.iterrows():
        pid = r['Product_ID']
        vid = r['Variant_ID']
        live_title = r['Title']
        raw_bc = str(r['Variant_Barcode'])
        cbc = clean_bc(raw_bc)
        
        if not cbc:
            m = re.search(r'(\d{6,14})', str(live_title))
            if m:
                cbc = clean_bc(m.group(1))

        if cbc in lookup_1659:
            matched_count += 1
            m = lookup_1659[cbc]
            da_title = str(m.get('Fuldt navn (DA)', '')).strip()
            en_title = str(m.get('Full name (EN)', '')).strip()
            brand = str(m.get('Brand', 'Asiatisk')).strip()
            category = str(m.get('Category (editorial)', 'Diverse')).strip()
            rec_id = str(m.get('Record ID', f'POS-{cbc[-4:]}')).strip()
            
            final_title = da_title if da_title and da_title != 'nan' else (en_title if en_title and en_title != 'nan' else live_title)
            final_sku = rec_id if rec_id and rec_id != 'nan' else f"SKU-{cbc}"
            
            # Format clean standard barcode (padded back or clean)
            std_bc = str(m.get('Barcode', raw_bc)).strip()
            if std_bc.endswith('.0'):
                std_bc = std_bc[:-2]

            match_details.append({
                "Product_ID": pid,
                "Variant_ID": vid,
                "Old_Title": live_title,
                "New_Title": final_title,
                "Clean_Barcode": std_bc,
                "New_SKU": final_sku,
                "Brand": brand,
                "Category": category,
                "Tags": f"{category}, {final_sku[:3]}, {brand}",
                "Source": "Master_1659"
            })
        else:
            # Generate clean fallback for any residual items
            std_bc = raw_bc
            if std_bc.endswith('.0'):
                std_bc = std_bc[:-2]
            
            match_details.append({
                "Product_ID": pid,
                "Variant_ID": vid,
                "Old_Title": live_title,
                "New_Title": live_title,
                "Clean_Barcode": std_bc,
                "New_SKU": f"POS-{std_bc[-6:] if len(std_bc) >= 6 else std_bc}",
                "Brand": "Asiatisk",
                "Category": "Diverse",
                "Tags": "Diverse, POS, Asiatisk",
                "Source": "Fallback_Standardization"
            })

    df_matches = pd.DataFrame(match_details)
    print(f"\nResult: {matched_count}/{len(missing_sku)} matched directly with Master 1659. {len(missing_sku) - matched_count} standardized with POS SKU schema.")
    print("Sample 5 records to update:")
    for _, item in df_matches.head(5).iterrows():
        print(f" - ID: {item['Product_ID']} | SKU: {item['New_SKU']} | Barcode: {item['Clean_Barcode']} | Title: {item['New_Title']}")

    df_matches.to_excel("output/reconciliation/Resolved_95_Missing_SKUs.xlsx", index=False)
    print("\nSaved mapping to output/reconciliation/Resolved_95_Missing_SKUs.xlsx")

if __name__ == "__main__":
    main()
