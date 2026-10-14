import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
import pandas as pd
df = pd.read_excel("output/reconciliation/Master_1659_Reconciled_Clean.xlsx", header=0)
print("Raw columns:", df.columns.tolist()[:15])
if "STT" in df.iloc[0].values:
    # Header was row 0 or 1
    print("Row 0:", df.iloc[0].dropna().tolist()[:10])
    df.columns = df.iloc[0]
    df = df[1:]
    print("New columns:", df.columns.tolist()[:15])

# Print columns matching Category
cat_cols = [c for c in df.columns if "Category" in str(c) or "Level" in str(c) or "Nhóm" in str(c)]
print("Category columns:", cat_cols)
for c in cat_cols:
    print(c, "unique values count:", df[c].nunique())
    print("Sample:", df[c].dropna().unique()[:5])
