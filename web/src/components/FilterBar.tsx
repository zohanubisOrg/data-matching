"use client";

import React from "react";
import { Search, X, Filter, ArrowUpDown, LayoutGrid, TableProperties, Download } from "lucide-react";
import { CatalogStats, ProductItem } from "@/types/product";

interface FilterBarProps {
  search: string;
  onSearchChange: (value: string) => void;
  statusFilter: string;
  onStatusFilterChange: (status: string) => void;
  brandFilter: string;
  onBrandFilterChange: (brand: string) => void;
  categoryLevel1Filter: string;
  onCategoryLevel1FilterChange: (cat: string) => void;
  categoryLevel2Filter: string;
  onCategoryLevel2FilterChange: (cat: string) => void;
  categoriesLevel1: string[];
  categoriesLevel2: string[];
  sortBy: string;
  onSortChange: (sort: string) => void;
  viewMode: "grid" | "table";
  onViewModeChange: (mode: "grid" | "table") => void;
  brands: string[];
  stats: CatalogStats;
  filteredProducts: ProductItem[];
}

export function FilterBar({
  search,
  onSearchChange,
  statusFilter,
  onStatusFilterChange,
  brandFilter,
  onBrandFilterChange,
  categoryLevel1Filter,
  onCategoryLevel1FilterChange,
  categoryLevel2Filter,
  onCategoryLevel2FilterChange,
  categoriesLevel1,
  categoriesLevel2,
  sortBy,
  onSortChange,
  viewMode,
  onViewModeChange,
  brands,
  stats,
  filteredProducts,
}: FilterBarProps) {
  const exportToCSV = () => {
    if (!filteredProducts.length) return;
    const headers = [
      "Barcode",
      "Brand",
      "Original Product Name",
      "Net Weight",
      "Variant",
      "POS SKU",
      "POS Product Name",
      "Detection Method",
      "Original Image",
      "Status",
    ];

    const rows = filteredProducts.map((p) => [
      `"${p.barcode || ""}"`,
      `"${(p.brand || "").replace(/"/g, '""')}"`,
      `"${(p.product_name || "").replace(/"/g, '""')}"`,
      `"${(p.net_weight || "").replace(/"/g, '""')}"`,
      `"${(p.variant || "").replace(/"/g, '""')}"`,
      `"${p.pos_sku || ""}"`,
      `"${(p.pos_product_name || "").replace(/"/g, '""')}"`,
      `"${p.detection_method || ""}"`,
      `"${p.original_image || ""}"`,
      `"${p.status || ""}"`,
    ]);

    const csvContent = "\uFEFF" + [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `G1_products_export_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-4 mb-6">
      {/* Search Input, Filters & View Mode */}
      <div className="flex flex-col lg:flex-row gap-3">
        {/* Search */}
        <div className="relative flex-1">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Tìm theo Barcode, Tên sản phẩm, Brand, POS SKU..."
            className="w-full pl-10 pr-10 py-2.5 bg-slate-900/90 border border-slate-700/80 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500/80 focus:ring-1 focus:ring-cyan-500/50 transition-all"
          />
          {search && (
            <button
              onClick={() => onSearchChange("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white p-1"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Controls Bar */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Category Level 1 Dropdown */}
          <div className="relative min-w-[160px]">
            <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
            <select
              value={categoryLevel1Filter}
              onChange={(e) => onCategoryLevel1FilterChange(e.target.value)}
              className="w-full pl-9 pr-8 py-2.5 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs text-slate-200 focus:outline-none focus:border-cyan-500/80 cursor-pointer appearance-none"
            >
              <option value="">Tất cả Nhóm Cấp 1 ({categoriesLevel1.length})</option>
              {categoriesLevel1.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>

          {/* Category Level 2 Dropdown */}
          <div className="relative min-w-[170px]">
            <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
            <select
              value={categoryLevel2Filter}
              onChange={(e) => onCategoryLevel2FilterChange(e.target.value)}
              className="w-full pl-9 pr-8 py-2.5 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs text-slate-200 focus:outline-none focus:border-cyan-500/80 cursor-pointer appearance-none"
            >
              <option value="">Tất cả Nhóm Cấp 2 ({categoriesLevel2.length})</option>
              {categoriesLevel2.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>

          {/* Brand Dropdown */}
          <div className="relative min-w-[170px]">
            <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
            <select
              value={brandFilter}
              onChange={(e) => onBrandFilterChange(e.target.value)}
              className="w-full pl-9 pr-8 py-2.5 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs text-slate-200 focus:outline-none focus:border-cyan-500/80 cursor-pointer appearance-none"
            >
              <option value="">Tất cả Thương hiệu ({brands.length})</option>
              {brands.map((b) => (
                <option key={b} value={b}>
                  {b}
                </option>
              ))}
            </select>
          </div>

          {/* Sort Dropdown */}
          <div className="relative min-w-[150px]">
            <ArrowUpDown className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
            <select
              value={sortBy}
              onChange={(e) => onSortChange(e.target.value)}
              className="w-full pl-9 pr-8 py-2.5 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs text-slate-200 focus:outline-none focus:border-cyan-500/80 cursor-pointer appearance-none"
            >
              <option value="default">Thứ tự gốc</option>
              <option value="name_asc">Tên (A-Z)</option>
              <option value="brand_asc">Thương hiệu (A-Z)</option>
              <option value="barcode_asc">Barcode (0-9)</option>
            </select>
          </div>

          {/* View Mode Toggle */}
          <div className="flex items-center rounded-xl bg-slate-900/90 border border-slate-700/80 p-0.5">
            <button
              onClick={() => onViewModeChange("grid")}
              title="Xem dạng Lưới (Grid)"
              className={`p-2 rounded-lg transition-colors ${
                viewMode === "grid" ? "bg-cyan-500/20 text-cyan-300" : "text-slate-400 hover:text-white"
              }`}
            >
              <LayoutGrid className="w-4 h-4" />
            </button>
            <button
              onClick={() => onViewModeChange("table")}
              title="Xem dạng Bảng (Table)"
              className={`p-2 rounded-lg transition-colors ${
                viewMode === "table" ? "bg-cyan-500/20 text-cyan-300" : "text-slate-400 hover:text-white"
              }`}
            >
              <TableProperties className="w-4 h-4" />
            </button>
          </div>

          {/* Export CSV Button */}
          <button
            onClick={exportToCSV}
            title="Xuất danh sách đang lọc ra CSV"
            className="flex items-center gap-1.5 px-3 py-2.5 rounded-xl text-xs font-medium text-slate-200 bg-slate-900/90 border border-slate-700/80 hover:border-emerald-500/60 hover:text-emerald-300 transition-colors"
          >
            <Download className="w-3.5 h-3.5 text-emerald-400" />
            <span className="hidden sm:inline">Xuất CSV</span>
          </button>
        </div>
      </div>

      {/* Status Filter Tabs */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => onStatusFilterChange("ALL")}
          className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
            statusFilter === "ALL"
              ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/50 shadow-[0_0_12px_rgba(6,182,212,0.2)]"
              : "bg-slate-900/60 text-slate-400 border border-slate-800 hover:border-slate-700 hover:text-slate-200"
          }`}
        >
          Tất cả ({stats.total})
        </button>

        <button
          onClick={() => onStatusFilterChange("CONFIRMED")}
          className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
            statusFilter === "CONFIRMED"
              ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/50 shadow-[0_0_12px_rgba(16,185,129,0.2)]"
              : "bg-slate-900/60 text-slate-400 border border-slate-800 hover:border-slate-700 hover:text-slate-200"
          }`}
        >
          Đã xác định ({stats.confirmed})
        </button>

        <button
          onClick={() => onStatusFilterChange("POS_MATCHED")}
          className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
            statusFilter === "POS_MATCHED"
              ? "bg-blue-500/20 text-blue-300 border border-blue-500/50 shadow-[0_0_12px_rgba(59,130,246,0.2)]"
              : "bg-slate-900/60 text-slate-400 border border-slate-800 hover:border-slate-700 hover:text-slate-200"
          }`}
        >
          Khớp POS ({stats.pos_matched})
        </button>

        <button
          onClick={() => onStatusFilterChange("MANUAL_REVIEW")}
          className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
            statusFilter === "MANUAL_REVIEW"
              ? "bg-amber-500/20 text-amber-300 border border-amber-500/50 shadow-[0_0_12px_rgba(245,158,11,0.2)]"
              : "bg-slate-900/60 text-slate-400 border border-slate-800 hover:border-slate-700 hover:text-slate-200"
          }`}
        >
          Cần kiểm tra ({stats.review_needed})
        </button>
      </div>
    </div>
  );
}
