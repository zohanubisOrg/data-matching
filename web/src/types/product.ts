export interface ProductItem {
  barcode: string;
  brand: string;
  product_name: string;
  net_weight: string;
  variant: string;
  pos_sku: string;
  pos_product_name: string;
  original_image: string;
  website_front_image: string;
  front_web_url: string;
  raw_web_url: string;
  front_box_2d: number[];
  cropped_width: number;
  cropped_height: number;
  detection_method: string;
  status: "CONFIRMED" | "NO_BARCODE_MANUAL_REVIEW" | string;
}

export interface CatalogStats {
  total: number;
  confirmed: number;
  pos_matched: number;
  review_needed: number;
  brands_count: number;
}

export interface CatalogPayload {
  stats: CatalogStats;
  brands: string[];
  products: ProductItem[];
}
