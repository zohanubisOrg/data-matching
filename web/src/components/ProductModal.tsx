"use client";

import React, { useEffect } from "react";
import { X, Check, Copy, Download, ExternalLink, Tag, Weight, Sparkles, AlertCircle, ShoppingBag, Eye } from "lucide-react";
import { ProductItem } from "@/types/product";

interface ProductModalProps {
  product: ProductItem | null;
  onClose: () => void;
  onPrev?: () => void;
  onNext?: () => void;
}

export function ProductModal({ product, onClose, onPrev, onNext }: ProductModalProps) {
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200">
      <div
        className="relative w-full max-w-5xl max-h-[92vh] glass-panel rounded-3xl overflow-hidden flex flex-col border border-slate-700/80 shadow-2xl bg-slate-900/95"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Top Modal Bar */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/50">
          <div className="flex items-center gap-3">
            <span
              className={`text-xs font-semibold px-3 py-1 rounded-full border ${
                isConfirmed
                  ? "bg-emerald-950 text-emerald-300 border-emerald-500/40"
                  : "bg-amber-950 text-amber-300 border-amber-500/40"
              }`}
            >
              {isConfirmed ? "✅ Barcode Confirmed" : "⚠️ Cần xem xét thủ công"}
            </span>
            <span className="text-xs text-slate-400 font-mono hidden sm:inline">
              File gốc: {product.original_image}
            </span>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Scrollable Body */}
        <div className="overflow-y-auto p-6 space-y-6">
          {/* Title & Brand */}
          <div>
            <div className="text-xs font-bold text-cyan-400 uppercase tracking-wider mb-1 flex items-center gap-1.5">
              <Tag className="w-3.5 h-3.5" />
              {product.brand || "Thương hiệu chưa xác định"}
            </div>
            <h2 className="text-xl sm:text-2xl font-bold text-white leading-tight">
              {product.product_name || "Chưa rõ tên sản phẩm"}
            </h2>
          </div>

          {/* Dual Visual Inspection: Front View vs Raw Photo */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Left: Cropped Website Front View */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs font-semibold text-cyan-400">
                <span className="flex items-center gap-1.5">
                  <Eye className="w-3.5 h-3.5" />
                  Ảnh mặt trước Website (Đã tách chuẩn)
                </span>
                <span className="text-slate-400 font-mono text-[11px]">
                  {product.cropped_width > 0 ? `${product.cropped_width}x${product.cropped_height} px` : ""}
                </span>
              </div>
              <div className="relative aspect-[4/3] bg-slate-950 rounded-2xl p-4 flex items-center justify-center border border-cyan-500/30 overflow-hidden shadow-inner">
                {product.front_web_url ? (
                  <img
                    src={product.front_web_url}
                    alt="Front view"
                    className="max-h-full max-w-full object-contain rounded-lg"
                  />
                ) : (
                  <span className="text-slate-500 text-xs">Đang xử lý ảnh</span>
                )}
              </div>
              {product.front_web_url && (
                <div className="text-right">
                  <a
                    href={product.front_web_url}
                    download={product.barcode ? `${product.barcode}.webp` : "front.webp"}
                    className="inline-flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300 font-medium"
                  >
                    <Download className="w-3 h-3" />
                    Tải ảnh WebP
                  </a>
                </div>
              )}
            </div>

            {/* Right: Raw Original Photo for verification */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-400">
                <span className="flex items-center gap-1.5">
                  <Eye className="w-3.5 h-3.5" />
                  Ảnh chụp gốc (Đối chiếu 2 mặt)
                </span>
                <span className="text-slate-500 font-mono text-[11px]">{product.original_image}</span>
              </div>
              <div className="relative aspect-[4/3] bg-slate-950 rounded-2xl p-4 flex items-center justify-center border border-slate-800 overflow-hidden shadow-inner">
                {product.raw_web_url ? (
                  <img
                    src={product.raw_web_url}
                    alt="Raw 2-sided photo"
                    className="max-h-full max-w-full object-contain rounded-lg opacity-90 hover:opacity-100 transition-opacity"
                  />
                ) : (
                  <span className="text-slate-500 text-xs">Ảnh gốc chưa đồng bộ</span>
                )}
              </div>
            </div>
          </div>

          {/* Technical Metadata Inspection Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 pt-2">
            <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800 space-y-1">
              <div className="text-xs text-slate-400 font-medium">Mã Vạch (Barcode)</div>
              <div className="font-mono text-base font-bold text-cyan-400 tracking-wider flex items-center gap-2">
                <span>{product.barcode || "NO_BARCODE"}</span>
              </div>
              <div className="text-[11px] text-slate-500">
                Phương thức nhận diện: <code className="text-slate-400">{product.detection_method}</code>
              </div>
            </div>

            <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800 space-y-1">
              <div className="text-xs text-slate-400 font-medium">Khối lượng / Thể tích (Net Wt)</div>
              <div className="text-sm font-bold text-white">{product.net_weight || "---"}</div>
              <div className="text-[11px] text-slate-500">
                Variant / Vị: <span className="text-slate-300">{product.variant || "---"}</span>
              </div>
            </div>

            <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800 space-y-1">
              <div className="text-xs text-slate-400 font-medium">Khớp POS Shopbox</div>
              <div className="text-sm font-bold text-emerald-400 font-mono">
                {product.pos_sku ? `SKU: ${product.pos_sku}` : "Không có trong POS"}
              </div>
              <div className="text-[11px] text-slate-400 truncate">
                {product.pos_product_name || "---"}
              </div>
            </div>
          </div>
        </div>

        {/* Bottom Navigator */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-slate-800 bg-slate-950/60 text-xs">
          <div className="text-slate-500">
            Dùng phím <kbd className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">←</kbd> và{" "}
            <kbd className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">→</kbd> để chuyển sản phẩm
          </div>
          <div className="flex gap-2">
            {onPrev && (
              <button
                onClick={onPrev}
                className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors"
              >
                Trước
              </button>
            )}
            {onNext && (
              <button
                onClick={onNext}
                className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors"
              >
                Tiếp theo
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
