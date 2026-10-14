import json, re, sys
sys.stdout.reconfigure(encoding='utf-8')

with open('output/g1_delivery/g1_deep_scan_65_cache.json', 'r', encoding='utf-8') as f:
    cache = json.load(f)

def parse_net(text):
    if not text: return None, None
    m = re.search(r'(\d+(?:\.\d+)?)\s*(kg|g|ml|cl|l|liter|litres|oz|fl\s*oz|pcs|pack|bags|tabs)\b', text, re.IGNORECASE)
    if m:
        qty = float(m.group(1))
        unit = m.group(2).lower()
        if unit in ['liter', 'litres', 'l']: unit = 'L'
        elif unit == 'fl oz': unit = 'fl oz'
        elif unit == 'kg': unit = 'kg'
        elif unit == 'g': unit = 'g'
        elif unit == 'ml': unit = 'ml'
        return qty, unit
    return None, None

resolved_qty = 0
unresolved_qty = []
for k, v in cache.items():
    qty = v.get('net_quantity')
    unit = v.get('net_unit')
    if not qty or str(qty).strip() in ['', 'None']:
        for f in ['net_weight', 'full_name_en', 'product_name', 'literal_label_name', 'pos_product_name', 'fuldt_navn_da']:
            q, u = parse_net(str(v.get(f, '')))
            if q:
                qty, unit = q, u
                break
    if qty:
        resolved_qty += 1
    else:
        unresolved_qty.append((k, v.get('brand'), v.get('product_name') or v.get('full_name_en')))

print(f"Total resolved net qty: {resolved_qty}/467 ({resolved_qty/467*100:.1f}%)")
if unresolved_qty:
    print(f"Unresolved sample ({len(unresolved_qty)} items):")
    for item in unresolved_qty[:10]:
        print("  ", item)
