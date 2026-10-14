import cv2
import numpy as np
from PIL import Image as PILImage, ImageOps, ImageEnhance
from pathlib import Path
import json

def get_perfect_front_crop(img_path: Path, debug: bool = False) -> tuple[PILImage.Image | None, str]:
    """Precisely segments the 2 packaging items (Front & Back) in a photo,

    determines which one is the FRONT (brand/logo side without barcode/nutrition table),
    and crops the ENTIRE front item cleanly without cutting through it.
    """
    with PILImage.open(img_path) as pil_im:
        pil_im = ImageOps.exif_transpose(pil_im)
        orig_w, orig_h = pil_im.size

        # Downsample for robust CV analysis
        proc_w = 1200
        proc_h = int(1200 * orig_h / orig_w)
        cv_im = cv2.cvtColor(np.array(pil_im.resize((proc_w, proc_h))), cv2.COLOR_RGB2BGR)

    gray = cv2.cvtColor(cv_im, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(cv_im, cv2.COLOR_BGR2HSV)

    # 1. Barcode Localization using Gradient & Morphological operations
    gradX = cv2.Sobel(gray, ddepth=cv2.CV_32F, dx=1, dy=0, ksize=-1)
    gradY = cv2.Sobel(gray, ddepth=cv2.CV_32F, dx=0, dy=1, ksize=-1)
    gradient = cv2.subtract(gradX, gradY)
    gradient = cv2.convertScaleAbs(gradient)
    blurred = cv2.blur(gradient, (9, 9))
    _, thresh_bc = cv2.threshold(blurred, 220, 255, cv2.THRESH_BINARY)
    kernel_bc = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 7))
    closed_bc = cv2.morphologyEx(thresh_bc, cv2.MORPH_CLOSE, kernel_bc)
    closed_bc = cv2.erode(closed_bc, None, iterations=4)
    closed_bc = cv2.dilate(closed_bc, None, iterations=4)

    bc_cnts, _ = cv2.findContours(closed_bc.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    bc_center = None
    if bc_cnts:
        l_bc = max(bc_cnts, key=cv2.contourArea)
        if cv2.contourArea(l_bc) > 300:
            M = cv2.moments(l_bc)
            if M["m00"] > 0:
                bc_center = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))

    # 2. Foreground Object Segmentation (Otsu + Canny edge integration)
    blur_bg = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur_bg, 30, 100)
    kernel_e = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    closed_edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel_e)
    
    # Also find background via adaptive threshold
    thresh = cv2.adaptiveThreshold(blur_bg, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 5)
    combined = cv2.bitwise_or(closed_edges, thresh)
    kernel_c = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel_c)
    combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)))

    contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # 3. Analyze left-vs-right split
    # In studio photos, items are placed LEFT and RIGHT
    # Check left half vs right half text/edge density and barcode
    left_gray = gray[:, :proc_w // 2]
    right_gray = gray[:, proc_w // 2:]
    left_hsv = hsv[:, :proc_w // 2]
    right_hsv = hsv[:, proc_w // 2:]

    left_edges = np.mean(cv2.Canny(left_gray, 50, 150))
    right_edges = np.mean(cv2.Canny(right_gray, 50, 150))
    left_sat = np.mean(left_hsv[:, :, 1])
    right_sat = np.mean(right_hsv[:, :, 1])

    left_has_bc = bc_center and bc_center[0] < proc_w // 2
    right_has_bc = bc_center and bc_center[0] >= proc_w // 2

    # Score for being the BACK side
    left_back_score = left_edges - left_sat * 0.3 + (150.0 if left_has_bc else 0)
    right_back_score = right_edges - right_sat * 0.3 + (150.0 if right_has_bc else 0)

    if left_back_score > right_back_score:
        # Front is on the RIGHT side
        selected_side = "right"
        crop_x0, crop_x1 = int(orig_w * 0.48), orig_w
    else:
        # Front is on the LEFT side
        selected_side = "left"
        crop_x0, crop_x1 = 0, int(orig_w * 0.52)

    # 4. Find tight vertical and horizontal boundaries of the FRONT object
    # Crop the selected half on full image
    half_crop = pil_im.crop((crop_x0, 0, crop_x1, orig_h))
    hw, hh = half_crop.size

    # Downscale half crop to 800px width for fast contour bounding
    proc_hw = 800
    proc_hh = int(800 * hh / hw)
    cv_half = cv2.cvtColor(np.array(half_crop.resize((proc_hw, proc_hh))), cv2.COLOR_RGB2BGR)
    h_gray = cv2.cvtColor(cv_half, cv2.COLOR_BGR2GRAY)
    h_blur = cv2.GaussianBlur(h_gray, (7, 7), 0)
    h_edges = cv2.Canny(h_blur, 25, 90)
    h_closed = cv2.morphologyEx(h_edges, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15)))

    cnts_h, _ = cv2.findContours(h_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    fx0, fy0, fx1, fy1 = 0, 0, hw, hh
    if cnts_h:
        # Filter contours by min area
        valid = [c for c in cnts_h if cv2.contourArea(c) > (proc_hw * proc_hh * 0.04)]
        if valid:
            main_c = max(valid, key=cv2.contourArea)
            bx, by, bw, bh = cv2.boundingRect(main_c)
            
            # If multiple significant contours exist vertically, merge them
            for c in valid:
                if cv2.contourArea(c) > (proc_hw * proc_hh * 0.1):
                    cx, cy, cw, ch = cv2.boundingRect(c)
                    bx = min(bx, cx)
                    by = min(by, cy)
                    bw = max(bx + bw, cx + cw) - bx
                    bh = max(by + bh, cy + ch) - by

            sx = hw / float(proc_hw)
            sy = hh / float(proc_hh)
            
            pad_x = int(bw * sx * 0.03)
            pad_y = int(bh * sy * 0.03)
            
            fx0 = max(0, int(bx * sx) - pad_x)
            fy0 = max(0, int(by * sy) - pad_y)
            fx1 = min(hw, int((bx + bw) * sx) + pad_x)
            fy1 = min(hh, int((by + bh) * sy) + pad_y)

    # Perform tight crop on front object
    if (fx1 - fx0) > hw * 0.2 and (fy1 - fy0) > hh * 0.2:
        front_crop = half_crop.crop((fx0, fy0, fx1, fy1))
    else:
        front_crop = half_crop

    # 5. Check if the object was photographed lying on its side (horizontal)
    # If width is much greater than height (e.g. w > 1.4*h) for a package that has vertical text
    fw, fh = front_crop.size
    
    # Scale to HD 800px on max dimension
    scale = min(800.0 / fw, 800.0 / fh)
    new_w, new_h = max(1, int(fw * scale)), max(1, int(fh * scale))
    front_hd = front_crop.resize((new_w, new_h), PILImage.Resampling.LANCZOS)
    
    enhancer = ImageEnhance.Sharpness(front_hd)
    front_hd = enhancer.enhance(1.15)
    
    return front_hd, f"side={selected_side}, box=({fx0},{fy0},{fx1},{fy1}), size=({new_w},{new_h})"

if __name__ == "__main__":
    test_files = ['IMG_0080.jpeg', 'IMG_0096.jpeg', 'IMG_0117.jpeg', 'IMG_0122.jpeg', 'IMG_0123.jpeg', 'IMG_0124.jpeg']
    for f in test_files:
        p = Path("G1_original") / f
        if p.exists():
            im, info = get_perfect_front_crop(p)
            if im:
                out_p = Path("output/g1_delivery/test_perfect") / f"{f}.jpg"
                out_p.parent.mkdir(parents=True, exist_ok=True)
                im.convert("RGB").save(out_p, "JPEG", quality=95)
                print(f"{f:<15} -> {info}")
