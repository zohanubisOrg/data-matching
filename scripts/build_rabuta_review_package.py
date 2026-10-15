"""Build a navigable, non-accepting review bundle from Rabuta batch results."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import html
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def file_url(value: str) -> str:
    return Path(value).resolve().as_uri()


def make_sheet(items, field: str, output: Path, *, columns: int = 4, cell: int = 420):
    rows = (len(items) + columns - 1) // columns
    label_h = 38
    sheet = Image.new("RGB", (columns * cell, rows * (cell + label_h)), "#e7e7e7")
    draw = ImageDraw.Draw(sheet)
    for i, item in enumerate(items):
        path = item.get(field)
        if not path or not Path(path).is_file():
            continue
        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((cell - 16, cell - 16), Image.Resampling.LANCZOS)
            x = (i % columns) * cell + (cell - im.width) // 2
            y = (i // columns) * (cell + label_h) + label_h + (cell - im.height) // 2
            sheet.paste(im, (x, y))
        label = f"row {item['excel_row']} | {item.get('barcode','')} | {item.get('record_id','')}"
        draw.text(((i % columns) * cell + 8, (i // columns) * (cell + label_h) + 10), label, fill="black")
    sheet.save(output, optimize=True)


def build(results_path: Path, review_dir: Path):
    results = read_jsonl(results_path)
    review_dir.mkdir(parents=True, exist_ok=True)
    candidates = [r for r in results if r.get("output_path") and Path(r["output_path"]).is_file()]
    checks = []
    for row in candidates:
        p = Path(row["output_path"])
        with Image.open(p) as im:
            rgb = np.asarray(im.convert("RGB"))
            check = {
                "excel_row": row["excel_row"], "record_id": row["record_id"], "barcode": row["barcode"],
                "format": im.format, "size": list(im.size), "mode": im.mode,
                "white_canvas_border": all(bool(np.all(edge == 255)) for edge in
                                            (rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1])),
                "source_hash_matches_annotation": row.get("source_sha256") == row.get("annotation", {}).get("source_sha256"),
                "upscale_factor": row.get("layout", {}).get("upscale_factor"),
                "output_sha256": digest(p), "status": row.get("status"), "qa_pass": False,
            }
        checks.append(check)
    (review_dir / "candidate_image_checks.json").write_text(
        json.dumps({"candidate_count": len(checks), "visual_qa_pass_count": 0, "checks": checks},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    make_sheet(candidates, "output_path", review_dir / "candidate_contact_sheet.png")
    make_sheet(candidates, "overlay_path", review_dir / "source_mask_contact_sheet.png")
    statuses = Counter(r.get("status", "UNKNOWN") for r in results)
    publication_path = results_path.resolve().parent / "publication_backup" / "publication.json"
    publication = json.loads(publication_path.read_text(encoding="utf-8")) if publication_path.is_file() else None
    cards = []
    for r in candidates:
        links = [("Source", r.get("source_path")), ("Mask overlay", r.get("overlay_path")),
                 ("Candidate", r.get("output_path")), ("Current front-v3", next(
                     (x.get("path") for x in r.get("current_front_files", [])), None))]
        link_html = " | ".join(f'<a href="{html.escape(file_url(path), quote=True)}">{label}</a>'
                                for label, path in links if path and Path(path).is_file())
        cards.append(f"<section><h2>Row {r['excel_row']} — {html.escape(str(r.get('barcode','')))} — "
                     f"{html.escape(str(r.get('product_name_en','')))}</h2>"
                     f"<p>{html.escape(str(r.get('status','')))} · {html.escape(str(r.get('reason','')))}</p>"
                     f"<p>{link_html}</p></section>")
    body = "\n".join(cards)
    summary = " | ".join(f"{html.escape(k)}: {v}" for k, v in sorted(statuses.items()))
    publication_note = (f"Published under user authorization: {publication.get('published_count', 0)}; "
                        f"skipped: {publication.get('skipped_count', 0)}; publication QA PASS: "
                        f"{publication.get('qa_pass', False)}." if publication else "No publication journal found.")
    page = ("<!doctype html><meta charset='utf-8'><title>Rabuta full-catalog candidate review</title>"
            "<style>body{font:16px system-ui;max-width:1100px;margin:2rem auto}section{border-top:1px solid #bbb;padding:1rem}"
            "a{margin-right:.8rem}</style><h1>Rabuta full-catalog candidate review</h1>"
            f"<p>Records: {len(results)} · candidates: {len(candidates)} · visual QA PASS: 0</p>"
            f"<p>{summary}</p><p>{html.escape(publication_note)}</p><p>Contact sheets are navigation aids; compare source, "
            "mask overlay and output at full resolution. Visual QA PASS count remains 0.</p>" + body)
    (review_dir / "review_index.html").write_text(page, encoding="utf-8")
    (review_dir / "summary.json").write_text(json.dumps({
        "record_count": len(results), "candidate_count": len(candidates),
        "qa_pass_count": 0, "statuses": dict(statuses), "live_front_modified": bool(publication),
        "published_count": publication.get("published_count", 0) if publication else 0,
        "publication_status": publication.get("status") if publication else "NOT_PUBLISHED",
        "results": str(results_path.resolve()),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(results), len(candidates), dict(statuses)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--review-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.results, args.review_dir), ensure_ascii=False))


if __name__ == "__main__":
    main()
