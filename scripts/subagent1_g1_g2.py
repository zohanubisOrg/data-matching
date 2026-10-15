#!/usr/bin/env python3
"""
scripts/subagent1_g1_g2.py
--------------------------
Subagent 1: Inventories G1_original and G2_original.
Output: D:\\Work\\shopify\\output\\catalog_pairs\\review\\external_source_inventory\\g1_g2.jsonl
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from inventory_engine import run_subagent_inventory

if __name__ == "__main__":
    run_subagent_inventory(
        agent_name="Subagent-1 (G1 & G2)",
        target_folders=["G1_original", "G2_original"],
        output_filename="g1_g2.jsonl",
        max_workers=8,
    )
