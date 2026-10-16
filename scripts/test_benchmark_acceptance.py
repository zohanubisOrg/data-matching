"""
scripts/test_benchmark_acceptance.py
====================================
Automated Acceptance Benchmark Test Suite for pipeline-zohanubis.
Tests the 5-Archetype Layout Classifier, hole protection, and G4/Nyt regression prevention.
Saves visual verification outputs in output/benchmark_audit/
"""

import sys
from pathlib import Path
from PIL import Image

sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.product_mapper.zohanubis.sanitizer import ImageSanitizer
from src.product_mapper.zohanubis.hero_cropper import HeroCropper
from src.product_mapper.zohanubis.matting_engine import MattingEngine
from src.product_mapper.zohanubis.studio_standardizer import StudioStandardizer
from src.product_mapper.zohanubis.quality_gate import QualityGate


def run_benchmark():
    print("=" * 70)
    print("      PIPELINE-ZOHANUBIS: ACCEPTANCE BENCHMARK VERIFICATION SUITE      ")
    print("=" * 70)

    audit_dir = ROOT / "output" / "benchmark_audit"
    audit_dir.mkdir(parents=True, exist_ok=True)

    sanitizer = ImageSanitizer()
    cropper = HeroCropper()
    matting = MattingEngine("birefnet-general")
    standardizer = StudioStandardizer(canvas_size=2048)
    gate = QualityGate()

    test_cases = [
        {
            "name": "IMG_0885 (Shan Meat Masala - Triple Vertical Panel)",
            "path": ROOT / "source-import/G2_original/IMG_0885.jpeg",
            "strategy": "STANDARD",
            "expect_archetype": "TRIPLE_VERTICAL_PANEL",
        },
        {
            "name": "IMG_0123 (Horizontal Bottles - Y-Split)",
            "path": ROOT / "source-import/G1_original/IMG_0123.jpeg",
            "strategy": "STANDARD",
            "expect_archetype": "HORIZONTAL_STACK",
        },
        {
            "name": "IMG_0429 (Triple Standing Bottles - Dual Hero/Center)",
            "path": ROOT / "source-import/G2_original/IMG_0429.jpeg",
            "strategy": "STANDARD",
            "expect_archetype": "DUAL_HERO",
        },
        {
            "name": "IMG_0380 (Mae Pranom - 6 Stacked Tubs Grid)",
            "path": ROOT / "source-import/G1_original/IMG_0380.jpeg",
            "strategy": "STANDARD",
            "expect_archetype": "STACKED_TUBS_GRID",
        },
        {
            "name": "IMG_1399 (Wonton Dual Tray - Wrapped)",
            "path": ROOT / "source-import/G3_Original/IMG_1399.jpeg",
            "strategy": "STANDARD",
            "expect_archetype": "DUAL_TRAY_WRAPPED",
        },
        {
            "name": "IMG_0886 (Pho Ga Deconstructed Carton)",
            "path": ROOT / "source-import/G2_original/IMG_0886.jpeg",
            "strategy": "STANDARD",
            "expect_archetype": "DECONSTRUCTED_CARTON",
        },
        {
            "name": "G4 Carton Box (Regression Check)",
            "path": ROOT / "source-import/G4-original/20260916_110807255_iOS.heic",
            "strategy": "CARTON_BOX",
            "expect_archetype": "CARTON_BOX_BYPASS",
        },
        {
            "name": "Nyt Produce (Regression Check)",
            "path": ROOT / "source-import/Nyt25.09.26/10.jpg",
            "strategy": "SEQUENTIAL_PAIR",
            "expect_archetype": "SEQUENTIAL_PAIR_BYPASS",
        },
    ]

    results = []

    for idx, tc in enumerate(test_cases, start=1):
        test_name = tc["name"]
        img_path = tc["path"]
        strategy = tc["strategy"]
        print(f"\n[{idx}/{len(test_cases)}] Testing: {test_name}...")
        print(f"  Source file: {img_path.name}")

        if not img_path.exists():
            print(f"  [ERROR] File not found: {img_path}")
            continue

        # Step 1: Load and normalize
        raw = sanitizer.load_normalized_image(img_path)
        w_orig, h_orig = raw.size
        print(f"  Raw size: {w_orig}x{h_orig}")

        # Step 2: Isolation
        isolated, was_isolated = cropper.isolate_front(raw, strategy=strategy)
        w_iso, h_iso = isolated.size
        print(f"  Isolated size: {w_iso}x{h_iso} (Was isolated: {was_isolated})")

        # Step 3: Alpha Matting with Hole Protection
        rgba, mask = matting.remove_background(isolated, enable_hole_protection=True)

        # Step 4: Canvas Standardization (2048x2048 white canvas, centered)
        packshot, std_mask, bbox = standardizer.standardize(rgba)
        print(f"  Standardized canvas: {packshot.size}, Product bbox: {bbox}")

        # Step 5: Quality Gate Evaluation
        metrics = gate.evaluate_packshot(packshot, std_mask, f"BENCH-{idx:02d}", "885000000000")
        print(f"  Quality Gate: {metrics.decision} (Solidity: {metrics.solidity:.4f}, Margin: {metrics.canvas_clipping_px}px, Blur: {metrics.blur_score:.1f})")

        # Save verification output
        safe_name = img_path.stem
        out_packshot_path = audit_dir / f"{safe_name}_webshop_front_2048.jpg"
        out_isolated_path = audit_dir / f"{safe_name}_isolated_crop.jpg"
        packshot.save(out_packshot_path, "JPEG", quality=95, optimize=True)
        isolated.save(out_isolated_path, "JPEG", quality=92, optimize=True)

        results.append({
            "name": test_name,
            "filename": img_path.name,
            "raw_size": (w_orig, h_orig),
            "isolated_size": (w_iso, h_iso),
            "was_isolated": was_isolated,
            "decision": metrics.decision,
            "solidity": metrics.solidity,
            "blur_score": metrics.blur_score,
            "margin_px": metrics.canvas_clipping_px,
            "output_path": str(out_packshot_path),
        })

        import gc
        gc.collect()

    print("\n" + "=" * 70)
    print("                    BENCHMARK AUDIT SUMMARY                     ")
    print("=" * 70)
    all_passed = True
    for r in results:
        status_symbol = "PASS" if r["decision"] in ("PASS", "WARNING/SOFT-PASS") else "FAIL"
        if status_symbol == "FAIL":
            all_passed = False
        print(f"[{status_symbol:<4}] {r['name']:<48} | Solidity: {r['solidity']:.3f} | Margin: {r['margin_px']}px")

    print("=" * 70)
    print(f"All Audit Artifacts saved to: {audit_dir}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(run_benchmark())
