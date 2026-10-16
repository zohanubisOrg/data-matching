import io
import pytest
from unittest.mock import MagicMock
from PIL import Image

from product_mapper.harvest.visual_anchor import VisualAnchorValidator
from product_mapper.harvest.candidate_resolver import CandidateResolver


def test_visual_anchor_aspect_ratio_match():
    validator = VisualAnchorValidator(max_aspect_drift=0.25)
    # Create tall demo (100x200) and tall candidate (200x400) -> both ratio 0.5
    demo = Image.new("RGB", (100, 200), color="blue")
    cand = Image.new("RGB", (200, 400), color="blue")
    buf = io.BytesIO()
    demo.save(buf, format="JPEG")
    demo_bytes = buf.getvalue()

    is_valid, drift, reason = validator.validate_candidate_against_demo(cand, demo_bytes)
    assert is_valid is True
    assert drift <= 0.05


def test_visual_anchor_aspect_ratio_drift_rejected():
    validator = VisualAnchorValidator(max_aspect_drift=0.25)
    # Demo is tall (100x200, ratio 0.5), candidate is wide (300x150, ratio 2.0)
    demo = Image.new("RGB", (100, 200), color="blue")
    cand = Image.new("RGB", (300, 150), color="blue")
    buf = io.BytesIO()
    demo.save(buf, format="JPEG")
    demo_bytes = buf.getvalue()

    is_valid, drift, reason = validator.validate_candidate_against_demo(cand, demo_bytes)
    assert is_valid is False
    assert "Aspect ratio mismatch" in reason


def test_candidate_resolver_tier1_success():
    off_mock = MagicMock()
    off_mock.get_front_packshot_url.return_value = "https://off.org/front.jpg"

    downloader_mock = MagicMock()
    sample_img = Image.new("RGB", (800, 800), color="blue")
    downloader_mock.download_and_validate.return_value = (sample_img, b"fake_bytes", "OK")

    resolver = CandidateResolver(
        off_client=off_mock,
        downloader=downloader_mock,
    )

    catalog_item = {"barcode": "12345", "brand": "TestBrand"}
    img, data, source = resolver.resolve_best_candidate(catalog_item)
    assert img is not None
    assert source == "OpenFoodFacts"
