import sys
from pathlib import Path
import json
import cv2
import numpy as np
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from product_mapper.ingestion.image_loader import open_image_safely

def detect_front_box_cv(img_path: Path) -> tuple[list[int], int, str]:
    """
    Rock-solid, non-destructive computer vision detector for retail grocery packaging.
    Guarantees that the physical product package is NEVER severed in half.
    
    Returns:
      - [ymin, xmin, ymax, xmax] normalized to 0-1000 scale.
      - rotation (0 degrees).
      - debug label describing detection mode.
    """
    try:
        pil_im = open_image_safely(img_path)
        orig_w, orig_h = pil_im.size
        
        proc_w = 1200
        proc_h = int(1200 * orig_h / orig_w)
        cv_im = cv2.cvtColor(np.array(pil_im.resize((proc_w, proc_h))), cv2.COLOR_RGB2BGR)
    except Exception as e:
        return [0, 0, 1000, 1000], 0, f"cv_error: {e}"

    gray = cv2.cvtColor(cv_im, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(cv_im, cv2.COLOR_BGR2HSV)

    # 1. Barcode Localization using gradient
    gradX = cv2.Sobel(gray, ddepth=cv2.CV_32F, dx=1, dy=0, ksize=-1)
    gradY = cv2.Sobel(gray, ddepth=cv2.CV_32F, dx=0, dy=1, ksize=-1)
    gradient = cv2.subtract(gradX, gradY)
    gradient = cv2.convertScaleAbs(gradient)
    blurred_bc = cv2.blur(gradient, (9, 9))
    _, thresh_bc = cv2.threshold(blurred_bc, 225, 255, cv2.THRESH_BINARY)
    kernel_bc = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 7))
    closed_bc = cv2.morphologyEx(thresh_bc, cv2.MORPH_CLOSE, kernel_bc)
    closed_bc = cv2.erode(closed_bc, None, iterations=3)
    closed_bc = cv2.dilate(closed_bc, None, iterations=3)

    bc_contours, _ = cv2.findContours(closed_bc.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    bc_centroid = None
    if bc_contours:
        largest_bc = max(bc_contours, key=cv2.contourArea)
        if cv2.contourArea(largest_bc) > 400:
            M = cv2.moments(largest_bc)
            if M["m00"] > 0:
                bc_centroid = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))

    # 2. Foreground Object Extraction (Canny Edges + Morphological Closing)
    blur_fg = cv2.GaussianBlur(gray, (7, 7), 0)
    edges = cv2.Canny(blur_fg, 25, 90)
    kernel_fg = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
    dilated = cv2.dilate(edges, kernel_fg, iterations=2)
    closed_fg = cv2.morphologyEx(dilated, cv2.MORPH_CLOSE, kernel_fg)

    contours, _ = cv2.findContours(closed_fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    total_area = proc_w * proc_h
    min_area = total_area * 0.05
    valid_boxes = []

    for c in contours:
        area = cv2.contourArea(c)
        if area > min_area:
            x, y, w, h = cv2.boundingRect(c)
            # Ensure height is substantial (packaging is usually vertical or prominent)
            valid_boxes.append((x, y, x + w, y + h, area))

    # Case A: Dual objects side-by-side (e.g. Front & Back side-by-side)
    # Check if there are 2 prominent contours on left and right
    if len(valid_boxes) >= 2:
        valid_boxes.sort(key=lambda b: b[4], reverse=True)
        b1, b2 = valid_boxes[0], valid_boxes[1]
        
        # Check if they are distinct horizontal panels (left vs right)
        cx1 = (b1[0] + b1[2]) / 2.0
        cx2 = (b2[0] + b2[2]) / 2.0
        
        if abs(cx1 - cx2) > (proc_w * 0.25):
            left_b = b1 if cx1 < cx2 else b2
            right_b = b2 if cx1 < cx2 else b1
            
            def score_side(b):
                bx0, by0, bx1, by1, _ = b
                crop_gray = gray[by0:by1, bx0:bx1]
                crop_hsv = hsv[by0:by1, bx0:bx1]
                if crop_gray.size == 0:
                    return 0
                edge_score = np.mean(cv2.Canny(crop_gray, 50, 150))
                sat_score = np.mean(crop_hsv[:, :, 1])
                has_bc = 50.0 if (bc_centroid and bx0 <= bc_centroid[0] <= bx1 and by0 <= bc_centroid[1] <= by1) else 0.0
                return edge_score - (sat_score * 0.5) + has_bc

            s_left = score_side(left_b)
            s_right = score_side(right_b)
            
            # Lower score = FRONT (more colorful, fewer barcodes/dense text)
            front_b = left_b if s_left < s_right else right_b
            fx0, fy0, fx1, fy1, _ = front_b
            
            # Add safe margin around front packaging
            bw = fx1 - fx0
            bh = fy1 - fy0
            pad_x = int(bw * 0.04)
            pad_y = int(bh * 0.04)
            
            fx0 = max(0, fx0 - pad_x)
            fy0 = max(0, fy0 - pad_y)
            fx1 = min(proc_w, fx1 + pad_x)
            fy1 = min(proc_h, fy1 + pad_y)
            
            box_1000 = [
                int(fy0 * 1000 / proc_h),
                int(fx0 * 1000 / proc_w),
                int(fy1 * 1000 / proc_h),
                int(fx1 * 1000 / proc_w)
            ]
            return box_1000, 0, f"cv_dual_panel ({'left' if front_b == left_b else 'right'})"

    # Case B: Single Main Product (enclosing the full product package from top to bottom)
    if valid_boxes:
        all_pts = []
        for c in contours:
            if cv2.contourArea(c) > (total_area * 0.03):
                all_pts.append(c)
        if all_pts:
            pts_concat = np.concatenate(all_pts)
            x, y, w, h = cv2.boundingRect(pts_concat)
            
            # Add safe 3% margin
            pad_x = int(w * 0.03)
            pad_y = int(h * 0.03)
            x0 = max(0, x - pad_x)
            y0 = max(0, y - pad_y)
            x1 = min(proc_w, x + w + pad_x)
            y1 = min(proc_h, y + h + pad_y)
            
            # Check coverage - if bounding box covers at least 65% of height, use it
            box_h = (y1 - y0) / proc_h
            if box_h > 0.45:
                box_1000 = [
                    int(y0 * 1000 / proc_h),
                    int(x0 * 1000 / proc_w),
                    int(y1 * 1000 / proc_h),
                    int(x1 * 1000 / proc_w)
                ]
                return box_1000, 0, "cv_full_product_contour"

    # Case C: Safe Full-Frame with minimal border trim (NO CHOPPING)
    return [0, 0, 1000, 1000], 0, "cv_full_frame_safe"


_global_yolo_detector = None

def detect_front_box_hybrid(img_path: Path) -> tuple[list[int], int, str]:
    """
    Hàm nhận diện Hybrid tối ưu:
    1. Ưu tiên sử dụng YOLO Packaging Detector nếu model đã huấn luyện và độ tin cậy > 0.65
    2. Tự động fallback về OpenCV Heuristic (Sobel + Canny + HSV) nếu YOLO không khả dụng.
    """
    global _global_yolo_detector
    try:
        if _global_yolo_detector is None:
            from product_mapper.vision.yolo_detector import YOLOPackagingDetector
            _global_yolo_detector = YOLOPackagingDetector()

        if _global_yolo_detector.is_custom_trained:
            res = _global_yolo_detector.detect(img_path)
            if res.front_box_2d and res.confidence_front >= 0.65:
                return res.front_box_2d, res.front_rotation, f"yolo_hybrid (conf={res.confidence_front:.2f})"
    except Exception as e:
        pass

    return detect_front_box_cv(img_path)
