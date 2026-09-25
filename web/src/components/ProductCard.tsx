"use client";

import React, { useState } from "react";
import { Copy, Check, ExternalLink, Tag, Weight, Sparkles, AlertCircle, ShoppingBag } from "lucide-react";
import { ProductItem } from "@/types/product";

interface ProductCardProps {
  product: ProductItem;
  onSelect: (product: ProductItem) => void;
}

export function ProductCard({ product, onSelect }: ProductCardProps) {
  const [copied, setCopied] = useState(false);
  const [imgError, setImgError] = useState(false);

  const isConfirmed = product.status === "CONFIRMED";
  const hasPos = Boolean(product.pos_sku);

  const handleCopyBarcode = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (product.barcode) {
      navigator.clipboard.writeText(product.barcode);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div
      onClick={() => onSelect(product)}
      className="glass-panel glass-panel-hover rounded-2xl overflow-hidden cursor-pointer transition-all duration-300 flex flex-col group relative"
    >
      {/* Top Status & POS Indicator */}
      <div className="absolute top-3 left-3 right-3 z-10 flex items-center justify-between pointer-events-none">
        <span
          className={`text-[11px] font-semibold px-2.5 py-1 rounded-full border backdrop-blur-md shadow-sm ${
            isConfirmed
              ? "bg-emerald-950/80 text-emerald-300 border-emerald-500/40"
              : "bg-amber-950/80 text-amber-300 border-amber-500/40"
          }`}
        >
          {isConfirmed ? "✅ Confirmed" : "⚠️ Cần xem xét"}
        </span>

        {hasPos && (
          <span className="text-[11px] font-medium px-2 py-0.5 rounded-md bg-cyan-950/80 text-cyan-300 border border-cyan-500/30 flex items-center gap-1 backdrop-blur-md">
            <ShoppingBag className="w-3 h-3" />
            POS: {product.pos_sku}
          </span>
        )}
      </div>

      {/* Product Image Stage */}
      <div className="relative aspect-[4/3] bg-gradient-to-b from-slate-900/50 to-slate-950/80 p-4 flex items-center justify-center overflow-hidden border-b border-slate-800/60">
        {!imgError && product.front_web_url ? (
          <img
            src={product.front_web_url}
            alt={product.product_name || "Product front"}
            onError={() => setImgError(true)}
            className="max-h-full max-w-full object-contain rounded-lg transition-transform duration-300 group-hover:scale-105"
            loading="lazy"
          />
        ) : (
          <div className="text-center p-4 text-slate-500 text-xs flex flex-col items-center gap-1">
            <AlertCircle className="w-6 h-6 text-slate-600" />
            <span>Ảnh mặt trước đang đồng bộ</span>
          </div>
        )}

        {/* Floating barcode overlay at bottom of image */}
        <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between bg-slate-950/90 backdrop-blur-md rounded-lg px-2.5 py-1.5 border border-slate-800 text-xs">
          <span className="font-mono text-slate-200 tracking-wider font-semibold truncate">
            {product.barcode || "NO_BARCODE"}
          </span>
          <button
            onClick={handleCopyBarcode}
            title="Sao chép Barcode"
            className="p-1 hover:text-cyan-400 text-slate-400 transition-colors pointer-events-auto"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* Body Content */}
      <div className="p-4 flex-1 flex flex-col justify-between">
        <div>
          {/* Brand */}
          <div className="text-xs font-semibold text-cyan-400 uppercase tracking-wider mb-1 truncate flex items-center gap-1">
            <Tag className="w-3 h-3" />
            {product.brand || "---"}
          </div>

          {/* Product Name */}
          <h3 className="text-sm font-bold text-white leading-snug line-clamp-2 mb-2 group-hover:text-cyan-200 transition-colors">
            {product.product_name || "Chưa rõ tên sản phẩm"}
          </h3>

          {/* Attributes */}
          <div className="flex flex-wrap gap-1.5 text-[11px] text-slate-300">
            {product.net_weight && (
              <span className="px-2 py-0.5 rounded bg-slate-800/80 border border-slate-700/50 flex items-center gap-1">
                <Weight className="w-3 h-3 text-slate-400" />
                {product.net_weight}
              </span>
            )}
            {product.variant && (
              <span className="px-2 py-0.5 rounded bg-slate-800/80 border border-slate-700/50 truncate max-w-[150px]">
                {product.variant}
              </span>
            )}
          </div>
        </div>

        {/* Footer info */}
        <div className="mt-4 pt-3 border-t border-slate-800/60 flex items-center justify-between text-[11px] text-slate-400">
          <span className="truncate max-w-[140px] font-mono text-slate-500">
            {product.original_image}
          </span>
          <span className="text-cyan-400/80 font-medium group-hover:translate-x-0.5 transition-transform flex items-center gap-1">
            Chi tiết <ExternalLink className="w-3 h-3" />
          </span>
        </div>
      </div>
    </div>
  );
}
