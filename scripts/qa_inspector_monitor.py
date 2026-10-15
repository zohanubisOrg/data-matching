import sys
import json
import os
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

agents = [
    ('bfca7ce8-5ce5-4bf0-a9a7-1f3667d2dfd2', 'Subagent 1 (Guardian)'),
    ('38e2908f-ee37-4201-a079-5cd1c8ac5f02', 'Subagent 2 (Batch 1)'),
    ('0452addb-432f-4ec9-bc87-9f08cda9a45a', 'Subagent 3 (Batch 2)'),
]

for aid, name in agents:
    tpath = Path(rf'C:\Users\HP\.gemini\antigravity\brain\{aid}\.system_generated\logs\transcript.jsonl')
    if tpath.exists():
        lines = [l for l in tpath.read_text(encoding='utf-8').split('\n') if l.strip()]
        print(f"\n==================== {name} ({aid[:8]}...) - Total steps: {len(lines)} ====================")
        for l in lines[-6:]:
            ob = json.loads(l)
            s_idx = ob.get("step_index")
            t = ob.get("type")
            src = ob.get("source")
            content = ob.get("content")
            print(f"--- Step {s_idx} [{src} / {t}] ---")
            if "tool_calls" in ob:
                for tc in ob["tool_calls"]:
                    tc_name = tc.get("name")
                    args = tc.get("args", {})
                    if tc_name == "run_command":
                        print(f"  Tool: run_command -> {args.get('CommandLine')[:150]}")
                    elif tc_name in ("view_file", "write_to_file", "replace_file_content"):
                        print(f"  Tool: {tc_name} -> {args.get('AbsolutePath') or args.get('TargetFile')}")
                    else:
                        print(f"  Tool: {tc_name} -> {args}")
            if content:
                print(f"  Content: {str(content)[:250]}")
