"use client";

import React, { useEffect, useState, useMemo } from "react";
import { Header } from "@/components/Header";
import { FilterBar } from "@/components/FilterBar";
import { ProductCard } from "@/components/ProductCard";
import { ProductTableView } from "@/components/ProductTableView";
import { ProductModal } from "@/components/ProductModal";
import { CatalogPayload, ProductItem } from "@/types/product";
import { Loader2, PackageX } from "lucide-react";

export default function CatalogPage() {
  const [data, setData] = useState<CatalogPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filter States
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [brandFilter, setBrandFilter] = useState("");
  const [sortBy, setSortBy] = useState("default");
  const [viewMode, setViewMode] = useState<"grid" | "table">("grid");

  // Modal State
  const [selectedProduct, setSelectedProduct] = useState<ProductItem | null>(null);

  useEffect(() => {
    fetch("/data/products.json")
      .then((res) => {
        if (!res.ok) throw new Error("Chưa có dữ liệu products.json. Vui lòng chạy sync script.");
        return res.json();
      })
      .then((payload: CatalogPayload) => {
        setData(payload);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  // Filtered & Sorted Products
  const filteredProducts = useMemo(() => {
    if (!data) return [];
    let list = [...data.products];

    // Status filter
    if (statusFilter === "CONFIRMED") {
      list = list.filter((p) => p.status === "CONFIRMED");
    } else if (statusFilter === "POS_MATCHED") {
      list = list.filter((p) => Boolean(p.pos_sku));
    } else if (statusFilter === "MANUAL_REVIEW") {
      list = list.filter((p) => p.status !== "CONFIRMED");
    }

    // Brand filter
    if (brandFilter) {
      list = list.filter((p) => p.brand === brandFilter);
    }

    // Search query
    if (search.trim()) {
      const q = search.toLowerCase().trim();
      list = list.filter(
        (p) =>
          p.barcode.toLowerCase().includes(q) ||
          p.product_name.toLowerCase().includes(q) ||
          p.brand.toLowerCase().includes(q) ||
          p.pos_sku.toLowerCase().includes(q) ||
          p.pos_product_name.toLowerCase().includes(q) ||
          p.original_image.toLowerCase().includes(q)
      );
    }

    // Sorting
    if (sortBy === "name_asc") {
      list.sort((a, b) => a.product_name.localeCompare(b.product_name));
    } else if (sortBy === "brand_asc") {
      list.sort((a, b) => a.brand.localeCompare(b.brand));
    } else if (sortBy === "barcode_asc") {
      list.sort((a, b) => a.barcode.localeCompare(b.barcode));
    }

    return list;
  }, [data, search, statusFilter, brandFilter, sortBy]);

  // Modal navigation index
  const currentIndex = useMemo(() => {
    if (!selectedProduct) return -1;
    return filteredProducts.findIndex((p) => p.original_image === selectedProduct.original_image);
  }, [selectedProduct, filteredProducts]);

  const handlePrev = () => {
    if (currentIndex > 0) {
      setSelectedProduct(filteredProducts[currentIndex - 1]);
    }
  };

  const handleNext = () => {
    if (currentIndex >= 0 && currentIndex < filteredProducts.length - 1) {
      setSelectedProduct(filteredProducts[currentIndex + 1]);
    }
  };

  return (
    <div className="min-h-screen bg-[#090d16] text-slate-100 flex flex-col selection:bg-cyan-500/30 selection:text-cyan-200">
      {/* Header with Stats */}
      {data && <Header stats={data.stats} />}

      {/* Main Body */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {loading && (
          <div className="flex flex-col items-center justify-center py-32 text-slate-400 gap-3">
            <Loader2 className="w-8 h-8 animate-spin text-cyan-400" />
            <p className="text-sm font-medium">Đang tải danh mục sản phẩm G1...</p>
          </div>
        )}

        {error && (
          <div className="max-w-xl mx-auto my-12 p-6 glass-panel rounded-2xl border-amber-500/40 text-center space-y-3">
            <div className="text-amber-400 font-bold">Chưa tìm thấy dữ liệu web</div>
            <p className="text-sm text-slate-400">{error}</p>
            <p className="text-xs text-slate-500">
              Chạy lệnh <code className="text-cyan-300 font-mono">python scripts/prepare_web_delivery.py</code> để tạo dữ liệu.
            </p>
          </div>
        )}

        {!loading && data && (
          <>
            {/* Filter and Search Bar */}
            <FilterBar
              search={search}
              onSearchChange={setSearch}
              statusFilter={statusFilter}
              onStatusFilterChange={setStatusFilter}
              brandFilter={brandFilter}
              onBrandFilterChange={setBrandFilter}
              sortBy={sortBy}
              onSortChange={setSortBy}
              viewMode={viewMode}
              onViewModeChange={setViewMode}
              brands={data.brands}
              stats={data.stats}
              filteredProducts={filteredProducts}
            />

            {/* Results Counter */}
            <div className="flex items-center justify-between text-xs text-slate-400 mb-4 px-1">
              <span>
                Hiển thị <strong className="text-white font-mono">{filteredProducts.length}</strong> / {data.stats.total} sản phẩm
              </span>
              {search && (
                <span>
                  Bộ lọc: &ldquo;{search}&rdquo;
                </span>
              )}
            </div>

            {/* Content: Grid or Table */}
            {filteredProducts.length > 0 ? (
              viewMode === "grid" ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-5">
                  {filteredProducts.map((p) => (
                    <ProductCard key={p.original_image} product={p} onSelect={setSelectedProduct} />
                  ))}
                </div>
              ) : (
                <ProductTableView products={filteredProducts} onSelect={setSelectedProduct} />
              )
            ) : (
              <div className="py-24 text-center glass-panel rounded-2xl p-8 border-slate-800 space-y-3">
                <PackageX className="w-12 h-12 text-slate-600 mx-auto" />
                <div className="text-base font-bold text-slate-300">Không tìm thấy sản phẩm phù hợp</div>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Hãy thử tìm kiếm với từ khóa khác hoặc bỏ các điều kiện lọc.
                </p>
              </div>
            )}
          </>
        )}
      </main>

      {/* Side-by-Side Verification Modal */}
      <ProductModal
        product={selectedProduct}
        onClose={() => setSelectedProduct(null)}
        onPrev={currentIndex > 0 ? handlePrev : undefined}
        onNext={currentIndex >= 0 && currentIndex < filteredProducts.length - 1 ? handleNext : undefined}
      />
    </div>
  );
}
