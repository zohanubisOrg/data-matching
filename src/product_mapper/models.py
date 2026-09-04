from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class POSProduct(BaseModel):
    product_id: str
    sku: str
    barcode: str | None = None
    category: str = ""
    product_name: str = ""
    official_name: str = ""
    printer_name: str = ""
    stock_price: str = ""
    selling_price: str = ""
    unit: str = ""


class SupplierProduct(BaseModel):
    name: str
    supplier: str
    supplier_sku: str | None = None
    sheet: str = ""


class Packaging(BaseModel):
    levels: list[tuple[float, str]] = Field(default_factory=list)
    raw: str = ""


class ProductImage(BaseModel):
    path: Path
    filename: str
    source: str | None = None
    source_product_id: str | None = None
    raw_name: str = ""
    normalized_name: str = ""
    brand: str | None = None
    variants: set[str] = Field(default_factory=set)
    packaging: Packaging = Field(default_factory=Packaging)


class MatchCandidate(BaseModel):
    product: POSProduct
    score: float
    name_score: float = 0
    brand_score: float = 0
    size_score: float = 0
    variant_score: float = 0
    supplier_score: float = 0
    bridge_score: float = 0
    conflicts: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class MatchResult(BaseModel):
    image: ProductImage
    status: str
    candidate: MatchCandidate | None = None
    top_candidates: list[MatchCandidate] = Field(default_factory=list)
    confidence: float = 0
    top2_score: float = 0
    margin: float = 0
    match_method: str = "none"
    reason: str = ""
    evidence: list[str] = Field(default_factory=list)
    error: str | None = None


class DataQualityIssue(BaseModel):
    issue_type: str
    field: str = ""
    value: str = ""
    count: int = 1
    details: str = ""

