from pathlib import Path
import json

import typer

from .config import DEFAULT_IMAGES, DEFAULT_IMPORTS, DEFAULT_OUTPUT, DEFAULT_POS
from .pipeline import run

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _paths(values: list[Path] | None) -> list[Path]: return values or DEFAULT_IMAGES


@app.command("run")
def run_command(images: list[Path] = typer.Option(None, "--images", exists=True, file_okay=False), pos: Path = typer.Option(DEFAULT_POS, "--pos", exists=True, dir_okay=False), imports: Path = typer.Option(DEFAULT_IMPORTS, "--imports", exists=True, dir_okay=False), output: Path = typer.Option(DEFAULT_OUTPUT, "--output"), auto_threshold: float = typer.Option(.80, "--auto-threshold", min=0, max=1), review_threshold: float = typer.Option(.60, "--review-threshold", min=0, max=1), top_k: int = typer.Option(3, "--top-k", min=1, max=20), verbose: bool = typer.Option(False, "--verbose")):
    typer.echo(json.dumps(run(_paths(images), pos, imports, output, auto_threshold, review_threshold, top_k, verbose), indent=2))


@app.command()
def profile(images: list[Path] = typer.Option(None, "--images", exists=True, file_okay=False), pos: Path = typer.Option(DEFAULT_POS, "--pos", exists=True, dir_okay=False), imports: Path = typer.Option(DEFAULT_IMPORTS, "--imports", exists=True, dir_okay=False), output: Path = typer.Option(DEFAULT_OUTPUT, "--output")):
    # Profile is deliberately implemented through the same safe ingestion path; it never matches.
    from .ingestion.image_loader import load_images
    from .ingestion.pos_loader import load_pos
    from .ingestion.supplier_loader import load_imports
    from .reporting.profile_report import profile_workbooks, write_profile
    products, pi, pm = load_pos(pos); suppliers, im = load_imports(imports); imgs, ii, xm = load_images(_paths(images)); write_profile(profile_workbooks(pos, imports, _paths(images), pm, im, xm, pi + ii), output); typer.echo(json.dumps({"pos_products": len(products), "imported_products": len(suppliers), "images": len(imgs)}, indent=2))


@app.command("apply-review")
def apply_review_command(
    review_file: Path = typer.Option(DEFAULT_OUTPUT / "customer_review.xlsx", "--review-file", exists=True, dir_okay=False),
    kb_file: Path = typer.Option(DEFAULT_OUTPUT / "knowledge_base.json", "--kb-file"),
):
    """Imports human review decisions from customer_review.xlsx into knowledge_base.json for Level 1 deterministic matching."""
    from .matching.knowledge_base import import_review_decisions
    count = import_review_decisions(review_file, kb_file)
    typer.echo(f"Successfully imported {count} review decisions into {kb_file}")


if __name__ == "__main__": app()
