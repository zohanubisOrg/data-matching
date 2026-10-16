import pytest
import numpy as np
from PIL import Image
from product_mapper.harvest.studio_quality_validator import StudioQualityValidator


def test_clean_studio_packshot_passes():
    validator = StudioQualityValidator()
    # Create synthetic 800x800 image with pure white background (255, 255, 255)
    img = Image.new("RGB", (800, 800), color=(255, 255, 255))
    # Put a simulated blue box in center
    arr = np.array(img)
    arr[200:600, 200:600] = [20, 50, 180]
    clean_img = Image.fromarray(arr)

    is_compliant, violations = validator.validate_studio_compliance(clean_img)
    assert is_compliant is True
    assert len(violations) == 0


def test_casual_domestic_room_background_rejected():
    validator = StudioQualityValidator()
    # Create image with room background (gray/beige wall: 150, 140, 130)
    img = Image.new("RGB", (800, 800), color=(150, 140, 130))
    is_compliant, violations = validator.validate_studio_compliance(img)
    assert is_compliant is False
    assert any("Non-studio" in v for v in violations)


def test_hand_holding_product_rejected():
    validator = StudioQualityValidator()
    # Create white canvas
    arr = np.full((800, 800, 3), 255, dtype=np.uint8)
    # Simulate a product in the center
    arr[150:650, 250:550] = [200, 30, 30]
    # Simulate a human hand holding the package from the right edge with typical skin tone (RGB: 220, 160, 130)
    arr[350:550, 500:800] = [220, 160, 130]
    img = Image.fromarray(arr)

    is_compliant, violations = validator.validate_studio_compliance(img)
    assert is_compliant is False
    assert any("Human hand" in v or "Non-studio" in v for v in violations)


def test_transparent_png_passes():
    validator = StudioQualityValidator()
    # Transparent RGBA image
    rgba = Image.new("RGBA", (800, 800), (0, 0, 0, 0))
    arr = np.array(rgba)
    # Draw green product in center with full opacity
    arr[200:600, 200:600] = [30, 180, 50, 255]
    img = Image.fromarray(arr)

    is_compliant, violations = validator.validate_studio_compliance(img)
    assert is_compliant is True
    assert len(violations) == 0
