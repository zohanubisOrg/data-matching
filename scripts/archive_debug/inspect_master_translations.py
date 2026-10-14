import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import pandas as pd

for path, hdr in [
    ('output/shopify_import_final/Master_All_Products_89cols_With_Images.xlsx', 2),
    ('output/shopify_import_final/Master_All_1659_Products_With_Images.xlsx', 2),
    ('customer-send-me.xlsx', 1)
]:
    if os.path.exists(path):
        df = pd.read_excel(path, header=hdr, nrows=5)
        print(f"\n==================== FILE: {path} (Header={hdr}) ====================")
        print("Columns:", [str(c) for c in df.columns if not str(c).startswith('Unnamed')])
        sample_row = df.iloc[0].to_dict()
        print("\nSample row keys & values:")
        for k, v in sample_row.items():
            if not str(k).startswith('Unnamed') and pd.notna(v):
                print(f"  • {k}: {str(v)[:70]}")
