import numpy as np
import pytest
from PIL import Image

from product_mapper.vision.package_packshot import (
    UnverifiedPackageError, mask_from_polygon, assess_candidate_mask,
    render_verified_packshot,
)
from product_mapper.vision.smart_packshot import make_smart_packshot


def fixture():
    image = Image.new('RGB', (1000, 1200), (165, 125, 80))
    arr = np.asarray(image).copy()
    arr[100:1100, 100:900] = (245, 240, 220)
    arr[300:500, 300:700] = (20, 100, 40)
    mask = np.zeros((1200, 1000), np.uint8)
    mask[100:1100, 100:900] = 255
    return Image.fromarray(arr), mask


def test_white_and_cardboard_coloured_package_interior_is_unchanged():
    image, mask = fixture()
    output, metrics = render_verified_packshot(image, mask, target_side=1000, shape='square')
    assert output.size == (1000, 1000)
    # 1000px source height is placed at 840px, centred, preserving aspect ratio.
    assert metrics['placed_size'] == [672, 840]
    assert output.getpixel((250, 200)) == (245, 240, 220)
    assert output.getpixel((500, 300)) == (20, 100, 40)
    assert output.getpixel((0, 0)) == (255, 255, 255)


def test_logo_only_candidate_is_rejected_against_independent_package_mask():
    _, reference = fixture()
    logo = np.zeros_like(reference)
    logo[300:500, 300:700] = 255
    result = assess_candidate_mask(logo, reference)
    assert result['accepted'] is False
    assert result['coverage'] == pytest.approx(0.1)


@pytest.mark.parametrize('damage', ['hole', 'second_object', 'clipped', 'empty'])
def test_invalid_package_mask_is_rejected(damage):
    image, mask = fixture()
    if damage == 'hole':
        mask[400:700, 400:600] = 0
    elif damage == 'second_object':
        mask[10:50, 10:50] = 255
    elif damage == 'clipped':
        mask[:101, 100:900] = 255
    else:
        mask[:] = 0
    with pytest.raises(UnverifiedPackageError):
        render_verified_packshot(image, mask)


def test_no_unverified_ai_or_full_frame_fallback_can_save_a_packshot():
    with pytest.raises(UnverifiedPackageError):
        make_smart_packshot(fixture()[0])


def test_legacy_off_padding_bypass_cannot_accept_unverified_full_frame():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.studio_front_v3_extractor import format_to_canvas
    with pytest.raises(UnverifiedPackageError):
        format_to_canvas(fixture()[0])


def test_native_thumbnail_is_rejected_instead_of_upscaled_as_a_source():
    image = Image.new('RGB', (115, 115))
    mask = mask_from_polygon(image.size, [(10, 10), (104, 10), (104, 104), (10, 104)])
    with pytest.raises(UnverifiedPackageError):
        render_verified_packshot(image, mask)


def test_render_rejects_native_package_when_2400_canvas_would_require_upscaling():
    image = Image.new('RGB', (1200, 1000), (245, 240, 220))
    mask = np.zeros((1000, 1200), np.uint8)
    mask[100:800, 100:700] = 255
    with pytest.raises(UnverifiedPackageError, match='upscal'):
        render_verified_packshot(image, mask, target_side=2400, shape='square')


def test_native_fit_reduces_occupancy_without_upscaling_when_product_remains_large():
    image = Image.new('RGB', (2200, 2200), (245, 240, 220))
    mask = np.zeros((2200, 2200), np.uint8)
    mask[100:2005, 300:1900] = 255
    output, metrics = render_verified_packshot(
        image, mask, target_side=2400, shape='square', fit_to_native=True)
    assert output.size == (2400, 2400)
    assert metrics['upscale_factor'] == 1
    assert metrics['scale_limited_to_native'] is True
    assert metrics['occupancy'] == pytest.approx(1905 / 2400)
    assert metrics['requested_occupancy'] == pytest.approx(.84)


@pytest.mark.parametrize('shape,box,expected', [
    ('tall', (100, 100, 300, 1100), [141, 704]),
    ('horizontal', (100, 100, 900, 500), [712, 356]),
])
def test_adaptive_layout_preserves_product_aspect_ratio(shape, box, expected):
    image, _ = fixture()
    mask = np.zeros((1200, 1000), np.uint8)
    x0, y0, x1, y1 = box
    mask[y0:y1, x0:x1] = 255
    output, metrics = render_verified_packshot(image, mask, target_side=800, shape=shape)
    assert output.size == (800, 800)
    assert metrics['placed_size'] == expected
    assert metrics['upscale_factor'] <= 1


def test_polygon_outside_source_is_not_silently_clamped():
    with pytest.raises(UnverifiedPackageError):
        mask_from_polygon((1000, 1200), [(-1, 0), (600, 50), (200, 900)])
