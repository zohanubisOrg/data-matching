import pytest
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

from product_mapper.harvest.canvas_standardizer import CanvasStandardizerAndEnhancer


def test_standardize_and_enhance_crisp_image(tmp_path: Path):
    standardizer = CanvasStandardizerAndEnhancer(target_dim=512, fill_ratio=0.84, min_laplacian=10.0)

    # Create image with high-contrast text / patterns to ensure Laplacian variance >= 10.0
    img = Image.new("RGBA", (300, 300), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    # Draw checkered pattern
    for x in range(50, 250, 10):
        for y in range(50, 250, 10):
            color = (0, 0, 0, 255) if (x + y) % 20 == 0 else (200, 50, 50, 255)
            draw.rectangle([x, y, x + 8, y + 8], fill=color)

    success, path, score, msg = standardizer.standardize_and_enhance(
        img=img,
        barcode="1234567890123",
        output_dir=tmp_path,
    )

    assert success is True
    assert path is not None
    assert path.name == "1234567890123-front.jpg"
    assert path.exists()

    # Verify final image dimensions
    saved_img = Image.open(path)
    assert saved_img.size == (512, 512)
    assert score >= 10.0


def test_standardize_and_enhance_blurry_rejection(tmp_path: Path):
    # Setting an unrealistically high threshold forces blur rejection
    standardizer = CanvasStandardizerAndEnhancer(target_dim=512, min_laplacian=99999.0)

    img = Image.new("RGB", (300, 300), (200, 200, 200))
    success, path, score, msg = standardizer.standardize_and_enhance(
        img=img,
        barcode="9999999999999",
        output_dir=tmp_path,
    )

    assert success is False
    assert path is None
    assert "Rejected: Laplacian sharpness score" in msg
    assert not (tmp_path / "9999999999999-front.jpg").exists()
