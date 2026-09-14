from pathlib import Path

from product_mapper.models import MatchResult, ProductImage
from product_mapper.reporting.image_exporter import export_standard_deliverables


def unresolved(path: Path, status: str = "UNMATCHED") -> MatchResult:
    return MatchResult(
        image=ProductImage(path=path, filename=path.name, normalized_name="unknown"),
        status=status,
        reason="no deterministic candidate",
    )


def test_duplicate_unresolved_filenames_are_preserved_without_overwrite(tmp_path):
    first_dir = tmp_path / "a"
    second_dir = tmp_path / "b"
    first_dir.mkdir()
    second_dir.mkdir()
    first = first_dir / "image.jpg"
    second = second_dir / "image.jpg"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    out = tmp_path / "out"
    summary = export_standard_deliverables(
        [unresolved(first), unresolved(second)],
        out,
    )

    preserved = sorted((out / "unmatched-images").glob("image*.jpg"))
    assert len(preserved) == 2
    assert {path.read_bytes() for path in preserved} == {b"first", b"second"}
    assert summary["unmatched_count"] == 2
