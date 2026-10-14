"use client";

import React, { useState } from "react";
import { Copy, Check, Tag, Weight, ShoppingBag, AlertCircle, Apple, Globe } from "lucide-react";
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
          className="text-[11px] font-mono font-bold px-2.5 py-0.5 rounded bg-slate-950/80 text-cyan-300 border border-slate-700/80 backdrop-blur-md"
        >
          {product.record_id || "G1"}
        </span>

        {hasPos && (
          <span className="text-[11px] font-medium px-2 py-0.5 rounded-md bg-cyan-950/80 text-cyan-300 border border-cyan-500/30 flex items-center gap-1 backdrop-blur-md">
            <ShoppingBag className="w-3 h-3" />
            POS: {product.pos_sku}
          </span>
        )}
      </div>

      {/* Product Image Stage */}
      <div className="relative aspect-[3/4] max-h-[260px] bg-gradient-to-b from-slate-900/50 to-slate-950/80 p-4 flex items-center justify-center overflow-hidden border-b border-slate-800/60">
        {!imgError && product.front_web_url ? (
          <img
            src={product.front_web_url}
            alt={product.full_name_en || product.product_name}
            onError={() => setImgError(true)}
            className="max-h-full max-w-full object-contain rounded-lg transition-transform duration-300 group-hover:scale-105"
            loading="lazy"
          />
        ) : (
          <div className="text-center p-4 text-slate-500 text-xs flex flex-col items-center gap-1">
            <AlertCircle className="w-6 h-6 text-slate-600" />
            <span>Ảnh mặt trước đang tải</span>
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
          {/* Brand & Category */}
          <div className="flex items-center justify-between gap-1 mb-1">
            <div className="text-xs font-semibold text-cyan-400 uppercase tracking-wider truncate flex items-center gap-1">
              <Tag className="w-3 h-3" />
              {product.brand || "---"}
            </div>
            {product.category && (
              <span className="text-[10px] text-slate-400 bg-slate-800/60 px-1.5 py-0.5 rounded">
                {product.category}
              </span>
            )}
          </div>

          {/* Product Name */}
          <h3 className="text-sm font-bold text-white leading-snug line-clamp-2 mb-1 group-hover:text-cyan-200 transition-colors">
            {product.full_name_en || product.product_name || "Chưa rõ tên sản phẩm"}
          </h3>

          {/* Danish Name */}
          {product.fuldt_navn_da && (
            <div className="text-[11px] text-slate-400 italic line-clamp-1 mb-2">
              <span className="text-[10px] text-blue-400 font-semibold mr-1 not-italic">DA:</span>
              {product.fuldt_navn_da}
            </div>
          )}

          {/* Attributes Pills */}
          <div className="flex flex-wrap gap-1.5 text-[11px] text-slate-300">
            {(product.net_quantity || product.net_weight) && (
              <span className="px-2 py-0.5 bg-slate-800 rounded-md border border-slate-700/60 flex items-center gap-1 font-medium">
                <Weight className="w-3 h-3 text-cyan-400" />
                {product.net_quantity ? `${product.net_quantity} ${product.net_unit || "g"}` : product.net_weight}
              </span>
            )}

            {product.energy_kcal !== null && product.energy_kcal !== undefined && (
              <span className="px-2 py-0.5 bg-amber-950/40 text-amber-300 rounded-md border border-amber-500/30 flex items-center gap-1 font-mono font-medium">
                <Apple className="w-3 h-3 text-amber-400" />
                {product.energy_kcal} kcal
              </span>
            )}

            {product.country_of_origin && (
              <span className="px-2 py-0.5 bg-slate-800/80 rounded-md border border-slate-700/60 text-slate-300 flex items-center gap-1">
                <Globe className="w-3 h-3 text-emerald-400" />
                {product.country_of_origin}
              </span>
            )}
          </div>
        </div>

        {/* Footer info */}
        <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400">
          <span className="truncate max-w-[150px]">{product.importer || product.packaging || "Bag"}</span>
          <span className="text-cyan-400 font-semibold group-hover:translate-x-0.5 transition-transform">
            Chi tiết &rarr;
          </span>
        </div>
      </div>
    </div>
  );
}
