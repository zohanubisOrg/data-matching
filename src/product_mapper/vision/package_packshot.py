"""Conservative rendering from an independently reviewed package boundary."""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image


class UnverifiedPackageError(ValueError):
    """Input needs source/identity/boundary review before rendering."""


class InsufficientNativeResolutionError(UnverifiedPackageError):
    """The product ROI would need enlargement to fill the requested canvas."""


def mask_from_polygon(size: tuple[int, int], points: list) -> np.ndarray:
    w, h = size
    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 2 or len(pts) < 3 or not np.isfinite(pts).all():
        raise UnverifiedPackageError('Invalid package polygon')
    if (pts[:, 0] < 0).any() or (pts[:, 0] >= w).any() or (pts[:, 1] < 0).any() or (pts[:, 1] >= h).any():
        raise UnverifiedPackageError('Polygon outside oriented source dimensions')
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])
    for i in range(len(pts)):
        a, b = pts[i], pts[(i+1) % len(pts)]
        for j in range(i+2, len(pts)):
            if i == 0 and j == len(pts)-1:
                continue
            c, d = pts[j], pts[(j+1) % len(pts)]
            if cross(a,b,c)*cross(a,b,d) < 0 and cross(c,d,a)*cross(c,d,b) < 0:
                raise UnverifiedPackageError('Self-intersecting package polygon')
    result = np.zeros((h, w), np.uint8)
    cv2.fillPoly(result, [np.rint(pts).astype(np.int32)], 255)
    return result


def assess_candidate_mask(candidate, reference) -> dict:
    """Diagnostic only; comparison never grants final QA PASS."""
    candidate, reference = np.asarray(candidate), np.asarray(reference)
    if candidate.shape != reference.shape or reference.ndim != 2:
        raise UnverifiedPackageError('Candidate/reference dimensions differ')
    c, r = candidate > 127, reference > 127
    if not r.any():
        raise UnverifiedPackageError('Empty reference mask')
    coverage = float(np.count_nonzero(c & r) / np.count_nonzero(r))
    spill = float(np.count_nonzero(c & ~r) / max(1, np.count_nonzero(c)))
    return {'coverage': coverage, 'spill': spill, 'accepted': coverage >= .985 and spill <= .02,
            'qa_status': 'NEEDS_MANUAL_REVIEW'}


def render_verified_packshot(image: Image.Image, mask, target_side=2400, shape='auto', *, fit_to_native=False) -> tuple[Image.Image, dict]:
    if mask is None:
        raise UnverifiedPackageError('Independent whole-package mask required; logo contour is insufficient')
    arr = np.asarray(image.convert('RGB'))
    m = np.asarray(mask)
    if m.shape != arr.shape[:2] or not np.isin(m, [0, 255]).all():
        raise UnverifiedPackageError('Mask must be source-aligned and binary 0/255')
    m = m.astype(np.uint8)
    count, _ = cv2.connectedComponents(m, connectivity=8)
    if count != 2:
        raise UnverifiedPackageError('Mask must contain exactly one connected package')
    _, hierarchy = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is not None and (hierarchy[0, :, 3] >= 0).any():
        raise UnverifiedPackageError('Mask holes need an explicit reviewed matting/handle workflow')
    if m[0].any() or m[-1].any() or m[:, 0].any() or m[:, -1].any():
        raise UnverifiedPackageError('Package touches source border; completeness unverified')
    ys, xs = np.where(m > 0)
    x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()+1), int(ys.max()+1)
    pw, ph = x1-x0, y1-y0
    if max(pw, ph) < 600 or min(pw, ph) < 30:
        raise UnverifiedPackageError('Native package resolution insufficient; never restore from a thumbnail')
    if target_side < 64:
        raise ValueError('Canvas side must be at least 64')
    if shape == 'auto':
        ratio = pw/ph
        shape = 'tall' if ratio < .65 else 'horizontal' if ratio > 1.35 else 'square'
    occupancy = {'tall': .88, 'horizontal': .89, 'square': .84, 'irregular': .83}.get(shape)
    if occupancy is None:
        raise ValueError('Unknown product shape')
    requested_occupancy = occupancy
    requested_scale = target_side*occupancy/max(pw, ph)
    scale_limited_to_native = requested_scale > 1 and fit_to_native
    if requested_scale > 1:
        if not fit_to_native:
            raise InsufficientNativeResolutionError(
                f'Native package resolution insufficient; 2400-style rendering would require upscaling ({requested_scale:.3f}x)'
            )
        scale = 1.0
        occupancy = max(pw, ph)/target_side
        if occupancy < .75:
            raise InsufficientNativeResolutionError(
                f'Native package would occupy only {occupancy:.3f} of the canvas at native scale; another source is required'
            )
    else:
        scale = requested_scale
    placed = (max(1, round(pw*scale)), max(1, round(ph*scale)))
    # Only feather 1.5 source pixels inward; all interior labels stay opaque.
    alpha = np.minimum(cv2.distanceTransform(m, cv2.DIST_L2, 5)/1.5, 1)[y0:y1, x0:x1, None]
    rgb = arr[y0:y1, x0:x1]
    crop = Image.fromarray(np.rint(rgb*alpha + 255*(1-alpha)).astype(np.uint8))
    crop = crop.resize(placed, Image.Resampling.LANCZOS)
    output = Image.new('RGB', (target_side, target_side), 'white')
    offset = ((target_side-placed[0])//2, (target_side-placed[1])//2)
    output.paste(crop, offset)
    return output, {'source_bbox': [x0,y0,x1,y1], 'native_package_size': [pw,ph],
                    'placed_size': list(placed), 'offset': list(offset), 'shape': shape,
                    'occupancy': occupancy, 'requested_occupancy': requested_occupancy,
                    'scale_limited_to_native': scale_limited_to_native, 'upscale_factor': scale,
                    'source_resolution_warning': False,
                    'qa_status': 'REPROCESSED_NEEDS_REVIEW'}
