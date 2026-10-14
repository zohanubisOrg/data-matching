# -*- coding: utf-8 -*-
import sys

print("Python version:", sys.version)
for mod in ["pyzbar", "cv2", "zxing", "PIL"]:
    try:
        __import__(mod)
        print(f"  - {mod}: AVAILABLE")
    except ImportError:
        print(f"  - {mod}: NOT AVAILABLE")
