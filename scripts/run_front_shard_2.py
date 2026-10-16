#!/usr/bin/env python3
"""Run the front-v5 confirmed pilot through the shared parent QA pipeline (shard 2)."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
labels = os.environ.get("FRONT_V5_PILOT_LABELS")
if not labels:
    raise SystemExit("set FRONT_V5_PILOT_LABELS to the 48 human-confirmed pilot labels")
label_path = Path(labels).resolve()
run_id = f"front-v5-{label_path.stem}-shard-2"
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,63}", run_id):
    raise SystemExit("pilot label filename must produce a safe run id")
command = [
    sys.executable, str(ROOT / "scripts/run_front_v5_batch.py"),
    "--stage", "render", "--run-id", run_id,
    "--labels", str(label_path), "--shard-index", "2",
    "--qa-mode", os.environ.get("FRONT_V5_QA_MODE", "shadow"),
]
approval = os.environ.get("FRONT_V5_PILOT_APPROVAL")
if approval:
    command.extend(["--pilot-approval", str(Path(approval).resolve())])
if os.environ.get("FRONT_V5_RESUME") == "1":
    command.append("--resume")
os.chdir(ROOT)
os.execv(sys.executable, command)
