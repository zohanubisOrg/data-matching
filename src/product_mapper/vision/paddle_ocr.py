from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .provider import ImageAttributes, OCRLine


def _plain_list(value: Any) -> list:
    if value is None:
        return []
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, tuple):
        value = list(value)
    return value if isinstance(value, list) else []


def _result_payload(result: Any) -> Mapping[str, Any]:
    payload = getattr(result, "json", result)
    if callable(payload):
        payload = payload()
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, Mapping):
        return {}
    nested = payload.get("res")
    return nested if isinstance(nested, Mapping) else payload


def _polygon(value: Any) -> list[list[float]]:
    points = _plain_list(value)
    result: list[list[float]] = []
    for point in points:
        plain = _plain_list(point)
        if len(plain) >= 2:
            result.append([float(plain[0]), float(plain[1])])
    return result


class PaddleOCRProvider:
    """Optional PaddleOCR 3.x evidence provider.

    The provider only extracts observable OCR evidence. It never decides product identity.
    """

    def __init__(self, engine: Any | None = None, lang: str = "en"):
        if engine is not None:
            self._engine = engine
            return

        try:
            from paddleocr import PaddleOCR  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "PaddleOCR is not installed. Install the OCR extra and a compatible "
                "PaddlePaddle runtime before using --ocr-provider paddle."
            ) from exc

        self._engine = PaddleOCR(
            lang=lang,
            use_doc_orientation_classify=True,
            use_doc_unwarping=False,
            use_textline_orientation=True,
        )

    def analyze(self, image_path: Path) -> ImageAttributes:
        warnings: list[str] = []
        lines: list[OCRLine] = []
        try:
            results = self._engine.predict(str(image_path))
        except Exception as exc:
            return ImageAttributes(warnings=[f"ocr_failed:{type(exc).__name__}"])

        for result in results or []:
            try:
                payload = _result_payload(result)
                texts = _plain_list(payload.get("rec_texts"))
                scores = _plain_list(payload.get("rec_scores"))
                polygons = _plain_list(payload.get("rec_polys"))
                for index, raw_text in enumerate(texts):
                    text = str(raw_text).strip()
                    if not text:
                        continue
                    confidence = float(scores[index]) if index < len(scores) else 0.0
                    polygon = _polygon(polygons[index]) if index < len(polygons) else []
                    lines.append(OCRLine(text=text, confidence=confidence, polygon=polygon))
            except Exception as exc:
                warnings.append(f"ocr_result_parse_failed:{type(exc).__name__}")

        return ImageAttributes(ocr_lines=lines, warnings=warnings)
