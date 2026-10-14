# -*- coding: utf-8 -*-
import sys
import os
import glob
import json

sys.stdout.reconfigure(encoding="utf-8")

for f in glob.glob("output/**/*.json", recursive=True):
    sz = os.path.getsize(f)
    print(f"{f} : {sz:,} bytes")
