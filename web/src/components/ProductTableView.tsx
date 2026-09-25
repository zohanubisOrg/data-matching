"use client";

import React, { useState } from "react";
import { Copy, Check, ExternalLink, AlertCircle, ShoppingBag, Eye } from "lucide-react";
import { ProductItem } from "@/types/product";

interface ProductTableViewProps {
  products: ProductItem[];
  onSelect: (product: ProductItem) => void;
}

export function ProductTableView({ products, onSelect }: ProductTableViewProps) {
  const [copiedBarcode, setCopiedBarcode] = useState<string | null>(null);

  const handleCopy = (e: React.MouseEvent, barcode: string) => {
    e.stopPropagation();
    if (barcode) {
      navigator.clipboard.writeText(barcode);
      setCopiedBarcode(barcode);
      setTimeout(() => setCopiedBarcode(null), 1500);
    }
  };

  return (
    <div className="glass-panel rounded-2xl overflow-hidden border border-slate-800">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-950/80 text-slate-400 font-semibold uppercase tracking-wider border-b border-slate-800 text-[11px]">
            <tr>
              <th className="py-3 px-4 w-12 text-center">#</th>
              <th className="py-3 px-4 w-20">Ảnh mặt trước</th>
              <th className="py-3 px-4 min-w-[140px]">Barcode</th>
              <th className="py-3 px-4 min-w-[120px]">Thương hiệu</th>
              <th className="py-3 px-4 min-w-[200px]">Tên sản phẩm</th>
              <th className="py-3 px-4 min-w-[90px]">Khối lượng</th>
              <th className="py-3 px-4 min-w-[110px]">Variant</th>
              <th className="py-3 px-4 min-w-[100px]">POS SKU</th>
              <th className="py-3 px-4 min-w-[150px]">Tên khớp POS</th>
              <th className="py-3 px-4 min-w-[110px] text-center">Trạng thái</th>
              <th className="py-3 px-4 w-16 text-center">Xem</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 text-slate-200">
            {products.map((p, idx) => {
              const isConfirmed = p.status === "CONFIRMED";
              const hasPos = Boolean(p.pos_sku);

              return (
                <tr
                  key={p.original_image}
                  onClick={() => onSelect(p)}
                  className="hover:bg-slate-800/40 cursor-pointer transition-colors group"
                >
                  <td className="py-2.5 px-4 text-center font-mono text-slate-500 text-[11px]">
                    {idx + 1}
                  </td>

                  {/* Thumbnail */}
                  <td className="py-2.5 px-4">
                    <div className="w-12 h-12 bg-slate-950 rounded-lg p-1 border border-slate-800 flex items-center justify-center overflow-hidden">
                      {p.front_web_url ? (
                        <img
                          src={p.front_web_url}
                          alt="Front"
                          className="max-h-full max-w-full object-contain group-hover:scale-110 transition-transform"
                          loading="lazy"
                        />
                      ) : (
                        <AlertCircle className="w-4 h-4 text-slate-600" />
                      )}
                    </div>
                  </td>

                  {/* Barcode */}
                  <td className="py-2.5 px-4">
                    <div className="flex items-center gap-1.5 font-mono font-semibold text-cyan-300">
                      <span>{p.barcode || "NO_BARCODE"}</span>
                      {p.barcode && (
                        <button
                          onClick={(e) => handleCopy(e, p.barcode)}
                          title="Sao chép Barcode"
                          className="text-slate-500 hover:text-cyan-400 p-0.5 transition-colors"
                        >
                          {copiedBarcode === p.barcode ? (
                            <Check className="w-3.5 h-3.5 text-emerald-400" />
                          ) : (
                            <Copy className="w-3.5 h-3.5" />
                          )}
                        </button>
                      )}
                    </div>
                    <div className="text-[10px] text-slate-500 truncate max-w-[130px]">
                      {p.detection_method}
                    </div>
                  </td>

                  {/* Brand */}
                  <td className="py-2.5 px-4 font-semibold text-slate-300">
                    {p.brand || "---"}
                  </td>

                  {/* Product Name */}
                  <td className="py-2.5 px-4">
                    <div className="font-medium text-white group-hover:text-cyan-200 transition-colors line-clamp-2">
                      {p.product_name || "Chưa rõ tên sản phẩm"}
                    </div>
                    <div className="text-[10px] text-slate-500 font-mono">
                      {p.original_image}
                    </div>
                  </td>

                  {/* Net Weight */}
                  <td className="py-2.5 px-4 text-slate-300">
                    {p.net_weight || "---"}
                  </td>

                  {/* Variant */}
                  <td className="py-2.5 px-4 text-slate-400 truncate max-w-[110px]">
                    {p.variant || "---"}
                  </td>

                  {/* POS SKU */}
                  <td className="py-2.5 px-4 font-mono font-semibold text-emerald-400">
                    {p.pos_sku || "---"}
                  </td>

                  {/* POS Product Name */}
                  <td className="py-2.5 px-4 text-slate-400 truncate max-w-[150px]">
                    {p.pos_product_name || "---"}
                  </td>

                  {/* Status */}
                  <td className="py-2.5 px-4 text-center">
                    <span
                      className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold border ${
                        isConfirmed
                          ? "bg-emerald-950/80 text-emerald-300 border-emerald-500/30"
                          : "bg-amber-950/80 text-amber-300 border-amber-500/30"
                      }`}
                    >
                      {isConfirmed ? "Confirmed" : "Review"}
                    </span>
                  </td>

                  {/* Action */}
                  <td className="py-2.5 px-4 text-center">
                    <button className="p-1 text-slate-400 hover:text-cyan-400 transition-colors">
                      <Eye className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
