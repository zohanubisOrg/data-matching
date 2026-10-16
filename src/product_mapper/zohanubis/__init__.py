"""Zohanubis Precision Packshot Pipeline.

Clean-sheet, zero-cache, high-fidelity e-commerce image processing pipeline
integrating tiered screening, multi-angle barcode decoding, visual ground-truth
matching, detail-preserving alpha matting, and atomic Excel embedding.
"""
import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

__version__ = "1.0.0"
