import pandas as pd
import json

df = pd.read_excel('output/shopify_import/Master_G2_G5_Consolidated.xlsx')
test_codes = ['8716789006523', '12415762', '4016337900254', '8858306001489', '8888296019010', '8901161105066', '8934563138165', '8936116500610', '8850464001571', '8854334005011']

for tc in test_codes:
    matched = df[df['barcode'].astype(str).str.contains(tc)]
    print(f"\n=== Barcode: {tc} (Found: {len(matched)}) ===")
    for _, r in matched.iterrows():
        print(f"Batch: {r.get('batch')} | Photo: {r.get('source_photo')} | Name: {r.get('product_name')}")
        print(f"Box: {r.get('front_box_2d')} | Rot: {r.get('front_rotation')} | Img: {r.get('Website Front Image')}")
