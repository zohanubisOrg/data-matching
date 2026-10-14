# 🛍️ Rabuta E-Commerce & Shopify Catalog Automation Suite

[![Store: rabuta.dk](https://img.shields.io/badge/Store-rabuta.dk-green?logo=shopify)](https://rabuta.dk)
[![Next.js 16](https://img.shields.io/badge/Next.js-16.3.6-black?logo=next.js)](https://nextjs.org/)
[![React 19](https://img.shields.io/badge/React-19.2.8-blue?logo=react)](https://react.dev/)
[![Tailwind CSS v4](https://img.shields.io/badge/Tailwind_CSS-v4.0-38bdf8?logo=tailwindcss)](https://tailwindcss.com/)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python)](https://www.python.org/)
[![Live Web Portal](https://img.shields.io/badge/Vercel-Live_Portal-000000?logo=vercel)](https://web-mu-seven-60.vercel.app)

An end-to-end automated catalog processing, reconciliation, and live Shopify synchronization suite for **Rabuta Asian Supermarket (`rabuta.dk`)**.

---

## 🌟 Current Live Store Status (`rabuta.dk`)

* 🛒 **Live Store Domain:** [https://rabuta.dk](https://rabuta.dk) (`rabuta.myshopify.com`)
* 📊 **Catalog Scale:** **1,195 Live Products** synced with 100% valid GS1 barcodes, populated SKUs, categorized types, and high-res studio images.
* 🌐 **Multi-Language Support (4 Languages):**
  * 🇩🇰 **Danish (`da`)** - Primary Default Locale (`/`)
  * 🇬🇧 **English (`en`)** - Secondary Language (`/en`)
  * 🇻🇳 **Vietnamese (`vi`)** - Subfolder Routing (`/vi`)
  * 🇹🇭 **Thai (`th`)** - Subfolder Routing (`/th`)
* 🗂️ **8 Smart Collections Synchronized in 4 Languages:**
  * `Nudler` (Mì, Bún & Phở / บะหมี่และก๋วยเตี๋ยว)
  * `Snacks` (Bánh kẹo & Ăn vặt / ขนมและของทานเล่น)
  * `Saucer & Sojasauce` (Nước xốt & Nước tương / ซอสปรุงรสและซีอิ๊ว)
  * `Krydderier & Karry` (Gia vị & Cà ri / เครื่องเทศและพริกแกง)
  * `Drikkevarer & Vin` (Đồ uống & Trà / เครื่องดื่มและชา)
  * `Konserves & Kokosmælk` (Đồ hộp & Nước cốt dừa / อาหารกระป๋องและกะทิ)
  * `Ris, Mel & Tørvarer` (Gạo, Bột & Đồ khô / ข้าว แป้ง และของแห้ง)
  * `Andre asiatiske varer` (Sản phẩm Á Châu khác / สินค้าเอเชียอื่นๆ)
* 📄 **6 Core Operational & Legal Pages Published:**
  * `om-os` (About Rabuta / Giới thiệu Rabuta / เกี่ยวกับราบูตะ)
  * `kontakt-os` (Contact & Store / Liên hệ / ติดต่อเรา)
  * `levering-fragt` (Shipping & Delivery Terms / Vận chuyển & Giao hàng / การจัดส่งสินค้า)
  * `handelsbetingelser` (Terms of Service / Điều khoản dịch vụ / ข้อกำหนดและเงื่อนไข)
  * `returpolitik` (Return & Refund Policy / Chính sách đổi trả / นโยบายการคืนสินค้า)
  * `privatlivspolitik` (Privacy Policy & GDPR / Chính sách bảo mật / นโยบายความเป็นส่วนตัว)

---

## 📂 Project Architecture & Organization

```text
shopify/
├── .env                                  # Shopify Admin API Credentials & App tokens
├── scripts/                              # Core Production Scripts
│   ├── sync_to_shopify_live.py           # Bulk product sync engine (Create/Update/Resume)
│   ├── sync_full_store_multilingual.py   # Master 4-language sync for collections, pages & menus
│   ├── audit_shopify_live_catalog.py     # Live catalog 5-dimension audit engine
│   ├── setup_full_store_content_and_navigation.py # Deploy pages & navigation menus
│   ├── shopify_catalog_sync_cli.py       # Interactive CLI utility
│   ├── cleanup_workspace.py              # Workspace hygiene & maintenance tool
│   └── archive_debug/                    # Archived one-off debug & test scripts
│
├── output/                               # Master Deliverables & Reports
│   ├── reconciliation/                   # Audit reports & reconciliation summaries
│   │   ├── Shopify_Live_Catalog_Full_Audit.xlsx
│   │   ├── Shopify_Full_Bulk_Sync_Summary.xlsx
│   │   └── Standardized_95_Products_Result.xlsx
│   ├── shopify_import_final/             # Final clean Shopify import catalogs
│   ├── g1_delivery/                      # G1 Batch delivery assets & exports
│   └── archive_scratch/                  # Archived intermediate scratch files
│
├── src/product_mapper/                   # Vision AI & Ingestion Engine
│   ├── cli.py                            # Python CLI
│   ├── g1_pipeline.py                    # Multi-angle barcode & packaging pipeline
│   ├── pos_matcher.py                    # POS master reconciliation logic
│   └── vision/gemini_vision.py           # Multimodal Gemini Vision AI wrapper
│
├── web/                                  # Next.js 16 Visual Inspection Portal
│   ├── src/app/                          # Next.js App Router pages
│   ├── src/components/                   # Product grid, spreadsheet table, inspection modal
│   └── public/                           # Optimized product images and JSON catalog
│
├── source-import/                        # Customer raw catalogs and supplier price lists
├── unique_pack1/ & unique_pack2/         # Studio photography image packs
└── vercel.json                           # Vercel deployment configuration
```

---

## ⚡ Core Production Commands

### 1. Synchronize Live Store Translations (4 Languages)
Runs full translation registration across all 8 collections, 6 store pages, and all navigation links:
```powershell
python scripts/sync_full_store_multilingual.py
```

### 2. Audit Live Shopify Catalog
Performs a comprehensive 5-dimension audit on all 1,195 live products:
```powershell
python scripts/audit_shopify_live_catalog.py
```

### 3. Bulk Sync Products from Master File to Shopify
```powershell
python scripts/sync_to_shopify_live.py
```

### 4. Run Workspace Cleanup & Cache Refresh
```powershell
python scripts/cleanup_workspace.py
```

### 5. Run Web Inspection Portal
```powershell
cd web
npm run dev
```

---

## 🔐 Credentials & Environment Setup

The `.env` file contains the Shopify Custom App access credentials:
* `SHOPIFY_STORE_DOMAIN="rabuta.myshopify.com"`
* `SHOPIFY_ADMIN_ACCESS_TOKEN="shpat_..."`
* `SHOPIFY_CLIENT_ID="..."`
* `SHOPIFY_CLIENT_SECRET="..."`

---

## 🛡️ Standards & Quality Guarantees

* **GS1 Checksum Validation:** Barcodes are guaranteed 100% valid with 0 scientific notation errors.
* **Shopify GraphQL Admin API Compliant:** Uses official `translationsRegister`, `marketUpdate`, `productCreate`, `productUpdate` mutations.
* **Multi-Market URL Routing:** Active subfolder routing on `rabuta.dk` for `/th`, `/vi`, and `/en`.
