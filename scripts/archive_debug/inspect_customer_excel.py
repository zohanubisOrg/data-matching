import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import pandas as pd

for h in range(5):
    try:
        df = pd.read_excel('customer-send-me.xlsx', header=h, nrows=2)
        print(f"Header {h} cols:", [str(c) for c in df.columns[:10]])
    except Exception as e:
        print(f"Header {h} error:", e)
