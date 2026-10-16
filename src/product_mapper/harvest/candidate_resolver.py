"""
Candidate Resolver with Backtracking and Query Mutation.
Orchestrates multi-tier harvesting, visual anchoring, and Gemini validation with safe aborts.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple
from PIL import Image

from .openfoodfacts_client import OpenFoodFactsClient
from .google_images_harvester import GoogleImagesHarvester
from .image_downloader import ImageDownloaderAndFilter
from .visual_anchor import VisualAnchorValidator
from .gemini_auditor import GeminiPackagingAuditor
from .studio_quality_validator import StudioQualityValidator

logger = logging.getLogger(__name__)


class CandidateResolver:
    """Resolves and validates the single best front packshot for a given catalog SKU."""

    def __init__(
        self,
        off_client: Optional[OpenFoodFactsClient] = None,
        google_harvester: Optional[GoogleImagesHarvester] = None,
        downloader: Optional[ImageDownloaderAndFilter] = None,
        visual_validator: Optional[VisualAnchorValidator] = None,
        gemini_auditor: Optional[GeminiPackagingAuditor] = None,
        studio_validator: Optional[StudioQualityValidator] = None,
    ):
        self.off_client = off_client or OpenFoodFactsClient()
        self.google_harvester = google_harvester or GoogleImagesHarvester()
        self.downloader = downloader or ImageDownloaderAndFilter(min_dim=600)
        self.visual_validator = visual_validator or VisualAnchorValidator(max_aspect_drift=0.25)
        self.gemini_auditor = gemini_auditor or GeminiPackagingAuditor()
        self.studio_validator = studio_validator or StudioQualityValidator()

    def resolve_best_candidate(
        self,
        catalog_item: Dict[str, Any],
        demo_img_bytes: Optional[bytes] = None,
    ) -> Tuple[Optional[Image.Image], Optional[bytes], str]:
        """
        Attempts multi-tier candidate retrieval and verification.
        Returns: (approved_image, raw_bytes, source_description) or (None, None, failure_reason)
        """
        bc = str(catalog_item.get("barcode") or "").strip()
        brand = str(catalog_item.get("brand") or "").strip()
        name_en = str(catalog_item.get("full_name_en") or "").strip()
        name_da = str(catalog_item.get("fuldt_navn_da") or "").strip()
        variant = str(catalog_item.get("variant") or "").strip()
        net_qty = str(catalog_item.get("net_quantity") or "").strip()
        net_unit = str(catalog_item.get("net_unit") or "g").strip()

        # -------------------------------------------------------------
        # TIER 1: OpenFoodFacts Direct API
        # -------------------------------------------------------------
        if bc:
            off_url = self.off_client.get_front_packshot_url(bc)
            if off_url:
                img, data, reason = self.downloader.download_and_validate(off_url)
                if img:
                    is_studio, studio_violations = self.studio_validator.validate_studio_compliance(img)
                    if not is_studio:
                        logger.info(f"[{bc}] OpenFoodFacts candidate rejected: {'; '.join(studio_violations)}")
                    else:
                        aspect_ok, drift, a_reason = self.visual_validator.validate_candidate_against_demo(
                            img, demo_img_bytes
                        )
                        if aspect_ok:
                            verdict = self.gemini_auditor.audit_candidate(img, catalog_item)
                            if verdict.is_approved:
                                logger.info(f"[{bc}] Approved via OpenFoodFacts Tier 1.")
                                return img, data, "OpenFoodFacts"

        # -------------------------------------------------------------
        # TIER 2: Google Images Strict Barcode Query
        # -------------------------------------------------------------
        candidates_t2 = []
        if bc:
            candidates_t2 = self.google_harvester.search_candidates(f'"{bc}"', limit=3)

        for cand in candidates_t2:
            img, data, d_reason = self.downloader.download_and_validate(cand.url)
            if not img:
                continue

            is_studio, studio_violations = self.studio_validator.validate_studio_compliance(img)
            if not is_studio:
                logger.info(f"[{bc}] Google Barcode candidate rejected: {'; '.join(studio_violations)}")
                continue

            aspect_ok, drift, a_reason = self.visual_validator.validate_candidate_against_demo(
                img, demo_img_bytes
            )
            if not aspect_ok:
                continue

            verdict = self.gemini_auditor.audit_candidate(img, catalog_item)
            if verdict.is_approved:
                logger.info(f"[{bc}] Approved via Google Images Barcode Query (Candidate {cand.url[:35]}...).")
                return img, data, "Google_Images_Barcode"

        # -------------------------------------------------------------
        # TIER 3: Query Mutation (Brand + Variant/Name + Packaging)
        # -------------------------------------------------------------
        query_terms = []
        if brand and brand != "Khác":
            query_terms.append(f'"{brand}"')
        if variant:
            query_terms.append(f'"{variant}"')
        elif name_en:
            query_terms.append(f'"{name_en[:30]}"')
        elif name_da:
            query_terms.append(f'"{name_da[:30]}"')

        if net_qty:
            query_terms.append(f'"{net_qty}{net_unit}"')
        query_terms.append("packshot white background")

        mutated_query = " ".join(query_terms)
        candidates_t3 = self.google_harvester.search_candidates(mutated_query, limit=2)

        for cand in candidates_t3:
            img, data, d_reason = self.downloader.download_and_validate(cand.url)
            if not img:
                continue

            is_studio, studio_violations = self.studio_validator.validate_studio_compliance(img)
            if not is_studio:
                logger.info(f"[{bc}] Google Mutated candidate rejected: {'; '.join(studio_violations)}")
                continue

            aspect_ok, drift, a_reason = self.visual_validator.validate_candidate_against_demo(
                img, demo_img_bytes
            )
            if not aspect_ok:
                continue

            verdict = self.gemini_auditor.audit_candidate(img, catalog_item)
            if verdict.is_approved:
                logger.info(f"[{bc}] Approved via Google Images Mutated Query.")
                return img, data, "Google_Images_Mutated"

        # Safe abort to reshoot list
        return None, None, "No candidate passed multi-tier verification (kept in Reshoot)"
