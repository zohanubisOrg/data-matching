# Spec Delta: Shopify Catalog Import

## Purpose

Enables automated export of standardized 28-column Shopify product import CSV datasets compliant with Danish e-commerce requirements and EU Regulation 1169/2011.

## ADDED Requirements

### Requirement: 28-Column Shopify CSV & Master Excel Consolidation
The system SHALL export product metadata into a consolidated master Excel workbook and a valid Shopify CSV file containing all 28 standard Shopify columns: Handle, Title, Body (HTML), Vendor, Product Category, Type, Tags, Published, Option1 Name, Option1 Value, Variant SKU, Variant Grams, Variant Inventory Tracker, Variant Inventory Qty, Variant Inventory Policy, Variant Fulfillment Service, Variant Price, Variant Compare At Price, Variant Requires Shipping, Variant Taxable, Variant Barcode, Image Src, Image Position, Image Alt Text, Gift Card, SEO Title, SEO Description, Status.

#### Scenario: Full Shopify Export for Verified Products
- **WHEN** verified packaging metadata and POS matching data are exported to Shopify CSV and Master Excel
- **THEN** all 28 columns are populated with standard values, Handle is a kebab-case slug, Published is TRUE, Status is active, Variant Inventory Tracker is set to shopify, and Image columns point strictly to the canonical barcode front crop (`<barcode>.jpg` / `https://rabuta.dk/cdn/shop/files/<barcode>.jpg`).

### Requirement: Text Barcode Formatting Without Scientific Notation
The system SHALL format all `Variant Barcode` entries as exact numeric string literals to prevent spreadsheet applications and Shopify importers from converting long digits into scientific notation (e.g. 4.80489E+12).

#### Scenario: 13-digit EAN Barcode formatting
- **WHEN** an EAN-13 barcode like `4804888804172` is exported
- **THEN** the CSV output contains the verbatim digit string without floating point conversion or exponential representation.

### Requirement: Rich Danish HTML Body Generation
The system SHALL generate localized Danish `Body (HTML)` descriptions containing manufacturer metadata, ingredients (`<h3>Ingredienser</h3>`), allergens (`<h3>Allergener</h3>`), a nutritional table (`<h3>Næringsindhold pr. 100 g</h3><table>...</table>`), preparation guide (`<h3>Tilberedning</h3>`), and storage guidelines (`<h3>Opbevaring</h3>`).

#### Scenario: Complete nutrition and ingredient label rendering
- **WHEN** product contains nutrition facts and allergen statements
- **THEN** the Body (HTML) string includes clean semantic HTML paragraphs and table rows formatted in Danish.
