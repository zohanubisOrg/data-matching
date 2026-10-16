"""Deep packshot matting engine with detail preservation and intelligent hole discrimination."""
from __future__ import annotations

import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

import threading
from typing import Any, Dict, Optional, Tuple
import cv2
import numpy as np
from PIL import Image
import rembg


class MattingEngine:
    """Deep packshot matting engine with Hybrid BiRefNet / U2Net and intelligent hole discrimination."""

    _lock = threading.RLock()
    _shared_sessions: Dict[str, Any] = {}
    _call_count: int = 0

    COMPLEX_KEYWORDS = [
        "herb", "vegetable", "produce", "leaf", "coriander", "basil", "mint",
        "onion", "garlic", "chili", "rau", "ngò", "quế", "hành", "tiêu",
        "nấm", "mushroom", "wrap", "wonton", "clear", "transparent", "trong suốt",
        "chai trong", "bóng kính", "bánh tráng", "sauce", "oil", "dầu", "nước mắm",
        "spray", "handle", "quai", "lo"
    ]

    def __init__(self, default_model: str = "birefnet-general-lite"):
        self.default_model = default_model

    def get_session(self, name: str):
        with self._lock:
            if name not in self._shared_sessions:
                try:
                    import onnxruntime as ort
                    sess_opts = ort.SessionOptions()
                    sess_opts.enable_cpu_mem_arena = False
                    self._shared_sessions[name] = rembg.new_session(name, sess_opts=sess_opts)
                except Exception:
                    self._shared_sessions[name] = rembg.new_session("u2net")
            return self._shared_sessions[name]

    def purge_session(self, name: Optional[str] = None):
        with self._lock:
            if name:
                self._shared_sessions.pop(name, None)
            else:
                self._shared_sessions.clear()
        import gc
        gc.collect()

    @property
    def u2net_session(self):
        return self.get_session("u2net")

    @property
    def birefnet_session(self):
        return self.get_session("birefnet-general-lite")

    @classmethod
    def is_complex_packaging(cls, category: Optional[str] = None, name: Optional[str] = None) -> bool:
        """Determines whether product packaging has complex/transparent geometry requiring BiRefNet."""
        text = f"{category or ''} {name or ''}".lower()
        return any(kw in text for kw in cls.COMPLEX_KEYWORDS)

    @staticmethod
    def apply_topological_hole_filling(
        alpha: np.ndarray,
        rgb_bgr: Optional[np.ndarray] = None,
        min_contour_area_ratio: float = 0.0003,
    ) -> np.ndarray:
        """Protects interior transparent packaging windows while preserving real hanging holes (quai treo).

        - Detects true physical openings (hanging slots, handle holes) that show the studio backdrop
          and keeps them open (alpha = 0).
        - Detects hollow-punched transparent plastic windows that show internal spices/noodles/products
          and locks them solid (alpha = 255).
        - Uses a tight 5x5 morphology kernel to preserve crisp 90-degree box corners and fine details.
        """
        try:
            h, w = alpha.shape
            img_area = h * w

            # Threshold low-confidence foreground to find outer shell
            _, bin_mask = cv2.threshold(alpha, 8, 255, cv2.THRESH_BINARY)
            contours, _ = cv2.findContours(bin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if not contours:
                return alpha

            # Retain all significant product components
            min_area = max(80, int(img_area * min_contour_area_ratio))
            sig_cnts = [c for c in contours if cv2.contourArea(c) >= min_area]
            if not sig_cnts:
                sig_cnts = contours

            # Draw filled solid interior mask for all product components
            solid_interior = np.zeros((h, w), dtype=np.uint8)
            cv2.drawContours(solid_interior, sig_cnts, -1, 255, thickness=cv2.FILLED)

            # Restrained closing kernel (5x5) to preserve sharp rectangular box vertices
            k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            solid_interior = cv2.morphologyEx(solid_interior, cv2.MORPH_CLOSE, k_close)

            # Identify candidate interior holes
            holes_mask = (solid_interior == 255) & (bin_mask == 0)

            # If RGB image is available, discriminate between real hanging holes and clear packaging windows
            if rgb_bgr is not None and np.any(holes_mask):
                border_h = max(2, int(h * 0.03))
                border_w = max(2, int(w * 0.03))
                border_pixels = np.concatenate([
                    rgb_bgr[:border_h, :].reshape(-1, 3),
                    rgb_bgr[-border_h:, :].reshape(-1, 3),
                    rgb_bgr[:, :border_w].reshape(-1, 3),
                    rgb_bgr[:, -border_w:].reshape(-1, 3),
                ], axis=0)
                bg_median = np.median(border_pixels, axis=0)

                num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(holes_mask.astype(np.uint8))
                for i in range(1, num_labels):
                    hole_area = stats[i, cv2.CC_STAT_AREA]
                    # Allow protecting larger transparent packaging windows up to 45% of image area
                    if hole_area < 50 or hole_area > (img_area * 0.45):
                        continue

                    x, y, w_box, h_box = (
                        stats[i, cv2.CC_STAT_LEFT],
                        stats[i, cv2.CC_STAT_TOP],
                        stats[i, cv2.CC_STAT_WIDTH],
                        stats[i, cv2.CC_STAT_HEIGHT],
                    )
                    sub_labels = labels[y : y + h_box, x : x + w_box]
                    sub_mask = sub_labels == i
                    if not np.any(sub_mask):
                        continue

                    sub_rgb = rgb_bgr[y : y + h_box, x : x + w_box]
                    mean_bgr = sub_rgb[sub_mask].mean(axis=0)
                    dist_to_bg = float(np.linalg.norm(mean_bgr - bg_median))
                    mean_lum = float(mean_bgr.mean())
                    cy = centroids[i][1]

                    # Only genuine small hanging slots (quai treo) in top 35% are allowed to be transparent
                    is_real_hanging_hole = (
                        (cy < (h * 0.35) and hole_area < (img_area * 0.025) and dist_to_bg < 30.0 and mean_lum > 200.0)
                        or (cy < (h * 0.25) and hole_area < (img_area * 0.015) and dist_to_bg < 18.0)
                    )

                    if is_real_hanging_hole:
                        sub_solid = solid_interior[y : y + h_box, x : x + w_box]
                        sub_solid[sub_mask] = 0
                        solid_interior[y : y + h_box, x : x + w_box] = sub_solid

                # Non-invasive Edge Recovery: recover white labels, glossy cellophane and packaging borders
                # that were falsely eroded or gouged by raw AI matting
                border_std = np.std(border_pixels, axis=0)
                bg_thresh = max(22.0, float(np.mean(border_std) * 2.2))
                color_diff = np.linalg.norm(rgb_bgr.astype(np.float32) - bg_median.astype(np.float32), axis=-1)

                for cnt in sig_cnts:
                    hull = cv2.convexHull(cnt)
                    hull_mask = np.zeros((h, w), dtype=np.uint8)
                    cv2.drawContours(hull_mask, [hull], -1, 255, thickness=cv2.FILLED)

                    gap_mask = (hull_mask == 255) & (bin_mask == 0)
                    restore_mask = gap_mask & (color_diff > bg_thresh)
                    solid_interior[restore_mask] = 255

            # Retain full solid interior without destructive erosion to prevent edge loss
            enhanced_alpha = np.maximum(alpha, solid_interior)

            return enhanced_alpha
        except Exception:
            return alpha

    def _infer_mask(self, img: Image.Image, model_name: str) -> np.ndarray:
        """Internal helper to infer alpha mask using a specific rembg model."""
        orig_w, orig_h = img.size
        max_dim = max(orig_w, orig_h)
        if max_dim > 1024:
            scale = 1024.0 / max_dim
            proc_img = img.resize((int(orig_w * scale), int(orig_h * scale)), Image.Resampling.BILINEAR)
        else:
            proc_img = img

        with self._lock:
            sess = self.get_session(model_name)
            raw_mask_pil = rembg.remove(proc_img, session=sess, only_mask=True)

        if raw_mask_pil is None or raw_mask_pil.size != (orig_w, orig_h):
            if raw_mask_pil is not None:
                resized_mask = raw_mask_pil.resize((orig_w, orig_h), Image.Resampling.BILINEAR)
                raw_mask_pil.close()
                raw_mask_pil = resized_mask
            else:
                raw_mask_pil = Image.new("L", (orig_w, orig_h), 255)
        res_arr = np.array(raw_mask_pil)
        raw_mask_pil.close()
        if proc_img is not img:
            proc_img.close()
        return res_arr

    @staticmethod
    def _evaluate_mask_solidity(alpha: np.ndarray) -> Tuple[float, int]:
        """Calculates solidity and significant component count to detect hollowed masks."""
        _, bin_mask = cv2.threshold(alpha, 128, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(bin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return 0.0, 0
        img_area = alpha.shape[0] * alpha.shape[1]
        sig_cnts = [c for c in contours if cv2.contourArea(c) >= (img_area * 0.01)]
        if not sig_cnts:
            return 0.5, 0
        main_cnt = max(sig_cnts, key=cv2.contourArea)
        area = cv2.contourArea(main_cnt)
        hull = cv2.convexHull(main_cnt)
        hull_area = cv2.contourArea(hull)
        solidity = float(area / max(1.0, hull_area))
        return solidity, len(sig_cnts)

    @staticmethod
    def apply_white_bleed_defringing(
        rgb_arr: np.ndarray,
        alpha_arr: np.ndarray,
        bg_distance_threshold: float = 32.0,
    ) -> np.ndarray:
        """Bleeds studio backdrop residue in the soft transition margin towards pure white (#FFFFFF).
        
        Preserves translucent glass and cellophane boundaries without dark or muddy halos on white canvas.
        """
        h, w = alpha_arr.shape
        border_h = max(2, int(h * 0.03))
        border_w = max(2, int(w * 0.03))
        border_pixels = np.concatenate([
            rgb_arr[:border_h, :].reshape(-1, 3),
            rgb_arr[-border_h:, :].reshape(-1, 3),
            rgb_arr[:, :border_w].reshape(-1, 3),
            rgb_arr[:, -border_w:].reshape(-1, 3),
        ], axis=0)
        bg_median = np.median(border_pixels, axis=0).astype(np.float32)

        transition_mask = (alpha_arr > 10) & (alpha_arr < 180)
        if not np.any(transition_mask):
            return rgb_arr

        out_rgb = rgb_arr.copy()
        trans_rgb = out_rgb[transition_mask].astype(np.float32)
        diff_to_bg = np.linalg.norm(trans_rgb - bg_median, axis=-1)

        near_bg = diff_to_bg < bg_distance_threshold
        if np.any(near_bg):
            trans_alphas = alpha_arr[transition_mask][near_bg].astype(np.float32) / 255.0
            weights = trans_alphas[:, np.newaxis]
            blended = weights * trans_rgb[near_bg] + (1.0 - weights) * 255.0

            indices = np.where(transition_mask)
            near_bg_y = indices[0][near_bg]
            near_bg_x = indices[1][near_bg]
            out_rgb[near_bg_y, near_bg_x] = np.clip(blended, 0, 255).astype(np.uint8)

        return out_rgb

    def remove_background(
        self,
        img: Image.Image,
        enable_hole_protection: bool = True,
        is_complex: bool = False,
        allow_escalation: bool = True,
    ) -> Tuple[Image.Image, np.ndarray]:
        """Removes background from an image with Hybrid BiRefNet/U2Net intelligence.

        Returns:
            (rgba_image, final_alpha_mask)
        """
        if img.mode != "RGB":
            img = img.convert("RGB")

        # 1. Complex packaging routes directly to BiRefNet-general-lite
        if is_complex:
            model_used = "birefnet-general-lite"
            raw_alpha = self._infer_mask(img, model_used)
        else:
            # 2. Standard items run fast U2Net first
            model_used = "u2net"
            raw_alpha = self._infer_mask(img, "u2net")

            # 3. Dynamic escalation check
            if allow_escalation:
                solidity, n_comps = self._evaluate_mask_solidity(raw_alpha)
                if solidity < 0.88 or n_comps > 1:
                    # U2Net produced a hollowed or fragmented mask -> escalate!
                    model_used = "birefnet-general-lite"
                    raw_alpha = self._infer_mask(img, model_used)

        self.last_model_used = model_used

        if enable_hole_protection:
            cv_bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            final_alpha = self.apply_topological_hole_filling(raw_alpha, rgb_bgr=cv_bgr)
        else:
            final_alpha = raw_alpha

        # Apply White-Bleed Defringing to dissolve studio backdrop remnants into #FFFFFF
        rgb_np = np.array(img)
        defringed_rgb_np = self.apply_white_bleed_defringing(rgb_np, final_alpha)
        defringed_pil = Image.fromarray(defringed_rgb_np, mode="RGB")

        r, g, b = defringed_pil.split()
        alpha_channel = Image.fromarray(final_alpha, mode="L")
        rgba = Image.merge("RGBA", (r, g, b, alpha_channel))

        import gc
        gc.collect()

        return rgba, final_alpha
