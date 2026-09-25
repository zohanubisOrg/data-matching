import json
import sys

# Ensure UTF-8 stdout on Windows
sys.stdout.reconfigure(encoding='utf-8')

def check():
    try:
        with open('output/g1_delivery/G1_products.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        total = len(data)
        if total == 0:
            print("Empty data")
            return
            
        print(f"Sample item status fields: barcode={data[0].get('barcode')}, status={data[0].get('barcode_status')}, status_flag={data[0].get('status')}")
        
        confirmed = [p for p in data if p.get('barcode_status') == 'confirmed' or p.get('status') == 'CONFIRMED' or p.get('status') == 'MATCHED_POS']
        needs_review = [p for p in data if p not in confirmed]
        pos_matched = [p for p in data if p.get('pos_sku')]
        
        print(f"Total processed in JSON: {total} / 467 ({total/467*100:.1f}%)")
        print(f"Confirmed Barcodes: {len(confirmed)} ({len(confirmed)/total*100:.1f}%)")
        print(f"POS Matched: {len(pos_matched)} ({len(pos_matched)/total*100:.1f}%)")
        print(f"Needs Review: {len(needs_review)} ({len(needs_review)/total*100:.1f}%)")
        print("\nChi tiết các ảnh chưa xác nhận barcode (Needs Review):")
        for p in needs_review[:20]:
            print(f"- {p.get('image_id')}: barcode='{p.get('barcode')}', name='{p.get('display_name') or p.get('vietnamese_name')}', brand='{p.get('brand')}', status='{p.get('status') or p.get('barcode_status')}', note='{p.get('review_note')}'")
    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    check()

