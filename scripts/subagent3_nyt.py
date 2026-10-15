#!/usr/bin/env python3
"""
scripts/subagent3_nyt.py
------------------------
Subagent 3: Inventories Nyt25.09.26.
Output: D:\\Work\\shopify\\output\\catalog_pairs\\review\\external_source_inventory\\nyt.jsonl
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from inventory_engine import run_subagent_inventory

if __name__ == "__main__":
    run_subagent_inventory(
        agent_name="Subagent-3 (Nyt)",
        target_folders=["Nyt25.09.26"],
        output_filename="nyt.jsonl",
        max_workers=6,
    )
