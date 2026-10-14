# Spec Delta: shopify-live-store-sync

## Purpose

Cung cấp khả năng đồng bộ catalog sản phẩm, tải ảnh studio mới lên Shopify CDN, ánh xạ Product Type và Tags theo phân cấp 2 tầng, và thiết lập cấu trúc Navigation Menu lồng nhau 2 cấp trên cửa hàng Shopify Live.

## ADDED Requirements

### Requirement: Shopify In-Place Media and Attribute Update
The system SHALL update existing Shopify live products with newly generated HD Studio images, set Product Type to Category Level 1, and inject Category Level 2 into product tags without altering product IDs or SEO handles.

#### Scenario: In-place catalog update
- **WHEN** an online product exists on Shopify
- **THEN** the system updates its primary image attachment, assigns Product Type to Level 1, and appends `subcat:<Level 2>` to Tags.

### Requirement: Nested 2-Tier Navigation Menu Construction
The system SHALL construct a nested 2-tier Main Navigation Menu via GraphQL Navigation API where each Level 1 collection expands into its corresponding Level 2 subcategories.

#### Scenario: Nested navigation menu creation
- **WHEN** the store navigation menu is generated
- **THEN** Main Menu contains Level 1 items (e.g. Snacks, Nudler, Saucer), each containing nested child menu items linking to corresponding Level 2 subcategories.

### Requirement: Web Inspection Portal Data Synchronization
The system SHALL export the refreshed catalog JSON and images to the Web Inspection Portal to enable side-by-side visual comparison between cropped studio images and raw warehouse photos.

#### Scenario: Inspection portal synchronization
- **WHEN** catalog processing completes
- **THEN** `web/public/data/products.json` is updated with Level 1 and Level 2 filters and side-by-side image comparison modal references.
