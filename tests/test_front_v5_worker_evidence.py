import json

import numpy as np
import pytest
from PIL import Image

from product_mapper.vision.front_v5_workers import _load_quality_evidence, _rotate_quality_masks


def test_quality_evidence_loads_reviewed_masks_and_numeric_fields(tmp_path):
    mask = np.zeros((16, 16), dtype=np.uint8)
    mask[2:14, 3:13] = 255
    Image.fromarray(mask).save(tmp_path / "core.png")
    manifest = tmp_path / "8850157516457.json"
    manifest.write_text(json.dumps({"source_complete": True, "mask_files": {"source_core_mask": "core.png"}}), encoding="utf-8")

    evidence = _load_quality_evidence(str(manifest))

    assert evidence["source_complete"] is True
    assert evidence["source_core_mask"].dtype == np.bool_
    assert int(evidence["source_core_mask"].sum()) == 120


def test_quality_evidence_rejects_mask_paths_outside_review_folder(tmp_path):
    outside = tmp_path / "outside.png"
    Image.new("L", (8, 8), 255).save(outside)
    review = tmp_path / "qa"
    review.mkdir()
    manifest = review / "item.json"
    manifest.write_text(json.dumps({"mask_files": {"source_core_mask": "../outside.png"}}), encoding="utf-8")

    with pytest.raises(ValueError, match="must be a file under"):
        _load_quality_evidence(str(manifest))


def test_source_masks_follow_the_same_lossless_rotation_as_the_image():
    mask = np.zeros((4, 6), dtype=bool)
    mask[0, 1] = True

    rotated = _rotate_quality_masks({"source_core_mask": mask}, (6, 4), 90)

    assert rotated["source_core_mask"].shape == (6, 4)
    assert tuple(np.argwhere(rotated["source_core_mask"])[0]) == (4, 0)
