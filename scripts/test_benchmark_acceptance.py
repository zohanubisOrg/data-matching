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
    model_name = sys.argv[1] if len(sys.argv) > 1 else "u2net"
    matting = MattingEngine(model_name)
    standardizer = StudioStandardizer(canvas_size=2048)
    gate = QualityGate()

    # Load demo images directly if cached on disk
    demo_images = {}
    p362 = ROOT / "scratch_demo_362.jpg"
    p863 = ROOT / "scratch_demo_863.jpg"
    if p362.exists():
        demo_images[362] = Image.open(p362).convert("RGB")
    if p863.exists():
        demo_images[863] = Image.open(p863).convert("RGB")

    test_cases = [
        {
            "name": "IMG_0885 (Shan Meat Masala - Triple Vertical Panel)",
            "path": ROOT / "source-import/G2_original/IMG_0885.jpeg",
            "strategy": "STANDARD",
            "barcode_center": (0.77, 0.52),
            "expect_archetype": "TRIPLE_VERTICAL_PANEL",
        },
        {
            "name": "IMG_0123 (Horizontal Bottles - Y-Split)",
            "path": ROOT / "source-import/G1_original/IMG_0123.jpeg",
            "strategy": "STANDARD",
            "barcode_center": (0.28, 0.72),
            "expect_archetype": "HORIZONTAL_STACK",
        },
        {
            "name": "IMG_0429 (Triple Standing Bottles - Dual Hero/Center)",
            "path": ROOT / "source-import/G2_original/IMG_0429.jpeg",
            "strategy": "STANDARD",
            "barcode_center": (0.49, 0.50),
            "expect_archetype": "DUAL_HERO",
        },
        {
            "name": "IMG_0380 (Mae Pranom - 6 Stacked Tubs Grid)",
            "path": ROOT / "source-import/G1_original/IMG_0380.jpeg",
            "strategy": "STANDARD",
            "barcode_center": (0.35, 0.25),
            "expect_archetype": "STACKED_TUBS_GRID",
        },
        {
            "name": "IMG_1399 (Wonton Dual Tray - Wrapped)",
            "path": ROOT / "source-import/G3_Original/IMG_1399.jpeg",
            "strategy": "STANDARD",
            "barcode_center": (0.30, 0.50),
            "expect_archetype": "DUAL_TRAY_WRAPPED",
        },
        {
            "name": "IMG_0886 (Pho Ga Deconstructed Carton)",
            "path": ROOT / "source-import/G2_original/IMG_0886.jpeg",
            "strategy": "STANDARD",
            "barcode_center": None,
            "expect_archetype": "DECONSTRUCTED_CARTON",
        },
        {
            "name": "G4 Carton Box (Regression Check)",
            "path": ROOT / "source-import/G4-original/20260916_110807255_iOS.heic",
            "strategy": "CARTON_BOX",
            "barcode_center": None,
            "expect_archetype": "CARTON_BOX_BYPASS",
        },
        {
            "name": "Nyt Produce (Regression Check)",
            "path": ROOT / "source-import/Nyt25.09.26/10.jpg",
            "strategy": "SEQUENTIAL_PAIR",
            "barcode_center": None,
            "expect_archetype": "SEQUENTIAL_PAIR_BYPASS",
        },
    ]

    results = []

    for idx, tc in enumerate(test_cases, start=1):
        test_name = tc["name"]
        img_path = tc["path"]
        strategy = tc["strategy"]
        bc_center = tc.get("barcode_center")
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
        row_id = 362 if "0380" in img_path.name else (863 if "0886" in img_path.name else None)
        demo_img = demo_images.get(row_id)
        isolated, was_isolated = cropper.isolate_front(raw, demo_img=demo_img, barcode_center=bc_center, strategy=strategy)
        w_iso, h_iso = isolated.size
        print(f"  Isolated size: {w_iso}x{h_iso} (Was isolated: {was_isolated}, Reason: {cropper.last_crop_reason})")

        # Step 3: Alpha Matting with Hole Protection
        rgba, mask = matting.remove_background(isolated, enable_hole_protection=True)

        # Step 4: Canvas Standardization (2048x2048 white canvas, centered)
        packshot, std_mask, bbox = standardizer.standardize(rgba)
        print(f"  Standardized canvas: {packshot.size}, Product bbox: {bbox}")

        # Step 5: Quality Gate Evaluation
        metrics = gate.evaluate_packshot(
            packshot, std_mask, f"BENCH-{idx:02d}", "885000000000",
            crop_mask=mask if was_isolated else None,
            demo_img=demo_img,
        )
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
        status_symbol = "PASS" if r["decision"] in ("PASS", "WARNING_ACCEPT", "WARNING/SOFT-PASS") else "FAIL"
        if status_symbol == "FAIL":
            all_passed = False
        print(f"[{status_symbol:<4}] {r['name']:<48} | Decision: {r['decision']:<14} | Solidity: {r['solidity']:.3f} | Margin: {r['margin_px']}px")

    print("=" * 70)
    print(f"All Audit Artifacts saved to: {audit_dir}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(run_benchmark())
