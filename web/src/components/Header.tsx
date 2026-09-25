"use client";

import React from "react";
import { CheckCircle2, AlertCircle, ShoppingBag, Layers, Download, Sparkles } from "lucide-react";
import { CatalogStats } from "@/types/product";

interface HeaderProps {
  stats: CatalogStats;
}

export function Header({ stats }: HeaderProps) {
  const confirmedRate = stats.total > 0 ? ((stats.confirmed / stats.total) * 100).toFixed(1) : "0";
  const posRate = stats.total > 0 ? ((stats.pos_matched / stats.total) * 100).toFixed(1) : "0";

  return (
    <header className="border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-md sticky top-0 z-30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="flex h-2.5 w-2.5 rounded-full bg-cyan-400 animate-pulse" />
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-white flex items-center gap-2">
                G1 Delivery <span className="text-cyan-400 font-mono text-lg">Visual Portal</span>
              </h1>
              <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
                Vercel Ready
              </span>
            </div>
            <p className="text-xs sm:text-sm text-slate-400 mt-1">
              Báo cáo đối soát Barcode & Ảnh mặt trước bao bì tách chuẩn 100% cho Website
            </p>
          </div>

          {/* Quick Action buttons */}
          <div className="flex items-center gap-3">
            <a
              href="/data/products.json"
              download="G1_products.json"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-300 bg-slate-900 border border-slate-700/80 hover:border-cyan-500/60 hover:text-white transition-colors"
            >
              <Download className="w-3.5 h-3.5 text-cyan-400" />
              Tải JSON
            </a>
          </div>
        </div>

        {/* High-Tech Metrics Bar */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-5">
          <div className="glass-panel rounded-xl p-3.5 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <div className="text-xs text-slate-400 font-medium">Tổng Sản Phẩm</div>
              <div className="text-xl font-bold text-white font-mono">{stats.total}</div>
            </div>
          </div>

          <div className="glass-panel rounded-xl p-3.5 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <CheckCircle2 className="w-5 h-5" />
            </div>
            <div>
              <div className="text-xs text-slate-400 font-medium">Đã Xác Định Barcode</div>
              <div className="text-xl font-bold text-emerald-400 font-mono">
                {stats.confirmed} <span className="text-xs text-slate-500 font-normal">({confirmedRate}%)</span>
              </div>
            </div>
          </div>

          <div className="glass-panel rounded-xl p-3.5 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              <ShoppingBag className="w-5 h-5" />
            </div>
            <div>
              <div className="text-xs text-slate-400 font-medium">Khớp Danh Mục POS</div>
              <div className="text-xl font-bold text-cyan-400 font-mono">
                {stats.pos_matched} <span className="text-xs text-slate-500 font-normal">({posRate}%)</span>
              </div>
            </div>
          </div>

          <div className="glass-panel rounded-xl p-3.5 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20">
              <AlertCircle className="w-5 h-5" />
            </div>
            <div>
              <div className="text-xs text-slate-400 font-medium">Cần Xem Xét Thủ Công</div>
              <div className="text-xl font-bold text-amber-400 font-mono">{stats.review_needed}</div>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
