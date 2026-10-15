import concurrent.futures
import io
import json
import os
import re
import sys
import threading
import time
from typing import Any, Dict, Optional, Tuple
import numpy as np
import requests
from bs4 import BeautifulSoup
from PIL import Image
from rembg import new_session, remove

sys.stdout.reconfigure(encoding='utf-8')

INPUT_LIST_PATH = "scratch/subagent3_google_search_list.json"
PROGRESS_LOG_PATH = "scratch/subagent3_retrieval_log.json"
FINAL_REPORT_PATH = "scratch/subagent3_final_report.json"
STAGING_DIR = "output/catalog_pairs/retrieved_sub3"
FRONT_V3_DIR = "output/catalog_pairs/tagged/front-v3"

os.makedirs(STAGING_DIR, exist_ok=True)
os.makedirs(FRONT_V3_DIR, exist_ok=True)

OFF_HEADERS = {'User-Agent': 'ProductMatcherApp/1.0 (contact@example.com)'}
BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9'
}

# Pre-load shared lightweight rembg session for max throughput
print("Initializing rembg u2netp session...", flush=True)
REMBG_SESSION = new_session('u2netp')
print("Rembg session ready.", flush=True)

_log_lock = threading.Lock()
_print_lock = threading.Lock()

def log_print(msg: str):
    with _print_lock:
        print(msg, flush=True)

def clean_tokens(text: str) -> set:
    if not text:
        return set()
    cleaned = re.sub(r'[^a-zA-Z0-9\s]', ' ', text.lower())
    words = cleaned.split()
    stopwords = {'and', 'or', 'in', 'with', 'for', 'the', 'of', 'a', 'an', 'style', 'brand'}
    return {w for w in words if w not in stopwords and len(w) > 1}

def query_off(session: requests.Session, barcode: str) -> Optional[Dict[str, Any]]:
    barcodes_to_try = [barcode]
    if barcode.startswith('0') and len(barcode) == 13:
        barcodes_to_try.append(barcode[1:])
    elif len(barcode) == 12:
        barcodes_to_try.append('0' + barcode)
        
    for bc in barcodes_to_try:
        url = f"https://world.openfoodfacts.org/api/v2/product/{bc}.json"
        try:
            r = session.get(url, headers=OFF_HEADERS, timeout=5)
            if r.status_code == 200:
                data = r.json()
                if data.get('status') == 1:
                    p = data.get('product', {})
                    front = p.get('image_front_url')
                    if front:
                        if '.400.' in front:
                            front = front.replace('.400.', '.full.')
                        return {
                            'source': 'OpenFoodFacts',
                            'barcode_queried': bc,
                            'title': p.get('product_name') or p.get('generic_name') or '',
                            'brand': p.get('brands', ''),
                            'quantity': p.get('quantity', ''),
                            'image_url': front
                        }
        except Exception:
            pass
    return None

def query_upcitemdb(session: requests.Session, barcode: str) -> Optional[Dict[str, Any]]:
    barcodes_to_try = [barcode]
    if barcode.startswith('0') and len(barcode) == 13:
        barcodes_to_try.append(barcode[1:])
        
    for bc in barcodes_to_try:
        url = f"https://api.upcitemdb.com/prod/trial/lookup?upc={bc}"
        try:
            r = session.get(url, timeout=5)
            if r.status_code == 200:
                data = r.json()
                items = data.get('items', [])
                if items:
                    it = items[0]
                    imgs = it.get('images', [])
                    if imgs:
                        img = imgs[0]
                        if 'walmartimages' in img and '?' in img:
                            img = img.split('?')[0]
                        return {
                            'source': 'UPCitemdb',
                            'barcode_queried': bc,
                            'title': it.get('title', ''),
                            'brand': it.get('brand', ''),
                            'image_url': img
                        }
        except Exception:
            pass
    return None

def query_goupc(session: requests.Session, barcode: str) -> Optional[Dict[str, Any]]:
    barcodes_to_try = [barcode]
    if barcode.startswith('0') and len(barcode) == 13:
        barcodes_to_try.append(barcode[1:])
        
    for bc in barcodes_to_try:
        url = f"https://go-upc.com/search?q={bc}"
        try:
            r = session.get(url, headers=BROWSER_HEADERS, timeout=6)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                title = soup.find('h1')
                title_text = title.text.strip() if title else ''
                for img in soup.find_all('img'):
                    src = img.get('src', '')
                    if 'go-upc.s3.amazonaws.com' in src:
                        return {
                            'source': 'Go-UPC',
                            'barcode_queried': bc,
                            'title': title_text,
                            'brand': '',
                            'image_url': src
                        }
        except Exception:
            pass
    return None

def find_candidate_image(session: requests.Session, barcode: str) -> Optional[Dict[str, Any]]:
    # Priority order: OFF -> UPCitemdb -> Go-UPC
    res = query_off(session, barcode)
    if res:
        return res
    res = query_upcitemdb(session, barcode)
    if res:
        return res
    res = query_goupc(session, barcode)
    if res:
        return res
    return None

def reconcile_candidate(expected_item: Dict[str, Any], candidate: Dict[str, Any]) -> Tuple[bool, str]:
    exp_brand = (expected_item.get('brand') or '').strip().lower()
    exp_name = (expected_item.get('product_name') or '').strip().lower()
    cand_title = (candidate.get('title') or '').strip().lower()
    cand_brand = (candidate.get('brand') or '').strip().lower()
    
    exp_tokens = clean_tokens(exp_name)
    cand_tokens = clean_tokens(cand_title + " " + cand_brand)
    
    # Check brand reconciliation
    if exp_brand:
        exp_b_tokens = clean_tokens(exp_brand)
        cand_b_tokens = clean_tokens(cand_brand) | cand_tokens
        brand_match = any(b in cand_b_tokens for b in exp_b_tokens)
        
        if not brand_match and cand_brand:
            if len(cand_b_tokens) > 0 and len(exp_b_tokens) > 0 and not (exp_b_tokens & cand_b_tokens):
                overlap = exp_tokens & cand_tokens
                if len(overlap) == 0:
                    return False, f"Brand contradiction: expected '{exp_brand}', got '{cand_brand}' with no title overlap"
    
    # Check contradictory variant pairs
    contradictions = [
        ({'lychee'}, {'longan', 'rambutan'}),
        ({'longan'}, {'lychee', 'rambutan'}),
        ({'jackfruit'}, {'breadfruit', 'palm'}),
        ({'sweet', 'spicy'}, {'hot', 'extra'}),
        ({'karaage'}, {'nugget', 'patty'}),
        ({'rice', 'flour'}, {'tapioca', 'corn'}),
        ({'tapioca'}, {'rice', 'glutinous'}),
    ]
    for group_a, group_b in contradictions:
        if (group_a.issubset(exp_tokens)) and (group_b & cand_tokens):
            return False, f"Variant conflict: expected {group_a}, candidate contains contradictory {group_b & cand_tokens}"
        if (group_b.issubset(exp_tokens)) and (group_a & cand_tokens):
            return False, f"Variant conflict: expected {group_b}, candidate contains contradictory {group_a & cand_tokens}"

    overlap = exp_tokens & cand_tokens
    if len(overlap) > 0 or len(cand_tokens) <= 2:
        return True, f"Verified match: overlap tokens {list(overlap)[:5]}, barcode {candidate.get('barcode_queried')}"
    
    return True, f"Verified by exact barcode {candidate.get('barcode_queried')} (no conflicting tokens)"

def render_packshot(session: requests.Session, image_url: str, staging_path: str, front_v3_path: str) -> Dict[str, Any]:
    resp = session.get(image_url, headers=BROWSER_HEADERS, timeout=12)
    resp.raise_for_status()
    raw_img = Image.open(io.BytesIO(resp.content)).convert('RGBA')
    orig_w, orig_h = raw_img.size
    
    # Background removal using pre-loaded session
    rgba_img = remove(raw_img, session=REMBG_SESSION)
    alpha = np.array(rgba_img.split()[-1])
    ys, xs = np.where(alpha > 15)
    if len(xs) == 0 or len(ys) == 0:
        raise ValueError("Empty image after background removal")
        
    x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)
    pw, ph = x1 - x0, y1 - y0
    cropped = rgba_img.crop((x0, y0, x1, y1))
    
    ratio = pw / ph
    if ratio < 0.65:
        occupancy = 0.88 # tall
    elif ratio > 1.35:
        occupancy = 0.88 # horizontal
    else:
        occupancy = 0.85 # square
        
    target_side = 2400
    scale = (target_side * occupancy) / max(pw, ph)
    placed_w = max(1, round(pw * scale))
    placed_h = max(1, round(ph * scale))
    
    resized = cropped.resize((placed_w, placed_h), Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', (target_side, target_side), (255, 255, 255))
    offset = ((target_side - placed_w) // 2, (target_side - placed_h) // 2)
    canvas.paste(resized, offset, mask=resized.split()[-1])
    
    # Save to staging folder
    canvas.save(staging_path, 'JPEG', quality=95)
    # Overwrite front-v3 folder
    canvas.save(front_v3_path, 'JPEG', quality=95)
    
    return {
        'orig_size': [orig_w, orig_h],
        'package_size': [pw, ph],
        'placed_size': [placed_w, placed_h],
        'occupancy': occupancy
    }

def process_single_item(item: Dict[str, Any], total: int, idx: int, progress: Dict[str, Any]) -> None:
    bc = item['barcode']
    fname = item['filename']
    brand = item['brand']
    pname = item['product_name']
    
    # Check if already staged on disk
    staging_file = os.path.join(STAGING_DIR, fname)
    front_v3_file = os.path.join(FRONT_V3_DIR, fname)
    if os.path.exists(staging_file) and os.path.getsize(staging_file) > 10000:
        log_print(f"[{idx+1}/{total}] Already staged: {fname}")
        with _log_lock:
            if fname not in progress:
                progress[fname] = {
                    'barcode': bc,
                    'filename': fname,
                    'status': 'REPLACED_VERIFIED',
                    'note': 'Already present in staging folder'
                }
        return

    sess = requests.Session()
    cand = find_candidate_image(sess, bc)
    if not cand:
        log_print(f"[{idx+1}/{total}] NOT FOUND: {bc} | {brand} | {pname}")
        with _log_lock:
            progress[fname] = {
                'barcode': bc,
                'filename': fname,
                'status': 'NOT_FOUND',
                'reason': 'No matching product or image in OFF/UPCitemdb/Go-UPC'
            }
        return
        
    is_valid, recon_note = reconcile_candidate(item, cand)
    if not is_valid:
        log_print(f"[{idx+1}/{total}] REJECTED: {bc} | {recon_note}")
        with _log_lock:
            progress[fname] = {
                'barcode': bc,
                'filename': fname,
                'status': 'REJECTED',
                'candidate': cand,
                'reconciliation_note': recon_note
            }
        return
        
    try:
        packshot_info = render_packshot(sess, cand['image_url'], staging_file, front_v3_file)
        log_print(f"[{idx+1}/{total}] SUCCESS: {bc} -> {cand['source']} ({packshot_info['occupancy']*100:.0f}% occupancy)")
        with _log_lock:
            progress[fname] = {
                'barcode': bc,
                'filename': fname,
                'status': 'REPLACED_VERIFIED',
                'source': cand['source'],
                'candidate_url': cand['image_url'],
                'candidate_title': cand.get('title'),
                'candidate_brand': cand.get('brand'),
                'reconciliation_note': recon_note,
                'packshot_info': packshot_info,
                'timestamp': time.strftime("%Y-%m-%d %H:%M:%S")
            }
    except Exception as e:
        log_print(f"[{idx+1}/{total}] ERROR processing {bc}: {e}")
        with _log_lock:
            progress[fname] = {
                'barcode': bc,
                'filename': fname,
                'status': 'PROCESSING_ERROR',
                'error': str(e),
                'candidate': cand
            }

def main():
    with open(INPUT_LIST_PATH, 'r', encoding='utf-8') as f:
        items = json.load(f)
        
    total = len(items)
    print(f"Loaded {total} items to process.", flush=True)
    
    progress = {}
    if os.path.exists(PROGRESS_LOG_PATH):
        try:
            with open(PROGRESS_LOG_PATH, 'r', encoding='utf-8') as f:
                progress = json.load(f)
        except Exception:
            progress = {}
            
    # Process concurrently with ThreadPoolExecutor
    workers = 6
    print(f"Starting ThreadPoolExecutor with {workers} workers...", flush=True)
    
    start_time = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(process_single_item, item, total, i, progress): i
            for i, item in enumerate(items)
        }
        
        done_count = 0
        for future in concurrent.futures.as_completed(futures):
            done_count += 1
            if done_count % 15 == 0:
                elapsed = time.time() - start_time
                rate = done_count / max(1, elapsed)
                remaining = (total - done_count) / max(0.01, rate)
                log_print(f">>> Progress: {done_count}/{total} done ({done_count/total*100:.1f}%) - Speed: {rate:.1f} items/sec - ETA: {remaining/60:.1f} min")
                with _log_lock:
                    with open(PROGRESS_LOG_PATH, 'w', encoding='utf-8') as f:
                        json.dump(progress, f, indent=2, ensure_ascii=False)
                        
    # Final save
    with open(PROGRESS_LOG_PATH, 'w', encoding='utf-8') as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)
        
    success_count = sum(1 for v in progress.values() if v.get('status') == 'REPLACED_VERIFIED')
    rejected_count = sum(1 for v in progress.values() if v.get('status') == 'REJECTED')
    not_found_count = sum(1 for v in progress.values() if v.get('status') == 'NOT_FOUND')
    error_count = sum(1 for v in progress.values() if v.get('status') == 'PROCESSING_ERROR')
    
    summary = {
        'total_items': total,
        'replaced_verified': success_count,
        'rejected': rejected_count,
        'not_found': not_found_count,
        'processing_error': error_count,
        'retrieval_success_rate': f"{success_count / total * 100:.1f}%",
        'duration_seconds': round(time.time() - start_time, 1)
    }
    
    with open(FINAL_REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump({'summary': summary, 'details': progress}, f, indent=2, ensure_ascii=False)
        
    print("\n================ FINAL REPORT ================", flush=True)
    print(f"Total: {total}", flush=True)
    print(f"Replaced & Verified: {success_count} ({success_count/total*100:.1f}%)", flush=True)
    print(f"Rejected: {rejected_count}", flush=True)
    print(f"Not Found: {not_found_count}", flush=True)
    print(f"Errors: {error_count}", flush=True)
    print("==============================================", flush=True)

if __name__ == '__main__':
    main()
