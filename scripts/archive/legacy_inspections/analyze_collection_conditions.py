import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import pandas as pd

df = pd.read_excel('output/reconciliation/Shopify_Live_Catalog_Full_Audit.xlsx')

print("=========================================================")
print("          CHI TIẾT PHÂN BỔ PRODUCT TYPE TRÊN STORE       ")
print("=========================================================")
type_counts = df['Product_Type'].value_counts()
for p_type, count in type_counts.items():
    print(f"  • Type = '{p_type}': {count} sản phẩm")

print("\n=========================================================")
print("          CÁC TAG PHỔ BIẾN THEO TỪNG NHÓM HÀNG           ")
print("=========================================================")
for p_type in ['Saucer', 'Snack', 'Nudler', 'Krydderier', 'Drikker', 'Diverse', 'Konserves']:
    subset = df[df['Product_Type'] == p_type]
    tags = []
    for t in subset['Tags'].dropna():
        tags.extend([x.strip() for x in str(t).split(',') if x.strip()])
    top_tags = pd.Series(tags).value_counts().head(8)
    print(f"\n[Nhóm {p_type} - {len(subset)} sản phẩm]:")
    for t_name, t_cnt in top_tags.items():
        print(f"    - Tag '{t_name}': {t_cnt} sản phẩm")
