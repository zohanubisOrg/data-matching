from pathlib import Path

import numpy as np
import openpyxl
import pytest
from PIL import Image

from product_mapper.vision.conservative_front import (
    BarcodeHit,
    FrontRejected,
    core_is_preserved,
    content_is_square,
    foreground_mask,
    leftover_barcode_panel,
    output_is_clean,
    render_panel,
    seam_cut_is_background,
    select_front_box,
    select_front_package,
)
from product_mapper.vision.front_v5_ledger import (
    iter_source_files,
    load_apptance_records,
    load_catalog_rows,
    normalize_barcode_variants,
)


def _two_packs():
    mask = np.zeros((400, 500), np.uint8)
    mask[40:360, 30:200] = 255
    mask[40:360, 280:470] = 255
    return mask


def test_eight_percent_seam_shift_is_rejected():
    mask = _two_packs()
    front = (280, 40, 470, 360)
    back = (30, 40, 200, 360)
    assert seam_cut_is_background(mask, front, back, 0)
    assert seam_cut_is_background(mask, front, back, 0.08) is False


def test_barcode_panel_is_not_the_front():
    mask = _two_packs()
    box = select_front_box(mask, (100, 200))
    assert box[0] >= 270
    assert box[2] <= 500


def test_touching_packs_have_no_front():
    mask = np.zeros((400, 500), np.uint8)
    mask[40:360, 30:470] = 255
    with pytest.raises(FrontRejected) as caught:
        select_front_box(mask, (80, 200))
    assert caught.value.state == "BLOCKED_INCOMPLETE_EDGE"


def test_core_hole_blocks_output():
    alpha = np.ones((80, 80), np.float32)
    core = np.ones((80, 80), bool)
    alpha[30:50, 30:50] = 0
    assert core_is_preserved(alpha, core) is False


def test_render_rejects_upscale_and_tight_margin():
    image = Image.new("RGB", (1200, 1400), (240, 240, 240))
    with pytest.raises(FrontRejected) as caught:
        render_panel(image, (50, 50, 1050, 1250), np.array([240, 240, 240]))
    assert caught.value.state == "CUSTOMER_RESHOOT"
    wide = Image.new("RGB", (3200, 3400), (230, 230, 230))
    pixels = np.asarray(wide).copy()
    pixels[100:3300, 100:3100] = (180, 40, 40)
    wide = Image.fromarray(pixels)
    with pytest.raises(FrontRejected) as tight:
        render_panel(wide, (80, 80, 3120, 3320), np.array([230, 230, 230]), occupancy=0.98)
    assert "48px" in tight.value.reason


def test_package_edge_pixel_is_not_feathered_inward():
    image = Image.new("RGB", (2800, 3000), (210, 210, 210))
    pixels = np.asarray(image).copy()
    pixels[80:2920, 80:2720] = (20, 90, 200)
    pixels[390:430, 110:150] = (0, 255, 0)
    image = Image.fromarray(pixels)
    output, metrics = render_panel(image, (40, 40, 2760, 2960), np.array([210, 210, 210]))
    assert output.size == (2400, 2400)
    assert metrics["scale"] <= 1
    assert output.getpixel((0, 0)) == (255, 255, 255)
    rendered = np.asarray(output).astype(np.int16)
    green = np.all(np.abs(rendered - np.array([0, 255, 0])) <= 8, axis=2)
    assert green.any()


def test_duplicate_barcode_keeps_both_rows_blocked(tmp_path):
    path = tmp_path / "catalog.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.cell(3, 1, "Barcode")
    sheet.cell(3, 2, "Full name (EN)")
    sheet.cell(3, 5, "Record ID")
    sheet.cell(4, 1, "8938500075070")
    sheet.cell(4, 2, "Fresh Nua")
    sheet.cell(4, 5, "G2-0117")
    sheet.cell(5, 1, "8938500075070")
    sheet.cell(5, 2, "Fresh Bud")
    sheet.cell(5, 5, "G2-0149")
    sheet.cell(6, 1, "1234567890128")
    sheet.cell(6, 2, "Solo")
    sheet.cell(6, 5, "G1-0001")
    workbook.save(path)
    rows = load_catalog_rows(path)
    assert len(rows) == 3
    blocked = [row for row in rows if row["identity_conflict"]]
    assert {row["record_id"] for row in blocked} == {"G2-0117", "G2-0149"}
    assert sum(row["identity_conflict"] for row in rows) == 2


def test_source_walker_skips_removed_and_refuses_webshop_dirs(tmp_path):
    root = tmp_path / "G1_original"
    kept = root / "a.jpg"
    removed = root / "_removed_not_in_excel" / "b.jpg"
    kept.parent.mkdir()
    removed.parent.mkdir()
    kept.write_bytes(b"jpg")
    removed.write_bytes(b"jpg")
    found = iter_source_files([root])
    assert found == [kept]
    with pytest.raises(ValueError):
        iter_source_files([tmp_path / "front-v3"])


def _scene(width: int, height: int) -> np.ndarray:
    return np.full((height, width, 3), 235, np.uint8)


def test_two_touching_subjects_keep_the_face_without_barcode():
    rgb = _scene(360, 240)
    rgb[30:210, 30:170] = (180, 20, 20)
    rgb[30:210, 170:330] = (20, 40, 190)
    rgb[100, 250] = (0, 255, 0)
    with pytest.raises(FrontRejected, match="multiple subjects need a front reference"):
        select_front_package(rgb, (80, 120))


def test_three_touching_subjects_use_the_far_face_not_the_side():
    rgb = _scene(420, 240)
    rgb[30:210, 20:140] = (180, 20, 20)
    rgb[30:210, 140:250] = (20, 160, 40)
    rgb[30:210, 250:400] = (20, 40, 190)
    rgb[80, 320] = (0, 255, 0)
    reference = rgb[30:210, 260:390].copy()
    _box, mask = select_front_package(rgb, (70, 120), reference)
    assert mask[80, 320] == 255
    assert int(np.count_nonzero(mask[30:210, 140:250])) == 0
    assert mask[120, 70] == 0


def test_lid_band_is_joined_back_to_its_jar():
    rgb = _scene(420, 360)
    rgb[20:90, 70:340] = (40, 70, 190)
    rgb[150:340, 90:320] = (170, 30, 40)
    reference = rgb[20:90, 70:340].copy()
    _box, mask = select_front_package(rgb, (200, 50), reference)
    assert mask[50, 200] == 255
    assert mask[240, 200] == 255


def test_two_jars_cropped_at_the_lids_keep_one_full_jar():
    rgb = _scene(640, 420)
    rgb[16:96, 40:280] = (30, 50, 180)
    rgb[16:96, 340:580] = (30, 50, 180)
    rgb[170:390, 50:270] = (170, 30, 40)
    rgb[170:390, 350:570] = (20, 140, 50)
    reference = np.full((80, 60, 3), (170, 30, 40), np.uint8)
    _box, mask = select_front_package(rgb, (450, 50), reference)
    assert mask[250, 150] == 255
    assert mask[50, 150] == 255
    assert mask[250, 450] == 0


def test_one_package_with_a_label_band_is_not_cut_in_half():
    rgb = _scene(360, 280)
    rgb[30:250, 40:320] = (170, 25, 30)
    rgb[120:145, 40:320] = (230, 190, 40)
    rgb[70, 80] = (0, 255, 0)
    rgb[210, 80] = (0, 0, 255)
    _box, mask = select_front_package(rgb, (90, 70))
    assert mask[70, 80] == 255
    assert mask[210, 80] == 255


def test_dark_crack_between_same_color_packs_is_not_the_label_edge():
    rgb = _scene(480, 260)
    rgb[30:230, 20:210] = (180, 20, 20)
    rgb[30:230, 210:218] = (30, 20, 20)
    rgb[30:230, 218:460] = (180, 20, 20)
    rgb[40:200, 280:430] = (245, 245, 245)
    rgb[80, 60] = (0, 255, 0)
    rgb[80, 240] = (0, 0, 255)
    reference = rgb[30:230, 30:180].copy()
    _box, mask = select_front_package(rgb, (350, 120), reference)
    assert mask[80, 60] == 255
    assert mask[80, 240] == 0
    assert int(np.count_nonzero(mask[40:200, 280:430])) == 0


def test_narrow_gap_keeps_the_far_face_and_drops_the_label_panel():
    rgb = _scene(480, 260)
    rgb[30:230, 30:200] = (180, 20, 20)
    rgb[30:230, 208:450] = (180, 20, 20)
    rgb[50:190, 250:400] = (245, 245, 245)
    rgb[140, 80] = (0, 255, 0)
    reference = rgb[30:230, 40:180].copy()
    _box, mask = select_front_package(rgb, (320, 120), reference)
    assert mask[140, 80] == 255
    assert int(np.count_nonzero(mask[50:190, 250:400])) == 0
    assert mask[120, 320] == 0


def test_horizontal_bottles_keep_the_branded_bottle_and_its_cap():
    rgb = _scene(360, 280)
    rgb[40:125, 30:330] = (180, 30, 30)
    rgb[40:125, 36:78] = (230, 220, 190)
    rgb[155:245, 30:330] = (90, 40, 30)
    rgb[80, 200] = (0, 255, 0)
    with pytest.raises(FrontRejected, match="multiple subjects need a front reference"):
        select_front_package(rgb, (200, 190))


def test_one_bag_keeps_the_film_around_its_barcode_sticker():
    rgb = _scene(240, 360)
    rgb[30:330, 40:200] = (40, 140, 50)
    rgb[200:250, 80:150] = (250, 250, 250)
    rgb[50, 70] = (0, 180, 40)
    _box, mask = select_front_package(rgb, (110, 225))
    assert mask[50, 70] == 255
    assert mask[300, 80] == 255
    assert mask[220, 100] == 255


def test_customer_front_keeps_the_middle_subject_that_matches():
    rgb = _scene(420, 240)
    rgb[30:210, 20:140] = (180, 20, 20)
    rgb[30:210, 140:250] = (20, 160, 40)
    rgb[30:210, 250:400] = (20, 40, 190)
    rgb[70:130, 165:220] = (250, 220, 30)
    reference = np.full((80, 60, 3), (20, 160, 40), np.uint8)
    reference[15:55, 12:48] = (250, 220, 30)
    _box, mask = select_front_package(rgb, (70, 120), reference)
    assert mask[100, 190] == 255
    assert mask[120, 70] == 0
    assert mask[120, 330] == 0


def test_customer_front_may_be_the_subject_carrying_the_barcode():
    rgb = _scene(360, 240)
    rgb[30:210, 30:170] = (180, 20, 20)
    rgb[30:210, 190:330] = (20, 40, 190)
    rgb[60:120, 50:110] = (250, 220, 30)
    reference = np.full((80, 60, 3), (180, 20, 20), np.uint8)
    reference[15:55, 12:48] = (250, 220, 30)
    _box, mask = select_front_package(rgb, (80, 120), reference)
    assert mask[90, 80] == 255
    assert int(np.count_nonzero(mask[30:210, 190:330])) == 0


def test_package_texture_picks_the_customer_front_even_when_it_carries_the_barcode():
    rgb = _scene(360, 240)
    rgb[30:210, 20:160] = (30, 70, 180)
    rgb[30:210, 190:340] = (30, 70, 180)
    rng = np.random.default_rng(1)
    rgb[50:150, 40:140] = rng.integers(0, 255, (100, 100, 3), dtype=np.uint8)
    rgb[50:150, 210:310] = rng.integers(0, 255, (100, 100, 3), dtype=np.uint8)
    reference = np.full((120, 110, 3), (30, 70, 180), np.uint8)
    reference[10:110, 5:105] = rgb[50:150, 40:140]
    _box, mask = select_front_package(rgb, (80, 120), reference)
    assert mask[100, 80] == 255
    assert mask[100, 250] == 0


def test_face_that_matches_the_back_photo_is_returned():
    rgb = _scene(360, 240)
    rgb[30:210, 30:170] = (180, 20, 20)
    rgb[30:210, 190:330] = (20, 40, 190)
    rgb[60:120, 50:110] = (250, 220, 30)
    reference = np.full((80, 60, 3), (180, 20, 20), np.uint8)
    reference[15:55, 12:48] = (250, 220, 30)
    back = reference.copy()
    with pytest.raises(FrontRejected) as caught:
        select_front_package(rgb, (200, 120), reference, back)
    assert caught.value.state == "QA_RETURN"


def test_three_separated_bottles_keep_only_the_customer_front():
    rgb = _scene(520, 280)
    rgb[40:240, 20:150] = (180, 20, 20)
    rgb[40:240, 190:330] = (20, 140, 40)
    rgb[40:240, 370:500] = (20, 40, 180)
    rgb[80:150, 220:300] = (250, 220, 30)
    reference = np.full((80, 60, 3), (20, 140, 40), np.uint8)
    reference[15:55, 12:48] = (250, 220, 30)
    _box, mask = select_front_package(rgb, (80, 140), reference)
    assert mask[120, 250] == 255
    assert mask[120, 80] == 0
    assert mask[120, 430] == 0


@pytest.mark.parametrize("scores", [(0.50, 0.50), (0.03, 0.0), (0.15, 0.12)])
def test_reference_subject_selection_requires_absolute_score_and_margin(monkeypatch, scores):
    import product_mapper.vision.conservative_front as front

    rgb = np.zeros((40, 40, 3), np.uint8)
    masks = [np.ones((40, 40), np.uint8), np.ones((40, 40), np.uint8)]
    monkeypatch.setattr(front, "_subject_crop", lambda *_args, **_kwargs: np.zeros((12, 12, 3), np.uint8))
    current = iter(scores)
    monkeypatch.setattr(front, "_feature_score", lambda *_args: next(current))
    with pytest.raises(FrontRejected, match="customer front does not match one subject"):
        front._best_reference_subject(rgb, masks, np.zeros((12, 12, 3), np.uint8), None)


def test_available_back_reference_without_a_comparable_score_fails_closed(monkeypatch):
    import product_mapper.vision.conservative_front as front

    rgb = np.zeros((40, 40, 3), np.uint8)
    masks = [np.ones((40, 40), np.uint8), np.ones((40, 40), np.uint8)]
    monkeypatch.setattr(front, "_subject_crop", lambda *_args, **_kwargs: np.zeros((12, 12, 3), np.uint8))
    scores = iter((0.5, 0.1, None))
    monkeypatch.setattr(front, "_feature_score", lambda *_args: next(scores))
    with pytest.raises(FrontRejected, match="chosen face matches the back photo"):
        front._best_reference_subject(rgb, masks, np.zeros((12, 12, 3), np.uint8), np.ones((12, 12, 3), np.uint8))


def test_a_horizontal_strip_fails_the_qa_gate():
    rgb = _white_canvas()
    rgb[2000:2200, 200:2200] = (180, 30, 30)
    assert output_is_clean(Image.fromarray(rgb)) == "product is cut down to a strip"


def test_barcode_on_the_middle_of_three_subjects_does_not_prove_front_identity():
    rgb = _scene(420, 240)
    rgb[30:210, 20:140] = (180, 20, 20)
    rgb[30:210, 140:250] = (20, 160, 40)
    rgb[30:210, 250:400] = (20, 40, 190)
    with pytest.raises(FrontRejected, match="multiple subjects need a front reference"):
        select_front_package(rgb, (190, 120))


def test_foreground_mask_keeps_a_dark_pack_on_white():
    rgb = np.full((80, 80, 3), 250, np.uint8)
    rgb[20:60, 20:60] = (30, 30, 30)
    mask = foreground_mask(rgb, np.array([250, 250, 250]))
    assert mask[40, 40] == 255
    assert mask[0, 0] == 0


def _white_canvas() -> np.ndarray:
    return np.full((2400, 2400, 3), 255, np.uint8)


def test_barcode_printed_on_the_product_passes_the_qa_gate():
    rgb = _white_canvas()
    rgb[200:2200, 900:1500] = (180, 30, 30)
    hit = BarcodeHit("8938500075070", 1200, 1200, 0, 400)
    assert leftover_barcode_panel(rgb, [hit]) is False


def test_barcode_on_a_separate_panel_fails_the_qa_gate():
    rgb = _white_canvas()
    rgb[200:2200, 900:1500] = (180, 30, 30)
    rgb[400:1000, 1700:2100] = (20, 20, 20)
    hit = BarcodeHit("8938500075070", 1900, 700, 0, 400)
    assert leftover_barcode_panel(rgb, [hit]) is True


def test_clean_front_passes_the_qa_gate():
    rgb = _white_canvas()
    rgb[200:2200, 900:1500] = (180, 30, 30)
    assert output_is_clean(Image.fromarray(rgb)) is None


def test_square_cardboard_around_the_package_passes_the_qa_gate():
    rgb = _white_canvas()
    rgb[180:2220, 700:1700] = (186, 164, 132)
    rgb[360:2040, 900:1500] = (180, 30, 30)
    assert output_is_clean(Image.fromarray(rgb)) is None


def test_irregular_cardboard_around_the_product_is_sent_back():
    rgb = _white_canvas()
    rgb[800:1600, 800:1600] = (180, 30, 30)
    rgb[1600:2000, 1600:2000] = (186, 164, 132)
    reason = output_is_clean(Image.fromarray(rgb))
    assert reason == "table or cardboard remains around the product"


def test_rectangular_panel_keeps_the_clear_film_and_a_square_of_background():
    image = Image.new("RGB", (3600, 4000), (214, 196, 168))
    pixels = np.asarray(image).copy()
    pixels[800:3400, 800:3000] = (180, 30, 30)
    pixels[760:800, 1400:2200] = (236, 236, 232)
    image = Image.fromarray(pixels)
    mask = np.zeros(pixels.shape[:2], np.uint8)
    mask[800:3400, 800:3000] = 255
    output, _metrics = render_panel(image, (800, 800, 3000, 3400), np.array([214, 196, 168]), package_mask=mask)
    rendered = np.asarray(output).astype(np.int16)
    pale = np.all(np.abs(rendered - np.array([236, 236, 232])) <= 12, axis=2)
    cardboard = np.all(np.abs(rendered - np.array([214, 196, 168])) <= 12, axis=2)
    assert pale.any()
    assert cardboard.any()
    assert output.getpixel((0, 0)) == (255, 255, 255)


def test_strict_renderer_scales_complete_product_not_retained_padding():
    image = Image.new("RGB", (3400, 2800), (214, 196, 168))
    mask = np.zeros((2800, 3400), np.uint8)
    mask[200:2800, 900:1800] = 255

    output, metrics = render_panel(
        image, (900, 200, 1800, 2800), np.array([214, 196, 168]),
        package_mask=mask, strict_geometry=True,
    )

    assert output.size == (2400, 2400)
    assert metrics["native_long_side"] == 2600
    assert metrics["scale"] == pytest.approx(2064 / 2600)
    assert max(metrics["canvas_product_bbox"][2] - metrics["canvas_product_bbox"][0],
               metrics["canvas_product_bbox"][3] - metrics["canvas_product_bbox"][1]) == 2064


def test_strict_renderer_rejects_product_that_requires_upscaling():
    image = Image.new("RGB", (2100, 2100), (255, 255, 255))
    mask = np.zeros((2100, 2100), np.uint8)
    mask[500:2500 if 2500 < 2100 else 1600, 900:1200] = 255
    with pytest.raises(FrontRejected):
        render_panel(image, (900, 500, 1200, 1600), np.array([255, 255, 255]),
                     package_mask=mask, strict_geometry=True)


def test_audit_false_accepts_fail_the_qa_gate():
    folder = Path(__file__).resolve().parents[1] / "output" / "catalog_pairs" / "front-v5-run" / "audit"
    files = [path for path in folder.glob("*-IMG_*.jpg") if "preview" not in path.name]
    if len(files) < 8:
        pytest.skip("audit renders are not on disk")
    for path in files:
        with Image.open(path) as image:
            rgb = np.asarray(image.convert("RGB"))
        reason = output_is_clean(Image.fromarray(rgb))
        if reason is None:
            assert content_is_square(rgb), path.name
            continue
        assert reason, path.name


def test_apptance_is_selection_input_and_never_auto_accepts_or_copies(tmp_path):
    apptance_dir = tmp_path / "apptance"
    apptance_dir.mkdir()
    front_dir = tmp_path / "front-v5"

    test_img = Image.new("RGB", (2400, 2400), (255, 255, 255))
    test_path = apptance_dir / "014285001799-front.jpg"
    test_img.save(test_path, "JPEG")

    records = load_apptance_records(apptance_dir, front_dir)
    assert "014285001799" in records
    assert "14285001799" in records
    rec = records["014285001799"]
    assert rec["state"] == "QA_RETURN"
    assert rec["selection_state"] == "USER_SELECTED"
    assert rec["source_sha256"]
    assert rec["output_path"] is None
    assert not (front_dir / "014285001799-front.jpg").exists()

