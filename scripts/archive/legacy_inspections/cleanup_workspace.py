import os
import shutil

# 1. Clean output directory
archive_dir = os.path.join("output", "archive_scratch")
os.makedirs(archive_dir, exist_ok=True)

out_files = [f for f in os.listdir("output") if os.path.isfile(os.path.join("output", f))]

# Core deliverables to keep in output root
keep_in_output = {
    ".gitkeep",
    "customer_result.xlsx",
    "customer_review.xlsx",
    "data_profile.json",
    "data_profile.xlsx",
    "mapping.xlsx",
    "mapping.csv",
    "mapping_result.xlsx",
    "mapping_result.csv",
    "mapping_result.json",
    "reconciliation_report.txt",
    "result.xlsx",
    "result.csv",
    "review_report.html",
    "perfect_front_boxes_1659.json",
    "g2_g5_manifest.json"
}

moved_out = 0
for f in out_files:
    if f not in keep_in_output:
        src = os.path.join("output", f)
        dst = os.path.join(archive_dir, f)
        shutil.move(src, dst)
        moved_out += 1

print(f"Moved {moved_out} scratch files from output/ to output/archive_scratch/")

# 2. Clean scripts directory
scripts_archive = os.path.join("scripts", "archive_debug")
os.makedirs(scripts_archive, exist_ok=True)

script_files = [f for f in os.listdir("scripts") if os.path.isfile(os.path.join("scripts", f))]

# Identify debug / one-off inspection scripts to archive
debug_prefixes = ("inspect_", "test_", "check_", "scratch_", "verify_specific", "dump_", "list_")

moved_scripts = 0
for sf in script_files:
    if sf.startswith(debug_prefixes):
        src = os.path.join("scripts", sf)
        dst = os.path.join(scripts_archive, sf)
        shutil.move(src, dst)
        moved_scripts += 1

print(f"Moved {moved_scripts} debug/inspection scripts to scripts/archive_debug/")

# Remove __pycache__ folders
for root, dirs, files in os.walk("."):
    if "__pycache__" in dirs:
        pycache_path = os.path.join(root, "__pycache__")
        print(f"Removing __pycache__: {pycache_path}")
        shutil.rmtree(pycache_path, ignore_errors=True)

print("Cleanup completed successfully.")
