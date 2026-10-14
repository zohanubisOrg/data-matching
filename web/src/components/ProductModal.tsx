"use client";

import React, { useEffect, useState } from "react";
import {
  X,
  Check,
  Copy,
  Download,
  ExternalLink,
  Tag,
  Weight,
  Sparkles,
  AlertCircle,
  ShoppingBag,
  Eye,
  Globe,
  Flame,
  ShieldCheck,
  Building2,
  Calendar,
  Layers,
  ChevronLeft,
  ChevronRight,
  Info,
  Apple,
} from "lucide-react";
import { ProductItem } from "@/types/product";

interface ProductModalProps {
  product: ProductItem | null;
  onClose: () => void;
  onPrev?: () => void;
  onNext?: () => void;
}

export function ProductModal({ product, onClose, onPrev, onNext }: ProductModalProps) {
  const [activeTab, setActiveTab] = useState<"overview" | "nutrition" | "ingredients" | "compliance">("overview");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft" && onPrev) onPrev();
      if (e.key === "ArrowRight" && onNext) onNext();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, onPrev, onNext]);

  if (!product) return null;

  const isConfirmed = product.status === "CONFIRMED";
  const hasPos = Boolean(product.pos_sku);

  const handleCopyBarcode = () => {
    if (product.barcode) {
      navigator.clipboard.writeText(product.barcode);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200">
      <div
        className="relative w-full max-w-5xl max-h-[92vh] glass-panel rounded-3xl overflow-hidden flex flex-col border border-slate-700/80 shadow-2xl bg-slate-900/95"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Top Modal Bar */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/50">
          <div className="flex items-center gap-3">
            {product.record_id && (
              <span className="text-xs font-mono font-bold px-2.5 py-1 rounded bg-slate-800 text-cyan-300 border border-slate-700">
                {product.record_id}
              </span>
            )}
            <span
              className={`text-xs font-semibold px-3 py-1 rounded-full border ${
                isConfirmed
                  ? "bg-emerald-950 text-emerald-300 border-emerald-500/40"
                  : "bg-amber-950 text-amber-300 border-amber-500/40"
              }`}
            >
              {isConfirmed ? "✅ FIC Standard Compliant" : "⚠️ Cần xem xét"}
            </span>
            <span className="text-xs text-slate-400 font-mono hidden sm:inline">
              File gốc: {product.original_image}
            </span>
          </div>

          <div className="flex items-center gap-2">
            {onPrev && (
              <button
                onClick={onPrev}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
                title="Sản phẩm trước (Phím mũi tên trái)"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
            )}
            {onNext && (
              <button
                onClick={onNext}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
                title="Sản phẩm tiếp (Phím mũi tên phải)"
              >
                <ChevronRight className="w-5 h-5" />
              </button>
            )}
            <button
              onClick={onClose}
              className="p-1.5 ml-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Modal Scrollable Body */}
        <div className="overflow-y-auto p-6 space-y-6 flex-1">
          {/* Header & Product Titles */}
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider flex items-center gap-1.5 bg-cyan-950/40 px-2.5 py-0.5 rounded-md border border-cyan-800/40">
                <Tag className="w-3.5 h-3.5" />
                {product.brand || "Chưa rõ Brand"}
              </span>
              {product.category && (
                <span className="text-xs font-medium text-slate-300 bg-slate-800 px-2.5 py-0.5 rounded-md border border-slate-700">
                  {product.category}
                </span>
              )}
              {product.packaging && (
                <span className="text-xs font-medium text-slate-300 bg-slate-800 px-2.5 py-0.5 rounded-md border border-slate-700">
                  {product.packaging}
                </span>
              )}
            </div>

            <h2 className="text-xl sm:text-2xl font-bold text-white leading-tight">
              {product.full_name_en || product.product_name}
            </h2>

            {product.fuldt_navn_da && (
              <div className="text-sm text-slate-300 flex items-center gap-2">
                <span className="text-xs font-semibold uppercase px-1.5 py-0.5 rounded bg-blue-900/60 text-blue-300 border border-blue-700">
                  DA
                </span>
                <span className="italic">{product.fuldt_navn_da}</span>
              </div>
            )}
          </div>

          {/* Navigation Tabs */}
          <div className="flex border-b border-slate-800 gap-2 pb-px overflow-x-auto">
            <button
              onClick={() => setActiveTab("overview")}
              className={`px-4 py-2 text-xs sm:text-sm font-semibold border-b-2 transition-colors flex items-center gap-2 ${
                activeTab === "overview"
                  ? "border-cyan-400 text-cyan-300 bg-cyan-950/20"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              <Eye className="w-4 h-4" /> Tổng quan & Soi ảnh
            </button>
            <button
              onClick={() => setActiveTab("nutrition")}
              className={`px-4 py-2 text-xs sm:text-sm font-semibold border-b-2 transition-colors flex items-center gap-2 ${
                activeTab === "nutrition"
                  ? "border-cyan-400 text-cyan-300 bg-cyan-950/20"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              <Apple className="w-4 h-4" /> Bảng dinh dưỡng (100g)
            </button>
            <button
              onClick={() => setActiveTab("ingredients")}
              className={`px-4 py-2 text-xs sm:text-sm font-semibold border-b-2 transition-colors flex items-center gap-2 ${
                activeTab === "ingredients"
                  ? "border-cyan-400 text-cyan-300 bg-cyan-950/20"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              <Layers className="w-4 h-4" /> Thành phần & Dị ứng
            </button>
            <button
              onClick={() => setActiveTab("compliance")}
              className={`px-4 py-2 text-xs sm:text-sm font-semibold border-b-2 transition-colors flex items-center gap-2 ${
                activeTab === "compliance"
                  ? "border-cyan-400 text-cyan-300 bg-cyan-950/20"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              <Building2 className="w-4 h-4" /> Nguồn gốc & Nhà nhập khẩu
            </button>
          </div>

          {/* TAB 1: Overview & Dual Visual Inspection */}
          {activeTab === "overview" && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Left: Cropped Website Front View */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs font-semibold text-cyan-400">
                    <span className="flex items-center gap-1.5">
                      <Eye className="w-3.5 h-3.5" />
                      Ảnh mặt trước Website (Chuẩn Portrait WebP)
                    </span>
                    <span className="text-slate-400 font-mono text-[11px]">
                      {product.cropped_width > 0 ? `${product.cropped_width}x${product.cropped_height} px` : ""}
                    </span>
                  </div>
                  <div className="relative aspect-[3/4] max-h-[380px] bg-slate-950 rounded-2xl p-4 flex items-center justify-center border border-cyan-500/30 overflow-hidden shadow-inner mx-auto">
                    {product.front_web_url ? (
                      <img
                        src={product.front_web_url}
                        alt="Front view"
                        className="max-h-full max-w-full object-contain rounded-lg"
                      />
                    ) : (
                      <span className="text-slate-500 text-xs">Đang nạp ảnh</span>
                    )}
                  </div>
                  {product.front_web_url && (
                    <div className="text-right">
                      <a
                        href={product.front_web_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-xs text-cyan-400 hover:text-cyan-300 inline-flex items-center gap-1"
                      >
                        Mở ảnh gốc trong tab mới <ExternalLink className="w-3 h-3" />
                      </a>
                    </div>
                  )}
                </div>

                {/* Right: Raw 2-Sided Photography */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs font-semibold text-slate-400">
                    <span>Ảnh chụp bao bì gốc (2 mặt)</span>
                    <span className="font-mono text-[11px]">{product.original_image}</span>
                  </div>
                  <div className="relative aspect-[3/4] max-h-[380px] bg-slate-950 rounded-2xl p-4 flex items-center justify-center border border-slate-800 overflow-hidden shadow-inner mx-auto">
                    {product.raw_web_url ? (
                      <img
                        src={product.raw_web_url}
                        alt="Raw photo"
                        className="max-h-full max-w-full object-contain rounded-lg opacity-90 hover:opacity-100 transition-opacity"
                      />
                    ) : (
                      <span className="text-slate-500 text-xs">Chưa có ảnh</span>
                    )}
                  </div>
                  {product.raw_web_url && (
                    <div className="text-right">
                      <a
                        href={product.raw_web_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-xs text-slate-400 hover:text-slate-200 inline-flex items-center gap-1"
                      >
                        Xem ảnh 2 mặt gốc <ExternalLink className="w-3 h-3" />
                      </a>
                    </div>
                  )}
                </div>
              </div>

              {/* Quick Info Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                <div className="p-3.5 bg-slate-950/60 rounded-xl border border-slate-800">
                  <div className="text-xs text-slate-400 flex items-center justify-between">
                    <span>Mã vạch (Barcode)</span>
                    <button
                      onClick={handleCopyBarcode}
                      className="text-slate-400 hover:text-cyan-300 flex items-center gap-1 text-[11px]"
                    >
                      {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                      {copied ? "Đã chép" : "Copy"}
                    </button>
                  </div>
                  <div className="text-base font-mono font-bold text-cyan-300 mt-1">{product.barcode}</div>
                  <div className="text-[11px] text-emerald-400/90 mt-0.5">{product.barcode_check_status || "Đúng GS1 Checksum"}</div>
                </div>

                <div className="p-3.5 bg-slate-950/60 rounded-xl border border-slate-800">
                  <div className="text-xs text-slate-400">Khối lượng / Thể tích (Net)</div>
                  <div className="text-base font-bold text-white mt-1">
                    {product.net_quantity ? `${product.net_quantity} ${product.net_unit || "g"}` : product.net_weight || "---"}
                    {product.unit_count ? ` (${product.unit_count} packs)` : ""}
                  </div>
                  <div className="text-[11px] text-slate-400 mt-0.5">Variant: {product.variant || "Standard"}</div>
                </div>

                <div className="p-3.5 bg-slate-950/60 rounded-xl border border-slate-800">
                  <div className="text-xs text-slate-400">Khớp POS Master SKU</div>
                  <div className="text-base font-bold text-emerald-400 mt-1">{product.pos_sku || "Chưa gán SKU"}</div>
                  <div className="text-[11px] text-slate-400 truncate mt-0.5">{product.pos_product_name || "---"}</div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: Nutrition Facts */}
          {activeTab === "nutrition" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between bg-slate-950/60 p-3 rounded-xl border border-slate-800">
                <span className="text-xs font-semibold text-cyan-400 flex items-center gap-1.5">
                  <Flame className="w-4 h-4" /> Bảng giá trị dinh dưỡng
                </span>
                <span className="text-xs text-slate-400 font-mono">
                  Quy chuẩn: {product.nutrition_basis || "per 100 g"}
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 text-center">
                  <div className="text-xs text-slate-400">Năng lượng (kJ)</div>
                  <div className="text-lg font-bold text-white mt-1">
                    {product.energy_kj !== null && product.energy_kj !== undefined ? `${product.energy_kj} kJ` : "---"}
                  </div>
                </div>
                <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 text-center">
                  <div className="text-xs text-slate-400">Năng lượng (kcal)</div>
                  <div className="text-lg font-bold text-amber-400 mt-1">
                    {product.energy_kcal !== null && product.energy_kcal !== undefined ? `${product.energy_kcal} kcal` : "---"}
                  </div>
                </div>
                <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 text-center">
                  <div className="text-xs text-slate-400">Chất béo (Fat)</div>
                  <div className="text-lg font-bold text-white mt-1">
                    {product.fat_g !== null && product.fat_g !== undefined ? `${product.fat_g} g` : "---"}
                  </div>
                  {product.saturates_g !== null && product.saturates_g !== undefined && (
                    <div className="text-[11px] text-slate-400 mt-0.5">Bão hòa: {product.saturates_g}g</div>
                  )}
                </div>
                <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 text-center">
                  <div className="text-xs text-slate-400">Carbohydrate</div>
                  <div className="text-lg font-bold text-white mt-1">
                    {product.carbohydrate_g !== null && product.carbohydrate_g !== undefined ? `${product.carbohydrate_g} g` : "---"}
                  </div>
                  {product.sugars_g !== null && product.sugars_g !== undefined && (
                    <div className="text-[11px] text-slate-400 mt-0.5">Đường: {product.sugars_g}g</div>
                  )}
                </div>
                <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 text-center">
                  <div className="text-xs text-slate-400">Chất xơ (Fibre)</div>
                  <div className="text-lg font-bold text-white mt-1">
                    {product.fibre_g !== null && product.fibre_g !== undefined ? `${product.fibre_g} g` : "---"}
                  </div>
                </div>
                <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 text-center">
                  <div className="text-xs text-slate-400">Đạm (Protein)</div>
                  <div className="text-lg font-bold text-white mt-1">
                    {product.protein_g !== null && product.protein_g !== undefined ? `${product.protein_g} g` : "---"}
                  </div>
                </div>
                <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 text-center">
                  <div className="text-xs text-slate-400">Muối (Salt)</div>
                  <div className="text-lg font-bold text-cyan-300 mt-1">
                    {product.salt_g !== null && product.salt_g !== undefined ? `${product.salt_g} g` : "---"}
                  </div>
                </div>
                <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 text-center">
                  <div className="text-xs text-slate-400">Độ cồn (Alcohol)</div>
                  <div className="text-lg font-bold text-emerald-400 mt-1">
                    {product.alcohol_vol !== null && product.alcohol_vol !== undefined ? `${product.alcohol_vol}%` : "0.0%"}
                  </div>
                </div>
              </div>

              {product.other_nutrition_source && (
                <div className="p-3.5 bg-slate-950/60 rounded-xl border border-slate-800 text-xs text-slate-300">
                  <span className="font-semibold text-slate-200">Ghi chú dinh dưỡng phụ:</span> {product.other_nutrition_source}
                </div>
              )}
            </div>
          )}

          {/* TAB 3: Ingredients & Allergens */}
          {activeTab === "ingredients" && (
            <div className="space-y-5">
              {/* Allergens Alert Box */}
              {(product.allergens_en || product.allergener_da || product.may_contain_label) && (
                <div className="p-4 rounded-xl bg-amber-950/30 border border-amber-500/40 space-y-2">
                  <div className="text-xs font-bold text-amber-300 uppercase flex items-center gap-1.5">
                    <AlertCircle className="w-4 h-4 text-amber-400" /> Cảnh báo dị ứng (Allergens - EU FIC 1169/2011)
                  </div>
                  {product.allergens_en && (
                    <div className="text-xs text-amber-100">
                      <strong>EN:</strong> {product.allergens_en}
                    </div>
                  )}
                  {product.allergener_da && (
                    <div className="text-xs text-amber-100">
                      <strong>DA:</strong> {product.allergener_da}
                    </div>
                  )}
                  {product.may_contain_label && (
                    <div className="text-xs text-amber-200/80 italic">
                      <strong>May contain traces:</strong> {product.may_contain_label}
                    </div>
                  )}
                </div>
              )}

              {/* Ingredients EN */}
              <div className="space-y-1.5">
                <div className="text-xs font-bold text-cyan-400 uppercase tracking-wide">
                  Thành phần tiếng Anh (Ingredients - EN)
                </div>
                <div className="p-3.5 bg-slate-950 rounded-xl border border-slate-800 text-xs text-slate-200 leading-relaxed">
                  {product.ingredients_en || "Chưa có dữ liệu thành phần tiếng Anh"}
                </div>
              </div>

              {/* Ingredients DA */}
              {product.ingredienser_da && (
                <div className="space-y-1.5">
                  <div className="text-xs font-bold text-blue-400 uppercase tracking-wide">
                    Thành phần tiếng Đan Mạch (Ingredienser - DA)
                  </div>
                  <div className="p-3.5 bg-slate-950 rounded-xl border border-slate-800 text-xs text-slate-200 leading-relaxed">
                    {product.ingredienser_da}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 4: Compliance & Supply Chain */}
          {activeTab === "compliance" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-3">
                <div className="text-xs font-bold text-cyan-400 uppercase flex items-center gap-1.5">
                  <Building2 className="w-4 h-4" /> Nhà sản xuất & Nguồn gốc
                </div>
                <div className="text-xs space-y-1 text-slate-300">
                  <div><strong>Xuất xứ (Country of origin):</strong> {product.country_of_origin || "---"}</div>
                  {product.origin_label_evidence && (
                    <div className="text-[11px] text-slate-400 italic">Bằng chứng trên nhãn: {product.origin_label_evidence}</div>
                  )}
                  <div><strong>Nhà sản xuất (Manufacturer):</strong> {product.manufacturer || "---"}</div>
                  {product.manufacturer_address && (
                    <div className="text-[11px] text-slate-400">{product.manufacturer_address}</div>
                  )}
                </div>
              </div>

              <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-3">
                <div className="text-xs font-bold text-emerald-400 uppercase flex items-center gap-1.5">
                  <Globe className="w-4 h-4" /> Nhà nhập khẩu EU (Importer)
                </div>
                <div className="text-xs space-y-1 text-slate-300">
                  <div><strong>Đơn vị nhập khẩu:</strong> {product.importer || "---"}</div>
                  {product.importer_address && (
                    <div className="text-[11px] text-slate-400">{product.importer_address}</div>
                  )}
                  {product.distributor && (
                    <div><strong>Nhà phân phối:</strong> {product.distributor}</div>
                  )}
                </div>
              </div>

              <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-3">
                <div className="text-xs font-bold text-amber-400 uppercase flex items-center gap-1.5">
                  <Calendar className="w-4 h-4" /> Hạn dùng, Ngày SX & Lô
                </div>
                <div className="text-xs space-y-1 text-slate-300">
                  <div><strong>Hạn dùng (BBE / Expiry):</strong> {product.best_before_expiry || "---"}</div>
                  <div><strong>Ngày SX (MFG Date):</strong> {product.manufacture_date || "---"}</div>
                  <div><strong>Mã lô (Lot / Batch):</strong> {product.lot_batch || "---"}</div>
                </div>
              </div>

              <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-3">
                <div className="text-xs font-bold text-purple-400 uppercase flex items-center gap-1.5">
                  <ShieldCheck className="w-4 h-4" /> Chứng chỉ & Bảo quản
                </div>
                <div className="text-xs space-y-1 text-slate-300">
                  <div><strong>Bảo quản (Storage EN):</strong> {product.storage_en || "Store cool and dry."}</div>
                  {product.opbevaring_da && (
                    <div className="text-[11px] text-slate-400">DA: {product.opbevaring_da}</div>
                  )}
                  {product.claims_certifications && (
                    <div><strong>Chứng nhận / Claim:</strong> <span className="text-emerald-300">{product.claims_certifications}</span></div>
                  )}
                  {product.warnings_label && (
                    <div className="text-amber-300 text-[11px]"><strong>Cảnh báo:</strong> {product.warnings_label}</div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer Bar */}
        <div className="px-6 py-3.5 border-t border-slate-800 bg-slate-950/60 flex items-center justify-between text-xs text-slate-400">
          <div>
            Record: <span className="font-mono text-cyan-300">{product.record_id || product.barcode}</span>
          </div>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-semibold transition"
          >
            Đóng
          </button>
        </div>
      </div>
    </div>
  );
}
