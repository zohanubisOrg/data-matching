"use client";

import React, { useState } from "react";
import { Copy, Check, ExternalLink, AlertCircle, ShoppingBag, Eye, Apple, Building2 } from "lucide-react";
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
    <div className="glass-panel rounded-2xl overflow-hidden border border-slate-800 shadow-xl">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-950 text-slate-400 font-semibold uppercase tracking-wider border-b border-slate-800 text-[11px]">
            <tr>
              <th className="py-3 px-3 w-12 text-center">ID</th>
              <th className="py-3 px-3 w-16 text-center">Ảnh</th>
              <th className="py-3 px-4 min-w-[130px]">Barcode</th>
              <th className="py-3 px-3 min-w-[100px]">Brand</th>
              <th className="py-3 px-4 min-w-[220px]">Tên đầy đủ (EN / DA)</th>
              <th className="py-3 px-3 min-w-[80px]">Khối lượng</th>
              <th className="py-3 px-3 min-w-[80px]">Kcal / 100g</th>
              <th className="py-3 px-3 min-w-[110px]">Xuất xứ / Importer</th>
              <th className="py-3 px-3 min-w-[90px]">POS SKU</th>
              <th className="py-3 px-3 min-w-[90px] text-center">Trạng thái</th>
              <th className="py-3 px-3 w-16 text-center">Chi tiết</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 text-slate-200">
            {products.map((p, idx) => {
              const isConfirmed = p.status === "CONFIRMED";
              const hasPos = Boolean(p.pos_sku);

              return (
                <tr
                  key={p.record_id || p.barcode || idx}
                  onClick={() => onSelect(p)}
                  className="hover:bg-slate-800/40 cursor-pointer transition-colors group"
                >
                  <td className="py-2.5 px-3 text-center font-mono text-cyan-400/90 font-bold text-[11px]">
                    {p.record_id || `G1-${String(idx + 1).padStart(4, "0")}`}
                  </td>

                  {/* Thumbnail */}
                  <td className="py-2.5 px-3 text-center">
                    <div className="w-12 h-12 bg-slate-950 rounded-lg p-1 border border-slate-800 flex items-center justify-center overflow-hidden mx-auto">
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
                    <div className="text-[10px] text-emerald-400/80 truncate max-w-[130px]">
                      {p.barcode_check_status || "GS1 Verified"}
                    </div>
                  </td>

                  {/* Brand */}
                  <td className="py-2.5 px-3 font-semibold text-slate-300">
                    {p.brand || "---"}
                  </td>

                  {/* Product Names (EN & DA) */}
                  <td className="py-2.5 px-4">
                    <div className="font-semibold text-white line-clamp-1 group-hover:text-cyan-300 transition-colors">
                      {p.full_name_en || p.product_name}
                    </div>
                    {p.fuldt_navn_da && (
                      <div className="text-[11px] text-slate-400 italic line-clamp-1 mt-0.5">
                        <span className="text-[10px] text-blue-400 font-semibold mr-1">DA:</span>
                        {p.fuldt_navn_da}
                      </div>
                    )}
                  </td>

                  {/* Net Weight */}
                  <td className="py-2.5 px-3 text-slate-300 font-medium">
                    {p.net_quantity ? `${p.net_quantity} ${p.net_unit || "g"}` : p.net_weight || "---"}
                  </td>

                  {/* Kcal */}
                  <td className="py-2.5 px-3 font-mono text-amber-300/90 font-semibold">
                    {p.energy_kcal !== null && p.energy_kcal !== undefined ? `${p.energy_kcal}` : "---"}
                  </td>

                  {/* Origin & Importer */}
                  <td className="py-2.5 px-3 text-slate-300">
                    <div className="font-medium text-slate-200">{p.country_of_origin || "---"}</div>
                    {p.importer && (
                      <div className="text-[10px] text-slate-400 truncate max-w-[120px]">{p.importer}</div>
                    )}
                  </td>

                  {/* POS SKU */}
                  <td className="py-2.5 px-3">
                    {hasPos ? (
                      <span className="font-mono font-bold text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-500/30">
                        {p.pos_sku}
                      </span>
                    ) : (
                      <span className="text-slate-500 text-[11px]">Chưa gán</span>
                    )}
                  </td>

                  {/* Status */}
                  <td className="py-2.5 px-3 text-center">
                    <span
                      className={`inline-block text-[10px] font-semibold px-2 py-0.5 rounded-full border ${
                        isConfirmed
                          ? "bg-emerald-950 text-emerald-300 border-emerald-500/40"
                          : "bg-amber-950 text-amber-300 border-amber-500/40"
                      }`}
                    >
                      {isConfirmed ? "FIC OK" : "Cần duyệt"}
                    </span>
                  </td>

                  {/* Action View */}
                  <td className="py-2.5 px-3 text-center">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelect(p);
                      }}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-700/60 transition"
                      title="Soi chi tiết"
                    >
                      <Eye className="w-4 h-4 text-cyan-400" />
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
