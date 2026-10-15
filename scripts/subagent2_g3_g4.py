#!/usr/bin/env python3
"""
scripts/subagent2_g3_g4.py
--------------------------
Subagent 2: Inventories G3_Original and G4-original.
Output: D:\\Work\\shopify\\output\\catalog_pairs\\review\\external_source_inventory\\g3_g4.jsonl
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from inventory_engine import run_subagent_inventory

if __name__ == "__main__":
    run_subagent_inventory(
        agent_name="Subagent-2 (G3 & G4)",
        target_folders=["G3_Original", "G4-original"],
        output_filename="g3_g4.jsonl",
        max_workers=8,
    )
