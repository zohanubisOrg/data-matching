#!/usr/bin/env python3
"""Copy the customer workbook and replace only column X drawings."""
from __future__ import annotations

import hashlib
import io
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from PIL import Image
from product_mapper.vision.front_v5_ledger import validate_release

XDR = "{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"
COLUMN_X = "23"
PROTECTED_COLUMNS = {"22", "24"}


def _thumb_bytes(path: Path, side: int = 115) -> bytes:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        rgb.thumbnail((side, side), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        rgb.save(buffer, "JPEG", quality=90)
        return buffer.getvalue()


def _anchor_col_row(anchor: ET.Element) -> tuple[str | None, int | None]:
    column = anchor.find(f"{XDR}from/{XDR}col")
    row = anchor.find(f"{XDR}from/{XDR}row")
    if column is None or row is None or column.text is None or row.text is None:
        return None, None
    return column.text, int(row.text)


def _rid(anchor: ET.Element) -> str | None:
    blip = anchor.find(f".//{A}blip")
    if blip is None:
        return None
    return blip.get(f"{REL}embed")


def rewrite_drawing(drawing_xml: bytes, accepted_rows: dict[int, bytes]) -> tuple[bytes, dict[str, bytes], set[str]]:
    """Replace column X media. Return xml, rid->jpeg bytes, and protected rIds."""
    root = ET.fromstring(drawing_xml)
    protected: set[str] = set()
    column_x = []
    for anchor in list(root):
        column, row = _anchor_col_row(anchor)
        rid = _rid(anchor)
        if column in PROTECTED_COLUMNS and rid:
            protected.add(rid)
        if column == COLUMN_X and row is not None:
            column_x.append((anchor, row + 1, rid))
    x_rows = [excel_row for _anchor, excel_row, _rid in column_x]
    if len(x_rows) != len(set(x_rows)):
        raise RuntimeError("duplicate X anchor rows")
    missing = set(accepted_rows) - set(x_rows)
    if missing:
        raise RuntimeError(f"accepted rows have no X anchor: {sorted(missing)}")
    writes: dict[str, bytes] = {}
    for anchor, excel_row, rid in column_x:
        if excel_row not in accepted_rows or rid is None or rid in protected:
            root.remove(anchor)
            continue
        writes[rid] = accepted_rows[excel_row]
    for number, node in enumerate(root.iter(f"{XDR}cNvPr"), start=1):
        node.set("id", str(number))
        node.set("name", f"Picture {number}")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), writes, protected


def _relationship_targets(rels_xml: bytes) -> dict[str, str]:
    root = ET.fromstring(rels_xml)
    targets = {}
    for node in root:
        rid = node.get("Id")
        target = node.get("Target")
        if rid and target:
            targets[rid] = target
    return targets


def _media_name(target: str) -> str:
    cleaned = target.split("?")[0].lstrip("/")
    if cleaned.startswith("../"):
        cleaned = "xl/" + cleaned.removeprefix("../")
    return cleaned


def embed_column_x(
    source: Path,
    destination: Path,
    accepted_rows: dict[int, Path],
    *,
    ledger: list[dict] | None = None,
    release: dict | None = None,
    run_fingerprint: str | None = None,
) -> dict:
    if ledger is None or release is None or not run_fingerprint:
        raise ValueError("release record and ledger are required before embedding")
    validate_release(ledger, release, run_fingerprint)
    released_rows = {row["excel_row"]: Path(row["output_path"]) for row in ledger if row.get("state") == "ACCEPTED"}
    if accepted_rows != released_rows:
        raise ValueError("embed input rows do not equal the hash-bound release set")
    thumbs = {row: _thumb_bytes(path) for row, path in accepted_rows.items()}
    with zipfile.ZipFile(source, "r") as archive:
        files = {info.filename: archive.read(info.filename) for info in archive.infolist()}
    drawing, writes, protected = rewrite_drawing(files["xl/drawings/drawing1.xml"], thumbs)
    targets = _relationship_targets(files["xl/drawings/_rels/drawing1.xml.rels"])
    protected_hashes = {}
    for rid in protected:
        name = _media_name(targets[rid])
        protected_hashes[name] = hashlib.sha256(files[name]).hexdigest()
    for rid, payload in writes.items():
        if rid in protected:
            raise RuntimeError(f"refusing to replace a W/Y image via {rid}")
        files[_media_name(targets[rid])] = payload
    files["xl/drawings/drawing1.xml"] = drawing
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.stem}-", suffix=".tmp", dir=destination.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, payload in files.items():
                archive.writestr(name, payload)
        with zipfile.ZipFile(temporary, "r") as archive:
            for name, digest in protected_hashes.items():
                if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                    raise RuntimeError(f"protected media changed: {name}")
            root = ET.fromstring(archive.read("xl/drawings/drawing1.xml"))
        ids = [node.get("id") for node in root.iter(f"{XDR}cNvPr")]
        if ids != [str(number) for number in range(1, len(ids) + 1)]:
            raise RuntimeError("drawing ids are not sequential")
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {"protected_media": len(protected_hashes), "replaced": len(writes), "drawing_ids": len(ids)}
