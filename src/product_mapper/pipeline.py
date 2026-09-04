from pathlib import Path
import logging
import time

from .config import DEFAULT_IMAGES, DEFAULT_IMPORTS, DEFAULT_OUTPUT, DEFAULT_POS
from .ingestion.image_loader import load_images
from .ingestion.pos_loader import load_pos
from .ingestion.supplier_loader import load_imports
from .matching.matcher import match_image
from .matching.candidate_generator import CandidateGenerator
from .models import DataQualityIssue, MatchCandidate, MatchResult
from .vision.barcode_reader import BarcodeReader
from .reporting.excel_report import write_reports
from .reporting.html_report import write_html
from .reporting.profile_report import profile_workbooks, write_profile
from .reporting.image_exporter import export_standard_deliverables
from .matching.knowledge_base import load_knowledge_base


def configure_logging(output: Path, verbose: bool = False) -> logging.Logger:
    output.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("product_mapper"); logger.handlers.clear(); logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler(output / "run.log", encoding="utf-8"); handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s")); logger.addHandler(handler)
    if verbose:
        console = logging.StreamHandler(); console.setLevel(logging.INFO); logger.addHandler(console)
    return logger


def run(images: list[Path] | None = None, pos: Path = DEFAULT_POS, imports: Path = DEFAULT_IMPORTS, output: Path = DEFAULT_OUTPUT, auto_threshold: float = .80, review_threshold: float = .60, top_k: int = 3, verbose: bool = False) -> dict:
    started = time.perf_counter(); images = images or DEFAULT_IMAGES; logger = configure_logging(output, verbose); logger.info("run start pos=%s imports=%s images=%s", pos, imports, images)
    products, pos_issues, pos_meta = load_pos(pos); suppliers, import_meta = load_imports(imports); parsed_images, image_issues, image_meta = load_images(images)
    issues: list[DataQualityIssue] = pos_issues + image_issues
    profile = profile_workbooks(pos, imports, images, pos_meta, import_meta, image_meta, issues); write_profile(profile, output)
    results: list[MatchResult] = []; generator = CandidateGenerator(products); barcode_reader = BarcodeReader(); logger.info("barcode reader available=%s", barcode_reader.available)
    kb = load_knowledge_base(output / "knowledge_base.json")
    if not kb and Path("knowledge_base.json").exists():
        kb = load_knowledge_base(Path("knowledge_base.json"))
    for index, image in enumerate(parsed_images, 1):
        try:
            if image.filename in kb and kb[image.filename].get("barcode"):
                approved_bc = kb[image.filename]["barcode"]
                hits = [p for p in products if p.barcode == approved_bc]
                if len(hits) == 1:
                    candidate = MatchCandidate(product=hits[0], score=1.0, evidence=["human-approved decision from knowledge base"])
                    result = MatchResult(image=image, status="AUTO_MATCHED", candidate=candidate, top_candidates=[candidate], confidence=1.0, top2_score=0, margin=1.0, match_method="exact_human_approved", reason="human verified mapping", evidence=candidate.evidence)
                else:
                    result = match_image(image, products, suppliers, auto_threshold, review_threshold, top_k, generator)
            elif image.filename in kb and kb[image.filename].get("selection") == "No Match":
                result = MatchResult(image=image, status="UNMATCHED", confidence=0.0, match_method="exact_human_approved", reason="human confirmed no match")
            else:
                result = match_image(image, products, suppliers, auto_threshold, review_threshold, top_k, generator)
                decoded = barcode_reader.analyze(image.path).barcode
                if decoded:
                    barcode_hits = [p for p in products if p.barcode == decoded]
                    if len(barcode_hits) == 1:
                        candidate = MatchCandidate(product=barcode_hits[0], score=1.0, evidence=[f"exact decoded POS barcode: {decoded}"])
                        result = MatchResult(image=image, status="AUTO_MATCHED", candidate=candidate, top_candidates=[candidate], confidence=1.0, top2_score=0, margin=1.0, match_method="exact_barcode", reason="unique decoded barcode found in POS", evidence=candidate.evidence)
                    else:
                        result.status = "NEED_REVIEW"
                        result.reason = ("BARCODE_NOT_FOUND_IN_POS" if not barcode_hits else "duplicate POS barcode for decoded value") + "; " + result.reason
            results.append(result)
        except Exception as exc: results.append(MatchResult(image=image, status="ERROR", reason="matching failed", error=str(exc))); logger.exception("matching failed for %s", image.filename)
        if index % 50 == 0: logger.info("matching progress %s/%s", index, len(parsed_images))
    write_reports(results, issues, profile, output); write_html(results, output)
    deliverables = export_standard_deliverables(results, output, total_pos_count=len(products))
    counts = {x: sum(r.status == x for r in results) for x in ["AUTO_MATCHED", "NEED_REVIEW", "UNMATCHED", "ERROR"]}; summary = {"pos_products": len(products), "imported_products": len(suppliers), "images": len(parsed_images), **{k.lower(): v for k, v in counts.items()}, **deliverables, "runtime_seconds": round(time.perf_counter() - started, 3)}
    logger.info("final summary %s", summary); return summary
