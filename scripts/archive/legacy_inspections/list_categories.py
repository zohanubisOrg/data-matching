import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import pandas as pd

df = pd.read_excel("output/reconciliation/Master_1659_Reconciled_Clean.xlsx")
print("Columns:", [str(c) for c in df.columns])

# find category columns
cat1_col = [c for c in df.columns if "1" in str(c) or "Level 1" in str(c) or "Nhóm" in str(c)][0]
cat2_col = [c for c in df.columns if "2" in str(c) or "Level 2" in str(c) or "Chi tiết" in str(c)][0]
print(f"Using cat1: {cat1_col}, cat2: {cat2_col}")

grouped = df.groupby([cat1_col, cat2_col]).size().reset_index(name="count")
for idx, r in grouped.iterrows():
    print(f"{r[cat1_col]} -> {r[cat2_col]} ({r['count']})")
