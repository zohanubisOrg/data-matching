export interface ProductItem {
  barcode: string;
  literal_label_name?: string;
  full_name_en: string;
  fuldt_navn_da?: string;
  brand: string;
  record_id?: string;
  barcode_check_status?: string;
  name_source_notes?: string;
  variant?: string;
  stt?: number;
  category?: string;
  category_level_1?: string;
  category_level_2?: string;
  online_status?: string;
  packaging?: string;
  net_quantity?: number | null;
  net_unit?: string;
  unit_count?: number | null;
  barcode_text_read?: string;
  supplier_sku?: string;
  other_printed_codes?: string;

  // Supply Chain & Origin
  manufacturer?: string;
  manufacturer_address?: string;
  country_of_origin?: string;
  origin_label_evidence?: string;
  importer?: string;
  importer_address?: string;
  distributor?: string;

  // Ingredients & Allergens
  ingredients_label_language?: string;
  ingredients_en?: string;
  ingredienser_da?: string;
  ingredient_translation_notes?: string;
  allergens_label?: string;
  allergens_en?: string;
  allergener_da?: string;
  may_contain_label?: string;

  // Nutrition Facts
  nutrition_basis?: string;
  energy_kj?: number | null;
  energy_kcal?: number | null;
  fat_g?: number | null;
  saturates_g?: number | null;
  carbohydrate_g?: number | null;
  sugars_g?: number | null;
  fibre_g?: number | null;
  protein_g?: number | null;
  salt_g?: number | null;
  other_nutrition_source?: string;

  // Usage, Storage & Compliance
  preparation_label?: string;
  preparation_en?: string;
  tilberedning_da?: string;
  storage_label?: string;
  storage_en?: string;
  opbevaring_da?: string;
  warnings_label?: string;
  claims_certifications?: string;
  alcohol_vol?: number | null;
  manufacture_date?: string;
  best_before_expiry?: string;
  lot_batch?: string;
  website_contact?: string;
  other_legible_info?: string;

  // UI / Display compatibility
  product_name: string;
  net_weight: string;
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
  categories_level_1?: string[];
  categories_level_2?: string[];
  products: ProductItem[];
}
