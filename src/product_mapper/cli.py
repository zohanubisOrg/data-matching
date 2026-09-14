from pathlib import Path
import json

import typer

from .config import DEFAULT_IMAGES, DEFAULT_IMPORTS, DEFAULT_OUTPUT, DEFAULT_POS
from .pipeline import run

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _paths(values: list[Path] | None) -> list[Path]:
    return values or DEFAULT_IMAGES


@app.command("run")
def run_command(
    images: list[Path] = typer.Option(None, "--images", exists=True, file_okay=False),
    pos: Path = typer.Option(DEFAULT_POS, "--pos", exists=True, dir_okay=False),
    imports: Path = typer.Option(DEFAULT_IMPORTS, "--imports", exists=True, dir_okay=False),
    output: Path = typer.Option(DEFAULT_OUTPUT, "--output"),
    top_k: int = typer.Option(3, "--top-k", min=1, max=20),
    verbose: bool = typer.Option(False, "--verbose"),
    ocr_provider: str = typer.Option(
        "none",
        "--ocr-provider",
        help="OCR evidence provider for strict image matching: none or paddle.",
    ),
):
    """Run strict barcode-first image reconciliation; fuzzy thresholds do not apply."""
    typer.echo(json.dumps(run(
        _paths(images),
        pos,
        imports,
        output,
        top_k=top_k,
        verbose=verbose,
        ocr_provider=ocr_provider,
    ), indent=2))


@app.command("match-names")
def match_names_legacy_fuzzy_command(
    pos: Path = typer.Option(DEFAULT_POS, "--pos", exists=True, dir_okay=False),
    imports: Path = typer.Option(DEFAULT_IMPORTS, "--imports", exists=True, dir_okay=False),
    output: Path = typer.Option(DEFAULT_OUTPUT / "legacy-fuzzy", "--output"),
    auto_threshold: float = typer.Option(.88, "--auto-threshold", min=0, max=1),
    review_threshold: float = typer.Option(.72, "--review-threshold", min=0, max=1),
    ambiguity_margin: float = typer.Option(.04, "--ambiguity-margin", min=0, max=1),
):
    """Legacy fuzzy benchmark only; never used by the production image pipeline."""
    try:
        from .ingestion.pos_loader import load_pos
        from .ingestion.supplier_loader import load_imports
        from .matching.name_only import match_import_names, summarize_name_matches, write_name_match_outputs
    except ImportError as exc:
        raise typer.BadParameter(
            "Legacy fuzzy benchmark dependencies are not installed. "
            "Install with: python -m pip install -e '.[legacy-fuzzy]'"
        ) from exc

    products, _, _ = load_pos(pos)
    supplier_rows, _ = load_imports(imports)
    rows = match_import_names(products, supplier_rows, auto_threshold, review_threshold, ambiguity_margin)
    summary = summarize_name_matches(rows)
    paths = write_name_match_outputs(rows, summary, output)
    typer.echo(json.dumps({
        **summary,
        "outputs": {key: str(value) for key, value in paths.items()},
    }, ensure_ascii=False, indent=2))


@app.command("match-names-no-fuzzy")
def match_names_no_fuzzy_command(
    pos: Path = typer.Option(DEFAULT_POS, "--pos", exists=True, dir_okay=False),
    imports: Path = typer.Option(DEFAULT_IMPORTS, "--imports", exists=True, dir_okay=False),
    output: Path = typer.Option(DEFAULT_OUTPUT / "no-fuzzy", "--output"),
):
    """Deterministically match import names to POS names without images or fuzzy scoring."""
    from .ingestion.pos_loader import load_pos
    from .ingestion.supplier_loader import load_imports
    from .matching.no_fuzzy import (
        match_import_names_no_fuzzy,
        summarize_no_fuzzy_matches,
        write_no_fuzzy_outputs,
    )

    products, _, _ = load_pos(pos)
    supplier_rows, _ = load_imports(imports)
    rows = match_import_names_no_fuzzy(products, supplier_rows)
    summary = summarize_no_fuzzy_matches(rows)
    paths = write_no_fuzzy_outputs(rows, summary, output)
    typer.echo(json.dumps({
        **summary,
        "outputs": {key: str(value) for key, value in paths.items()},
    }, ensure_ascii=False, indent=2))


@app.command()
def profile(
    images: list[Path] = typer.Option(None, "--images", exists=True, file_okay=False),
    pos: Path = typer.Option(DEFAULT_POS, "--pos", exists=True, dir_okay=False),
    imports: Path = typer.Option(DEFAULT_IMPORTS, "--imports", exists=True, dir_okay=False),
    output: Path = typer.Option(DEFAULT_OUTPUT, "--output"),
):
    from .ingestion.image_loader import load_images
    from .ingestion.pos_loader import load_pos
    from .ingestion.supplier_loader import load_imports
    from .reporting.profile_report import profile_workbooks, write_profile

    products, pi, pm = load_pos(pos)
    suppliers, im = load_imports(imports)
    imgs, ii, xm = load_images(_paths(images))
    write_profile(profile_workbooks(pos, imports, _paths(images), pm, im, xm, pi + ii), output)
    typer.echo(json.dumps({
        "pos_products": len(products),
        "imported_products": len(suppliers),
        "images": len(imgs),
    }, indent=2))


@app.command("apply-review")
def apply_review_command(
    review_file: Path = typer.Option(DEFAULT_OUTPUT / "customer_review.xlsx", "--review-file", exists=True, dir_okay=False),
    kb_file: Path = typer.Option(DEFAULT_OUTPUT / "knowledge_base.json", "--kb-file"),
):
    """Imports human review decisions from customer_review.xlsx into knowledge_base.json."""
    from .matching.knowledge_base import import_review_decisions

    count = import_review_decisions(review_file, kb_file)
    typer.echo(f"Successfully imported {count} review decisions into {kb_file}")


if __name__ == "__main__":
    app()
