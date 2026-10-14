import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import pandas as pd

for h in [1, 2, 3]:
    df = pd.read_excel('output/shopify_import_final/Master_All_1659_Products_With_Images.xlsx', header=h, nrows=2)
    print(f"\n--- Header={h} ---")
    cols = [str(c) for c in df.columns[:15]]
    print("Cols:", cols)
