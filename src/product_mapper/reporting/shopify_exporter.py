from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd


SHOPIFY_28_COLUMNS = [
    "Handle",
    "Title",
    "Body (HTML)",
    "Vendor",
    "Product Category",
    "Type",
    "Tags",
    "Published",
    "Option1 Name",
    "Option1 Value",
    "Variant SKU",
    "Variant Grams",
    "Variant Inventory Tracker",
    "Variant Inventory Qty",
    "Variant Inventory Policy",
    "Variant Fulfillment Service",
    "Variant Price",
    "Variant Compare At Price",
    "Variant Requires Shipping",
    "Variant Taxable",
    "Variant Barcode",
    "Image Src",
    "Image Position",
    "Image Alt Text",
    "Gift Card",
    "SEO Title",
    "SEO Description",
    "Status",
]

CATEGORY_TYPE_MAPPING = {
    "sauce": ("Food, Beverages & Tobacco > Food Items > Saucer & Sojasauce", "Saucer & Sojasauce"),
    "soja": ("Food, Beverages & Tobacco > Food Items > Saucer & Sojasauce", "Saucer & Sojasauce"),
    "soy": ("Food, Beverages & Tobacco > Food Items > Saucer & Sojasauce", "Saucer & Sojasauce"),
    "curry": ("Food, Beverages & Tobacco > Food Items > Saucer & Sojasauce", "Saucer & Sojasauce"),
    "karry": ("Food, Beverages & Tobacco > Food Items > Saucer & Sojasauce", "Saucer & Sojasauce"),
    "pasta": ("Food, Beverages & Tobacco > Food Items > Saucer & Sojasauce", "Saucer & Sojasauce"),
    "paste": ("Food, Beverages & Tobacco > Food Items > Saucer & Sojasauce", "Saucer & Sojasauce"),
    "krydderi": ("Food, Beverages & Tobacco > Food Items > Krydderier & Karry", "Krydderier & Karry"),
    "spice": ("Food, Beverages & Tobacco > Food Items > Krydderier & Karry", "Krydderier & Karry"),
    "sesam": ("Food, Beverages & Tobacco > Food Items > Krydderier & Karry", "Krydderier & Karry"),
    "eddike": ("Food, Beverages & Tobacco > Food Items > Krydderier & Karry", "Krydderier & Karry"),
    "snack": ("Food, Beverages & Tobacco > Food Items > Snack", "Snack"),
    "chip": ("Food, Beverages & Tobacco > Food Items > Snack", "Snack"),
    "slik": ("Food, Beverages & Tobacco > Food Items > Snack", "Snack"),
    "nori": ("Food, Beverages & Tobacco > Food Items > Snack", "Snack"),
    "ris": ("Food, Beverages & Tobacco > Food Items > Ris, Mel & Tørvarer", "Ris, Mel & Tørvarer"),
    "rice": ("Food, Beverages & Tobacco > Food Items > Ris, Mel & Tørvarer", "Ris, Mel & Tørvarer"),
    "bønner": ("Food, Beverages & Tobacco > Food Items > Ris, Mel & Tørvarer", "Ris, Mel & Tørvarer"),
    "beans": ("Food, Beverages & Tobacco > Food Items > Ris, Mel & Tørvarer", "Ris, Mel & Tørvarer"),
    "konserves": ("Food, Beverages & Tobacco > Food Items > Konserves & Kokosmælk", "Konserves & Kokosmælk"),
    "canned": ("Food, Beverages & Tobacco > Food Items > Konserves & Kokosmælk", "Konserves & Kokosmælk"),
    "kokos": ("Food, Beverages & Tobacco > Food Items > Konserves & Kokosmælk", "Konserves & Kokosmælk"),
    "drikke": ("Food, Beverages & Tobacco > Food Items > Drikkevarer & Vin", "Drikkevarer & Vin"),
    "drink": ("Food, Beverages & Tobacco > Food Items > Drikkevarer & Vin", "Drikkevarer & Vin"),
    "juice": ("Food, Beverages & Tobacco > Food Items > Drikkevarer & Vin", "Drikkevarer & Vin"),
    "sake": ("Food, Beverages & Tobacco > Food Items > Drikkevarer & Vin", "Drikkevarer & Vin"),
    "vin": ("Food, Beverages & Tobacco > Food Items > Drikkevarer & Vin", "Drikkevarer & Vin"),
}


def slugify(text: str) -> str:
    """Creates a URL-safe kebab-case slug handling Danish characters."""
    text = str(text or "").strip()
    text = text.replace("æ", "ae").replace("Æ", "ae")
    text = text.replace("ø", "oe").replace("Ø", "oe")
    text = text.replace("å", "aa").replace("Å", "aa")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[-\s]+", "-", text).strip("-")
    return text


def clean_barcode(val: Any) -> str:
    """Formats barcode cleanly as a pure numeric digit string."""
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip()
    if s.endswith(".0"):
        s = s[:-2]
    # Remove scientific notation if passed as string
    if "e+" in s.lower() or "e-" in s.lower():
        try:
            s = f"{int(float(s))}"
        except Exception:
            pass
    # Keep only alphanumeric digits
    s = re.sub(r"[^\w]", "", s)
    return s


def infer_product_category_and_type(category_text: str, title: str) -> tuple[str, str]:
    combined = f"{category_text} {title}".lower()
    for keyword, (cat, ptype) in CATEGORY_TYPE_MAPPING.items():
        if keyword in combined:
            return cat, ptype
    return ("Food, Beverages & Tobacco > Food Items > Andre asiatiske varer", "Andre asiatiske varer")


def safe_str(v: Any) -> str:
    if v is None or pd.isna(v):
        return ""
    s = str(v).strip()
    return "" if s.lower() in {"none", "nan", "null"} else s


def generate_danish_html_body(item: dict[str, Any]) -> str:
    brand = safe_str(item.get("brand") or item.get("Brand"))
    net_weight = safe_str(item.get("net_weight") or item.get("Net quantity"))
    net_unit = safe_str(item.get("net_unit") or item.get("Net unit")) or "g"
    if net_weight:
        weight_str = f"{net_weight} {net_unit}".strip()
    else:
        weight_str = ""
    origin = safe_str(item.get("country_of_origin") or item.get("Country of origin"))
    
    parts = []
    
    # 1. Header Meta Line
    meta_info = []
    if brand:
        meta_info.append(f"Mærke: {brand}")
    if weight_str:
        meta_info.append(f"Nettoindhold: {weight_str}")
    if origin:
        meta_info.append(f"Oprindelsesland: {origin}")
    if meta_info:
        parts.append(f"<p>{' · '.join(meta_info)}</p>")
    
    # 2. Ingredients
    ing_da = safe_str(item.get("ingredienser_da") or item.get("Ingredienser (DA)"))
    ing_en = safe_str(item.get("ingredients_en") or item.get("Ingredients (EN)"))
    ing = ing_da or ing_en
    if ing:
        parts.append(f"<h3>Ingredienser</h3><p>{ing}</p>")
        
    # 3. Allergens
    all_da = safe_str(item.get("allergener_da") or item.get("Allergener (DA)"))
    all_en = safe_str(item.get("allergens_en") or item.get("Allergens (EN)"))
    allergens = all_da or all_en
    if allergens:
        parts.append(f"<h3>Allergener</h3><p>{allergens}</p>")
        
    # 4. Nutrition Facts Table
    has_nutrition = any(
        item.get(k) is not None and not pd.isna(item.get(k)) and str(item.get(k)).strip() != ""
        for k in ["energy_kj", "energy_kcal", "fat_g", "carbohydrate_g", "protein_g", "salt_g"]
    )
    if has_nutrition:
        basis = safe_str(item.get("nutrition_basis") or item.get("Nutrition basis / preparation state")) or "pr. 100 g"
        if not basis.startswith("pr.") and not basis.startswith("per"):
            basis = f"pr. {basis}"
        rows = []
        
        ekj = item.get("energy_kj")
        ekcal = item.get("energy_kcal")
        if (ekj is not None and not pd.isna(ekj)) or (ekcal is not None and not pd.isna(ekcal)):
            e_str = []
            if ekj is not None and not pd.isna(ekj) and str(ekj).strip():
                e_str.append(f"{ekj} kJ")
            if ekcal is not None and not pd.isna(ekcal) and str(ekcal).strip():
                e_str.append(f"{ekcal} kcal")
            if e_str:
                rows.append(f"<tr><td>Energi</td><td>{' / '.join(e_str)}</td></tr>")
            
        fat = item.get("fat_g")
        if fat is not None and not pd.isna(fat) and str(fat).strip():
            rows.append(f"<tr><td>Fedt</td><td>{fat} g</td></tr>")
            
        sat = item.get("saturates_g")
        if sat is not None and not pd.isna(sat) and str(sat).strip():
            rows.append(f"<tr><td>&nbsp;&nbsp;heraf mættede fedtsyrer</td><td>{sat} g</td></tr>")
            
        carb = item.get("carbohydrate_g")
        if carb is not None and not pd.isna(carb) and str(carb).strip():
            rows.append(f"<tr><td>Kulhydrat</td><td>{carb} g</td></tr>")
            
        sug = item.get("sugars_g")
        if sug is not None and not pd.isna(sug) and str(sug).strip():
            rows.append(f"<tr><td>&nbsp;&nbsp;heraf sukkerarter</td><td>{sug} g</td></tr>")
            
        prot = item.get("protein_g")
        if prot is not None and not pd.isna(prot) and str(prot).strip():
            rows.append(f"<tr><td>Protein</td><td>{prot} g</td></tr>")
            
        salt = item.get("salt_g")
        if salt is not None and not pd.isna(salt) and str(salt).strip():
            rows.append(f"<tr><td>Salt</td><td>{salt} g</td></tr>")
            
        if rows:
            parts.append(f"<h3>Næringsindhold {basis}</h3><table>\n" + "\n".join(rows) + "\n</table>")
            
    # 5. Preparation
    prep_da = safe_str(item.get("tilberedning_da") or item.get("Tilberedning (DA)"))
    prep_en = safe_str(item.get("preparation_en") or item.get("Preparation (EN)"))
    prep = prep_da or prep_en
    if prep:
        parts.append(f"<h3>Tilberedning</h3><p>{prep}</p>")
        
    # 6. Storage
    opb_da = safe_str(item.get("opbevaring_da") or item.get("Opbevaring (DA)"))
    opb_en = safe_str(item.get("storage_en") or item.get("Storage (EN)"))
    opb = opb_da or opb_en or "Opbevares tørt og køligt."
    parts.append(f"<h3>Opbevaring</h3><p>{opb}</p>")
    
    return "".join(parts)


def convert_record_to_shopify_row(item: dict[str, Any], batch_tag: str = "import") -> dict[str, Any]:
    barcode = clean_barcode(item.get("barcode") or item.get("Barcode"))
    sku = str(item.get("pos_sku") or item.get("POS SKU") or item.get("supplier_sku") or "").strip()
    if sku.lower() in {"none", "nan", "null"}:
        sku = ""
        
    # Title
    raw_title = (
        item.get("fuldt_navn_da")
        or item.get("Fuldt navn (DA)")
        or item.get("full_name_en")
        or item.get("Full name (EN)")
        or item.get("pos_product_name")
        or item.get("literal_label_name")
        or item.get("Tên nguyên văn trên nhãn")
        or item.get("product_name")
        or item.get("Title")
        or ""
    )
    if raw_title is None or pd.isna(raw_title):
        raw_title = ""
    title = str(raw_title).strip()
    if title.lower() in {"none", "nan", "null"}:
        title = ""
    if not title:
        title = f"Asiatisk produkt {barcode}" if barcode else "Asiatisk produkt"
        
    # Handle
    handle = slugify(title)
    if not handle or handle == "asiatisk-produkt":
        handle = f"asiatisk-produkt-{barcode}" if barcode else f"produkt-{sku.lower()}"
        
    # Vendor
    raw_vendor = item.get("brand") or item.get("Brand") or item.get("Vendor") or "Khác"
    if raw_vendor is None or pd.isna(raw_vendor):
        raw_vendor = "Khác"
    vendor = str(raw_vendor).strip()
    if not vendor or vendor.lower() in {"none", "nan", "null"}:
        vendor = "Khác"
        
    # Category & Type
    cat_field = str(item.get("category") or item.get("Category (editorial)") or "").strip()
    category, ptype = infer_product_category_and_type(cat_field, title)
    
    # Country of origin for tags
    country = str(item.get("country_of_origin") or item.get("Country of origin") or "Asien").strip()
    if not country or country.lower() in {"none", "nan", "null"}:
        country = "Asien"
    tags = f"{ptype}, {vendor}, {country}, {batch_tag}"
    
    # Grams
    grams_val = item.get("net_quantity") or item.get("Net quantity") or 100
    try:
        grams = int(float(grams_val))
    except Exception:
        grams = 100
        
    # Price
    price = item.get("pos_price") or item.get("Variant Price")
    if not price or pd.isna(price):
        price = "25" if "Sauce" in ptype or "Karry" in ptype else "15"
        
    # HTML Body
    body_html = generate_danish_html_body(item)
    
    # Image Src
    if barcode:
        image_src = f"https://rabuta.dk/cdn/shop/files/{barcode}.jpg"
    else:
        image_src = ""
        
    seo_title = title
    seo_desc = f"Køb {title} online hos Rabuta.dk. Hurtig levering i hele Danmark."
    
    return {
        "Handle": handle,
        "Title": title,
        "Body (HTML)": body_html,
        "Vendor": vendor,
        "Product Category": category,
        "Type": ptype,
        "Tags": tags,
        "Published": "TRUE",
        "Option1 Name": "Title",
        "Option1 Value": "Default Title",
        "Variant SKU": sku,
        "Variant Grams": grams,
        "Variant Inventory Tracker": "shopify",
        "Variant Inventory Qty": 100,
        "Variant Inventory Policy": "deny",
        "Variant Fulfillment Service": "manual",
        "Variant Price": price,
        "Variant Compare At Price": "",
        "Variant Requires Shipping": "TRUE",
        "Variant Taxable": "TRUE",
        "Variant Barcode": barcode,
        "Image Src": image_src,
        "Image Position": 1,
        "Image Alt Text": title,
        "Gift Card": "FALSE",
        "SEO Title": seo_title,
        "SEO Description": seo_desc,
        "Status": "active",
    }


def export_shopify_csv(records: list[dict[str, Any]], output_path: str | Path, batch_tag: str = "import") -> Path:
    """Exports a list of product records into a standard 28-column Shopify CSV."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    rows = [convert_record_to_shopify_row(r, batch_tag=batch_tag) for r in records]
    
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SHOPIFY_28_COLUMNS, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            
    print(f"Shopify CSV exported: {output_path} ({len(rows)} products)")
    return output_path


def export_master_excel(records: list[dict[str, Any]], output_path: str | Path) -> Path:
    """Exports a consolidated Excel master file where image column points to <barcode>.jpg."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    df = pd.DataFrame(records)
    # Ensure barcode and image reference are text
    if "barcode" in df.columns:
        df["barcode"] = df["barcode"].apply(clean_barcode)
    if "Website Front Image" not in df.columns:
        if "barcode" in df.columns:
            df["Website Front Image"] = df["barcode"].apply(lambda b: f"{b}.jpg" if b else "")
        elif "Barcode" in df.columns:
            df["Website Front Image"] = df["Barcode"].apply(lambda b: f"{clean_barcode(b)}.jpg" if b else "")
            
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Master Products")
        
    print(f"Master Excel exported: {output_path} ({len(df)} rows)")
    return output_path
