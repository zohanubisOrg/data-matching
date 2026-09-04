from html import escape
import json
from pathlib import Path

from ..models import MatchResult


def write_html(results: list[MatchResult], output: Path) -> None:
    counts = {x: sum(r.status == x for r in results) for x in ["AUTO_MATCHED", "NEED_REVIEW", "UNMATCHED", "ERROR"]}
    total = len(results)
    auto_pct = round(counts["AUTO_MATCHED"] / total * 100, 1) if total else 0
    review_pct = round(counts["NEED_REVIEW"] / total * 100, 1) if total else 0
    unmatched_pct = round(counts["UNMATCHED"] / total * 100, 1) if total else 0

    # Count unique POS products matched
    matched_barcodes = set()
    for r in results:
        if r.status == "AUTO_MATCHED" and r.candidate and r.candidate.product and r.candidate.product.barcode:
            matched_barcodes.add(r.candidate.product.barcode)
    unique_pos_matched = len(matched_barcodes)

    items_data = []
    rows_html = []
    cards_html = []

    for idx, r in enumerate(results, 1):
        try:
            relative = "../" + str(r.image.path.relative_to(output.parent)).replace("\\", "/")
        except Exception:
            relative = str(r.image.path).replace("\\", "/")

        pack_name = r.image.path.parent.name if r.image.path else (r.image.source or "unique_pack1")
        status_class = r.status.lower().replace("_", "-")
        status_label = {
            "AUTO_MATCHED": "KHỚP TỰ ĐỘNG 100%",
            "NEED_REVIEW": "CẦN XÁC NHẬN",
            "UNMATCHED": "CHƯA CÓ TRONG POS",
            "ERROR": "LỖI"
        }.get(r.status, r.status)

        conf_pct = int(round(r.confidence * 100))
        conf_color = "#10b981" if conf_pct >= 85 else ("#f59e0b" if conf_pct >= 65 else "#ef4444")

        # Cluster detection
        reason_lower = (r.reason or "").lower()
        has_dup_barcode = False
        if len(r.top_candidates) >= 2:
            p0 = r.top_candidates[0].product.product_name.strip().lower()
            p1 = r.top_candidates[1].product.product_name.strip().lower()
            if p0 == p1 and r.top_candidates[0].product.barcode != r.top_candidates[1].product.barcode:
                has_dup_barcode = True

        if "duplicate" in reason_lower or "trùng" in reason_lower or has_dup_barcode:
            cluster = "dup_barcode"
            cluster_label = "Trùng tên POS - nhiều mã vạch"
        elif "asropa" in reason_lower or "ean" in reason_lower:
            cluster = "ean13"
            cluster_label = "Mã vạch Asropa EAN-13"
        elif "weight" in reason_lower or "size" in reason_lower or "gói" in reason_lower or "ml" in reason_lower or "kg" in reason_lower:
            cluster = "size_diff"
            cluster_label = "Kiểm tra quy cách / trọng lượng"
        elif conf_pct >= 75:
            cluster = "high_score"
            cluster_label = "Độ tương đồng cao (≥75%)"
        elif r.status == "UNMATCHED":
            cluster = "unmatched"
            cluster_label = "Chưa có trong danh mục"
        else:
            cluster = "standard"
            cluster_label = "Tiêu chuẩn"

        # Search tokens
        search_parts = [
            r.image.filename.lower(),
            r.image.normalized_name.lower(),
            r.image.brand.lower() if r.image.brand else "",
            pack_name.lower(),
            r.status.lower(),
            r.reason.lower()
        ]
        if r.candidate and r.candidate.product:
            search_parts.extend([
                r.candidate.product.product_name.lower(),
                r.candidate.product.barcode or "",
                r.candidate.product.sku.lower()
            ])
        for c in r.top_candidates[:3]:
            search_parts.extend([
                c.product.product_name.lower(),
                c.product.barcode or "",
                c.product.sku.lower()
            ])
        search_str = escape(" ".join(filter(None, search_parts)))

        # Candidate objects for JS
        candidates_list = []
        for i, c in enumerate(r.top_candidates[:3], 1):
            candidates_list.append({
                "index": i,
                "name": c.product.product_name,
                "barcode": c.product.barcode or "",
                "sku": c.product.sku or "",
                "price": c.product.selling_price or "",
                "unit": c.product.unit or "",
                "category": c.product.category or "",
                "score": int(round(c.score * 100)),
                "evidence": c.evidence,
                "conflicts": c.conflicts
            })

        matched_obj = None
        if r.candidate and r.candidate.product:
            matched_obj = {
                "name": r.candidate.product.product_name,
                "barcode": r.candidate.product.barcode or "",
                "sku": r.candidate.product.sku or "",
                "price": r.candidate.product.selling_price or "",
                "unit": r.candidate.product.unit or "",
                "category": r.candidate.product.category or "",
                "score": int(round(r.candidate.score * 100))
            }

        item_json = {
            "id": idx,
            "filename": r.image.filename,
            "image_url": relative,
            "source": r.image.source or "N/A",
            "pack": pack_name,
            "normalized_name": r.image.normalized_name,
            "brand": r.image.brand or "",
            "packaging": r.image.packaging.raw if r.image.packaging else "",
            "status": r.status,
            "confidence": conf_pct,
            "match_method": r.match_method,
            "reason": r.reason,
            "cluster": cluster,
            "matched_product": matched_obj,
            "candidates": candidates_list
        }
        items_data.append(item_json)

        # -------------------------------------------------------------
        # HTML For Visual Card View
        # -------------------------------------------------------------
        # Brand & Size Badges
        brand_badge = f"<span class='chip chip-brand' title='Thương hiệu bóc tách'>🏷️ {escape(r.image.brand)}</span>" if r.image.brand else ""
        size_badge = f"<span class='chip chip-size' title='Quy cách đóng gói'>⚖️ {escape(r.image.packaging.raw)}</span>" if (r.image.packaging and r.image.packaging.raw) else ""
        pack_badge = f"<span class='chip chip-pack'>📁 {escape(pack_name)}</span>"

        # Right-side matching block
        if r.status == "AUTO_MATCHED" and r.candidate and r.candidate.product:
            p = r.candidate.product
            p_name = escape(p.product_name)
            p_barcode = escape(p.barcode or "Chưa có barcode")
            p_sku = escape(p.sku or "Chưa có SKU")
            p_price = f"{escape(p.selling_price)} DKK" if p.selling_price else ""
            p_unit = f"({escape(p.unit)})" if p.unit else ""
            method_label = {
                "asropa_ean_barcode": "⚡ Mã EAN-13 Asropa (Chuẩn 100%)",
                "exact_barcode": "📷 Quét Barcode trực tiếp từ ảnh",
                "exact_human_approved": "🛡️ Quyết định đã duyệt (Knowledge Base)",
                "high_similarity": "🎯 Tương đồng cao (>85%)",
                "brand_ingredient_match": "🏷️ Trùng Thương hiệu & Thành phần",
                "rule_engine": "🔍 Công cụ Khớp Nâng cao"
            }.get(r.match_method, r.match_method)

            right_col = f"""
            <div class="match-card-success">
              <div class="match-header">
                <span class="badge-success-glow">✓ ĐÃ KHỚP TỰ ĐỘNG 100%</span>
                <span class="match-method-pill">{escape(method_label)}</span>
              </div>
              <div class="pos-product-title">{p_name}</div>
              <div class="key-values-grid">
                <div class="kv-box">
                  <span class="kv-label">MÃ VẠCH (BARCODE)</span>
                  <div class="kv-val-copy" onclick="copyText('{p_barcode}', 'Đã copy Barcode: {p_barcode}')" title="Bấm để copy Barcode">
                    <span class="barcode-text">{p_barcode}</span>
                    <button class="btn-copy-mini">📋 Copy</button>
                  </div>
                </div>
                <div class="kv-box">
                  <span class="kv-label">MÃ SKU</span>
                  <div class="kv-val-copy" onclick="copyText('{p_sku}', 'Đã copy SKU: {p_sku}')" title="Bấm để copy SKU">
                    <span class="sku-text">{p_sku}</span>
                    <button class="btn-copy-mini">📋 Copy</button>
                  </div>
                </div>
                <div class="kv-box">
                  <span class="kv-label">GIÁ BÁN / ĐVT</span>
                  <div class="kv-val-plain">{p_price} {p_unit}</div>
                </div>
                <div class="kv-box">
                  <span class="kv-label">FILE ẢNH ĐÍCH</span>
                  <div class="kv-val-plain destination-path">output/matched-images/{p_barcode}.jpg</div>
                </div>
              </div>
              <div class="match-reason-bar">
                <span class="reason-icon">💡</span>
                <span class="reason-text">{escape(r.reason)}</span>
              </div>
            </div>
            """
        elif r.status == "NEED_REVIEW":
            candidates_cards = []
            for i, c in enumerate(r.top_candidates[:3], 1):
                c_name = escape(c.product.product_name)
                c_bc = escape(c.product.barcode or "Chưa có barcode")
                c_sku = escape(c.product.sku or "Chưa có SKU")
                c_price = f"{escape(c.product.selling_price)} DKK" if c.product.selling_price else ""
                c_score = int(round(c.score * 100))
                is_top1 = (i == 1)
                badge_cand = f"<span class='badge-rec'>Lựa chọn #{i} ({c_score}%)</span>" if is_top1 else f"<span class='badge-alt-cand'>Gợi ý #{i} ({c_score}%)</span>"
                candidates_cards.append(f"""
                <div class="cand-choice-box {'is-top-rec' if is_top1 else ''}" id="cand-box-{idx}-{i}">
                  <div class="cand-choice-header">
                    {badge_cand}
                    <button class="btn-choose" onclick="selectCandidate({idx}, '{escape(r.image.filename)}', '{c_bc}', '{c_sku}', '{escape(c.product.product_name)}', {i})">
                      ✓ Chọn phương án này
                    </button>
                  </div>
                  <div class="cand-choice-title">{c_name}</div>
                  <div class="cand-choice-meta">
                    <span onclick="copyText('{c_bc}', 'Đã copy Barcode: {c_bc}')" class="clickable-code">Barcode: <b>{c_bc}</b> 📋</span>
                    <span onclick="copyText('{c_sku}', 'Đã copy SKU: {c_sku}')" class="clickable-code">SKU: <b>{c_sku}</b> 📋</span>
                    {f'<span>Giá: {c_price}</span>' if c_price else ''}
                  </div>
                </div>
                """)
            cand_html_str = "".join(candidates_cards) if candidates_cards else "<div class='text-muted'>Không tìm thấy ứng viên tiềm năng</div>"

            right_col = f"""
            <div class="match-card-review">
              <div class="review-alert-banner">
                <span class="alert-icon">⚠️</span>
                <div class="alert-content">
                  <div class="alert-title">Cần Xác Nhận Đối Chiếu (Gợi ý Top 3)</div>
                  <div class="alert-reason">{escape(r.reason)}</div>
                </div>
              </div>
              <div class="candidates-options-list">
                {cand_html_str}
              </div>
              <div class="review-actions-footer">
                <button class="btn-mark-unmatched" onclick="markUnmatched({idx}, '{escape(r.image.filename)}')">
                  ✕ Đánh dấu không khớp / Hàng mới
                </button>
                <div id="selection-status-{idx}" class="selection-status-badge" style="display: none;"></div>
              </div>
            </div>
            """
        else: # UNMATCHED or ERROR
            right_col = f"""
            <div class="match-card-unmatched">
              <div class="unmatched-banner">
                <span class="unmatched-icon">❌</span>
                <div class="unmatched-title">Chưa Có Trong Danh Mục POS</div>
                <div class="unmatched-desc">
                  Không tìm thấy sản phẩm tương đồng trong POS đạt ngưỡng tối thiểu (&ge; 60%).<br>
                  Có thể đây là sản phẩm mới nhập về hoặc chưa được khai báo mã vạch trên POS.
                </div>
                <div class="unmatched-action-hint">
                  👉 <b>Hành động đề xuất:</b> Tạo sản phẩm mới trên POS với tên chuẩn hóa <code>{escape(r.image.normalized_name)}</code>.
                </div>
              </div>
            </div>
            """

        card_html = f"""
        <div class="compare-card status-{status_class}" id="card-{idx}" data-idx="{idx}" data-status="{r.status}" data-cluster="{cluster}" data-pack="{pack_name}" data-conf="{conf_pct}" data-search="{search_str}">
          <div class="card-header">
            <div class="header-left">
              <span class="item-index">#{idx}</span>
              <span class="badge status-badge-{status_class}">{status_label}</span>
              {pack_badge}
              <span class="cluster-tag cluster-{cluster}">{cluster_label}</span>
            </div>
            <div class="header-right">
              <div class="conf-meter" title="Độ tin cậy thuật toán: {conf_pct}%">
                <span class="conf-meter-val" style="color: {conf_color};">{conf_pct}%</span>
                <div class="conf-meter-bar"><div style="width: {conf_pct}%; background: {conf_color};"></div></div>
              </div>
              <button class="btn-inspect" onclick="openModalByIdx({idx})" title="Phóng to & Đối chiếu chi tiết">
                🔍 So sánh chi tiết
              </button>
            </div>
          </div>
          <div class="card-body">
            <div class="card-left-col">
              <div class="img-container" onclick="openModalByIdx({idx})">
                <img src="{escape(relative)}" loading="lazy" alt="Sản phẩm">
                <div class="img-zoom-hint">🔍 Phóng to</div>
              </div>
              <div class="img-meta-box">
                <div class="meta-filename" title="{escape(r.image.filename)}">{escape(r.image.filename)}</div>
                <div class="meta-normalized">
                  <span class="meta-label">Tên chuẩn hóa:</span>
                  <span class="meta-text">{escape(r.image.normalized_name)}</span>
                </div>
                <div class="chips-container">
                  {brand_badge}
                  {size_badge}
                </div>
              </div>
            </div>
            <div class="card-right-col">
              {right_col}
            </div>
          </div>
        </div>
        """
        cards_html.append(card_html)

        # -------------------------------------------------------------
        # HTML For Compact Table View
        # -------------------------------------------------------------
        cand_summary_list = []
        if r.status == "AUTO_MATCHED" and r.candidate and r.candidate.product:
            p = r.candidate.product
            cand_summary_list.append(f"""
            <div class="table-cand-matched">
              <div class="t-name"><b>{escape(p.product_name)}</b></div>
              <div class="t-meta">Barcode: <b class="clickable-code" onclick="copyText('{escape(p.barcode or '')}', 'Đã copy')">{escape(p.barcode or '')}</b> | SKU: {escape(p.sku or '')}</div>
            </div>
            """)
        else:
            for i, c in enumerate(r.top_candidates[:2], 1):
                cand_summary_list.append(f"""
                <div class="table-cand-item">
                  <span class="t-badge">#{i} ({int(round(c.score*100))}%)</span>
                  <span class="t-name">{escape(c.product.product_name)}</span>
                  <span class="t-meta">(BC: {escape(c.product.barcode or '')})</span>
                </div>
                """)
        cand_table_block = "".join(cand_summary_list) if cand_summary_list else "<span class='text-muted'>Không có</span>"

        row_html = f"""
        <tr class="data-row status-{status_class}" id="row-{idx}" data-idx="{idx}" data-status="{r.status}" data-cluster="{cluster}" data-pack="{pack_name}" data-conf="{conf_pct}" data-search="{search_str}">
          <td class="col-num">{idx}</td>
          <td class="col-img">
            <div class="table-img-wrap" onclick="openModalByIdx({idx})">
              <img src="{escape(relative)}" loading="lazy" alt="Thumb">
            </div>
          </td>
          <td class="col-info">
            <div class="t-filename">{escape(r.image.filename)}</div>
            <div class="t-norm">{escape(r.image.normalized_name)}</div>
            <div class="t-chips">{brand_badge} {size_badge} <span class="chip-pack-mini">{escape(pack_name)}</span></div>
          </td>
          <td class="col-status">
            <span class="badge status-badge-{status_class}">{status_label}</span>
            <div class="conf-meter-bar-mini" title="{conf_pct}%">
              <div style="width: {conf_pct}%; background: {conf_color};"></div>
            </div>
            <div class="conf-val-mini" style="color: {conf_color};">{conf_pct}% tin cậy</div>
          </td>
          <td class="col-candidates">{cand_table_block}</td>
          <td class="col-reason"><div class="reason-cell">{escape(r.reason)}</div></td>
          <td class="col-actions">
            <button class="btn-inspect-mini" onclick="openModalByIdx({idx})">🔍 Đối chiếu</button>
          </td>
        </tr>
        """
        rows_html.append(row_html)

    cards_all_html = "\n".join(cards_html)
    rows_all_html = "\n".join(rows_html)
    json_data_str = json.dumps(items_data, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hệ Thống Đối Soát Trực Quan & Chuẩn Hóa Dữ Liệu Sản Phẩm POS / Shopify</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root {{
  --bg-main: #0A0E17;
  --bg-card: rgba(17, 24, 39, 0.88);
  --bg-card-hover: rgba(28, 38, 59, 0.95);
  --bg-surface: #131B2E;
  --border-color: rgba(255, 255, 255, 0.08);
  --border-focus: #3B82F6;
  --text-primary: #F3F4F6;
  --text-secondary: #9CA3AF;
  --text-muted: #6B7280;
  --accent-blue: #3B82F6;
  --accent-cyan: #06B6D4;
  --accent-emerald: #10B981;
  --accent-amber: #F59E0B;
  --accent-rose: #EF4444;
  --accent-purple: #8B5CF6;
  --glass-border: rgba(255, 255, 255, 0.1);
}}

* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  background-color: var(--bg-main);
  color: var(--text-primary);
  line-height: 1.5;
  padding: 24px 32px;
  background-image: 
    radial-gradient(at 0% 0%, rgba(59, 130, 246, 0.10) 0px, transparent 45%),
    radial-gradient(at 100% 100%, rgba(16, 185, 129, 0.08) 0px, transparent 45%),
    radial-gradient(at 50% 50%, rgba(6, 182, 212, 0.04) 0px, transparent 60%);
  min-height: 100vh;
}}

.container {{ max-width: 1680px; margin: 0 auto; }}

/* HEADER */
header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  flex-wrap: wrap;
  gap: 16px;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 20px;
}}
.brand h1 {{
  font-size: 26px;
  font-weight: 800;
  background: linear-gradient(135deg, #FFFFFF 0%, #93C5FD 50%, #34D399 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  letter-spacing: -0.5px;
}}
.brand p {{ color: var(--text-secondary); font-size: 13.5px; margin-top: 4px; }}

.header-meta {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
.badge-client {{
  background: rgba(59, 130, 246, 0.15);
  color: #60A5FA;
  border: 1px solid rgba(59, 130, 246, 0.3);
  padding: 6px 14px;
  border-radius: 9999px;
  font-size: 12.5px;
  font-weight: 600;
}}

/* KPI CARDS */
.metrics-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}}
.metric-card {{
  background: var(--bg-card);
  backdrop-filter: blur(12px);
  border: 1px solid var(--border-color);
  border-radius: 14px;
  padding: 18px 22px;
  position: relative;
  overflow: hidden;
  transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s;
}}
.metric-card:hover {{
  transform: translateY(-2px);
  border-color: rgba(255, 255, 255, 0.18);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
}}
.metric-title {{ font-size: 12px; color: var(--text-secondary); font-weight: 700; text-transform: uppercase; letter-spacing: 0.6px; }}
.metric-val {{ font-size: 30px; font-weight: 800; margin: 6px 0; color: #FFF; display: flex; align-items: baseline; gap: 8px; }}
.metric-sub {{ font-size: 12.5px; color: var(--text-muted); }}

.card-total {{ border-left: 4px solid var(--accent-blue); }}
.card-auto {{ border-left: 4px solid var(--accent-emerald); }}
.card-review {{ border-left: 4px solid var(--accent-amber); }}
.card-unmatched {{ border-left: 4px solid var(--accent-rose); }}

/* INTERACTIVE WORKBENCH BAR */
.review-workbench-bar {{
  background: linear-gradient(135deg, rgba(30, 41, 59, 0.9) 0%, rgba(15, 23, 42, 0.95) 100%);
  border: 1px solid rgba(59, 130, 246, 0.25);
  border-radius: 14px;
  padding: 16px 24px;
  margin-bottom: 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
}}
.wb-left {{ display: flex; align-items: center; gap: 16px; }}
.wb-badge {{
  background: rgba(59, 130, 246, 0.2);
  color: #93C5FD;
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 700;
}}
.wb-info {{ font-size: 13.5px; color: var(--text-secondary); }}
.wb-info b {{ color: #FFF; }}
.wb-actions {{ display: flex; gap: 10px; align-items: center; }}
.btn-export-json {{
  background: linear-gradient(135deg, #10B981 0%, #059669 100%);
  color: #FFF;
  border: none;
  padding: 9px 18px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: opacity 0.2s, transform 0.1s;
}}
.btn-export-json:hover {{ opacity: 0.92; transform: scale(1.02); }}
.btn-copy-kb {{
  background: rgba(255, 255, 255, 0.08);
  color: #E2E8F0;
  border: 1px solid var(--glass-border);
  padding: 9px 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}}
.btn-copy-kb:hover {{ background: rgba(255, 255, 255, 0.15); color: #FFF; }}

/* CONTROLS & TOOLBAR */
.controls-container {{
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 14px;
  padding: 16px 20px;
  margin-bottom: 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}}
.controls-row-top {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 14px;
}}
.filter-tabs {{ display: flex; gap: 8px; flex-wrap: wrap; }}
.tab-btn {{
  background: transparent;
  border: 1px solid transparent;
  color: var(--text-secondary);
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}}
.tab-btn:hover {{ color: #FFF; background: rgba(255, 255, 255, 0.05); }}
.tab-btn.active {{
  background: rgba(59, 130, 246, 0.2);
  color: #93C5FD;
  border-color: rgba(59, 130, 246, 0.4);
}}

.view-mode-toggle {{
  display: flex;
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 3px;
}}
.toggle-btn {{
  background: transparent;
  border: none;
  color: var(--text-secondary);
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
}}
.toggle-btn.active {{
  background: var(--accent-blue);
  color: #FFF;
}}

.controls-row-bottom {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  padding-top: 12px;
}}
.sub-filters {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
.sub-filter-chip {{
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: var(--text-secondary);
  padding: 5px 12px;
  border-radius: 9999px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}}
.sub-filter-chip:hover {{ background: rgba(255, 255, 255, 0.1); color: #FFF; }}
.sub-filter-chip.active {{
  background: rgba(6, 182, 212, 0.2);
  color: #67E8F9;
  border-color: rgba(6, 182, 212, 0.4);
}}

.search-and-sort {{ display: flex; gap: 12px; align-items: center; }}
.search-input-wrap {{ position: relative; width: 340px; max-width: 100%; }}
.search-input {{
  width: 100%;
  background: rgba(0, 0, 0, 0.4);
  border: 1px solid var(--border-color);
  color: #FFF;
  padding: 8px 14px 8px 36px;
  border-radius: 8px;
  font-size: 13.5px;
  outline: none;
}}
.search-input:focus {{
  border-color: var(--accent-blue);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
}}
.search-icon {{
  position: absolute;
  left: 11px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-muted);
  font-size: 14px;
}}
.sort-select {{
  background: rgba(0, 0, 0, 0.4);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
  outline: none;
  cursor: pointer;
}}

/* VISUAL CARDS GRID VIEW */
.cards-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(620px, 1fr));
  gap: 20px;
  margin-bottom: 40px;
}}

.compare-card {{
  background: var(--bg-card);
  backdrop-filter: blur(14px);
  border: 1px solid var(--border-color);
  border-radius: 16px;
  padding: 18px;
  position: relative;
  display: flex;
  flex-direction: column;
  transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s;
}}
.compare-card:hover {{
  border-color: rgba(255, 255, 255, 0.2);
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.4);
}}
.compare-card.status-auto-matched {{ border-left: 4px solid var(--accent-emerald); }}
.compare-card.status-need-review {{ border-left: 4px solid var(--accent-amber); }}
.compare-card.status-unmatched {{ border-left: 4px solid var(--accent-rose); }}
.compare-card.is-human-approved {{
  border-left: 4px solid #10B981 !important;
  background: rgba(16, 185, 129, 0.05);
  box-shadow: 0 0 0 1px rgba(16, 185, 129, 0.3);
}}

.card-header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  padding-bottom: 12px;
  margin-bottom: 14px;
}}
.header-left {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
.item-index {{ font-weight: 800; color: var(--text-muted); font-size: 13px; }}
.badge {{
  display: inline-block;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 0.3px;
}}
.status-badge-auto-matched {{ background: rgba(16, 185, 129, 0.15); color: #34D399; border: 1px solid rgba(16, 185, 129, 0.3); }}
.status-badge-need-review {{ background: rgba(245, 158, 11, 0.15); color: #FBBF24; border: 1px solid rgba(245, 158, 11, 0.3); }}
.status-badge-unmatched {{ background: rgba(239, 68, 68, 0.15); color: #F87171; border: 1px solid rgba(239, 68, 68, 0.3); }}

.chip {{
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}}
.chip-pack {{ background: rgba(255, 255, 255, 0.06); color: var(--text-secondary); }}
.chip-brand {{ background: rgba(139, 92, 246, 0.15); color: #C4B5FD; border: 1px solid rgba(139, 92, 246, 0.3); }}
.chip-size {{ background: rgba(6, 182, 212, 0.15); color: #67E8F9; border: 1px solid rgba(6, 182, 212, 0.3); }}

.cluster-tag {{ font-size: 10.5px; padding: 2px 7px; border-radius: 4px; font-weight: 600; }}
.cluster-dup_barcode {{ background: rgba(245, 158, 11, 0.1); color: #FCD34D; }}
.cluster-ean13 {{ background: rgba(16, 185, 129, 0.1); color: #6EE7B7; }}
.cluster-size_diff {{ background: rgba(236, 72, 153, 0.1); color: #F472B6; }}
.cluster-high_score {{ background: rgba(59, 130, 246, 0.1); color: #93C5FD; }}
.cluster-unmatched {{ background: rgba(239, 68, 68, 0.1); color: #FCA5A5; }}
.cluster-standard {{ background: rgba(255, 255, 255, 0.05); color: var(--text-muted); }}

.header-right {{ display: flex; align-items: center; gap: 12px; }}
.conf-meter {{ display: flex; align-items: center; gap: 6px; }}
.conf-meter-val {{ font-size: 12px; font-weight: 800; font-family: 'JetBrains Mono', monospace; }}
.conf-meter-bar {{ width: 50px; height: 5px; background: rgba(255, 255, 255, 0.08); border-radius: 3px; overflow: hidden; }}
.conf-meter-bar div {{ height: 100%; border-radius: 3px; }}

.btn-inspect {{
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid var(--glass-border);
  color: var(--text-secondary);
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 11.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}}
.btn-inspect:hover {{ background: rgba(59, 130, 246, 0.2); color: #93C5FD; border-color: rgba(59, 130, 246, 0.4); }}

/* CARD BODY (SPLIT TWO-COLUMNS) */
.card-body {{
  display: grid;
  grid-template-columns: 180px 1fr;
  gap: 16px;
  flex: 1;
}}
@media (max-width: 680px) {{
  .card-body {{ grid-template-columns: 1fr; }}
  .cards-grid {{ grid-template-columns: 1fr; }}
}}

.card-left-col {{
  display: flex;
  flex-direction: column;
  gap: 10px;
}}
.img-container {{
  width: 100%;
  aspect-ratio: 1/1;
  background: #FFF;
  border-radius: 10px;
  overflow: hidden;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border: 1px solid rgba(255, 255, 255, 0.1);
  transition: transform 0.2s, box-shadow 0.2s;
}}
.img-container:hover {{ transform: scale(1.02); box-shadow: 0 6px 18px rgba(0, 0, 0, 0.4); }}
.img-container img {{ max-width: 90%; max-height: 90%; object-fit: contain; }}
.img-zoom-hint {{
  position: absolute;
  bottom: 6px;
  right: 6px;
  background: rgba(0, 0, 0, 0.7);
  color: #FFF;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  pointer-events: none;
}}

.img-meta-box {{ display: flex; flex-direction: column; gap: 6px; }}
.meta-filename {{
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-secondary);
  word-break: break-all;
  line-height: 1.3;
}}
.meta-normalized {{ font-size: 12px; }}
.meta-label {{ color: var(--text-muted); font-size: 11px; display: block; }}
.meta-text {{ color: #93C5FD; font-weight: 600; }}
.chips-container {{ display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }}

.card-right-col {{
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}}

/* AUTO MATCHED CARD CONTENT */
.match-card-success {{
  background: rgba(16, 185, 129, 0.06);
  border: 1px solid rgba(16, 185, 129, 0.2);
  border-radius: 10px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
}}
.match-header {{ display: flex; justify-content: space-between; align-items: center; }}
.badge-success-glow {{
  font-size: 11.5px;
  font-weight: 800;
  color: #34D399;
  letter-spacing: 0.3px;
}}
.match-method-pill {{
  font-size: 11px;
  background: rgba(255, 255, 255, 0.08);
  color: #D1D5DB;
  padding: 2px 8px;
  border-radius: 4px;
}}
.pos-product-title {{
  font-size: 14.5px;
  font-weight: 700;
  color: #FFF;
  line-height: 1.4;
}}

.key-values-grid {{
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  background: rgba(0, 0, 0, 0.25);
  padding: 10px;
  border-radius: 8px;
}}
.kv-box {{ display: flex; flex-direction: column; gap: 2px; }}
.kv-label {{ font-size: 10px; color: var(--text-muted); font-weight: 700; letter-spacing: 0.4px; }}
.kv-val-copy {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: rgba(255, 255, 255, 0.05);
  padding: 3px 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
}}
.kv-val-copy:hover {{ background: rgba(59, 130, 246, 0.2); }}
.barcode-text {{ font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 700; color: #FBBF24; }}
.sku-text {{ font-family: 'JetBrains Mono', monospace; font-size: 11.5px; font-weight: 600; color: #E2E8F0; }}
.btn-copy-mini {{
  background: transparent;
  border: none;
  color: var(--text-muted);
  font-size: 10px;
  cursor: pointer;
}}
.kv-val-plain {{ font-size: 12px; color: #FFF; font-weight: 600; }}
.destination-path {{ font-family: 'JetBrains Mono', monospace; font-size: 10.5px; color: #6EE7B7; word-break: break-all; }}

.match-reason-bar {{
  display: flex;
  gap: 6px;
  align-items: flex-start;
  font-size: 11.5px;
  color: var(--text-secondary);
  background: rgba(0, 0, 0, 0.2);
  padding: 6px 8px;
  border-radius: 6px;
}}

/* NEED REVIEW CARD CONTENT */
.match-card-review {{
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
}}
.review-alert-banner {{
  display: flex;
  gap: 10px;
  align-items: flex-start;
  background: rgba(245, 158, 11, 0.1);
  border: 1px solid rgba(245, 158, 11, 0.25);
  padding: 8px 12px;
  border-radius: 8px;
}}
.alert-icon {{ font-size: 16px; line-height: 1; }}
.alert-title {{ font-size: 12px; font-weight: 700; color: #FBBF24; }}
.alert-reason {{ font-size: 11.5px; color: var(--text-secondary); margin-top: 2px; }}

.candidates-options-list {{ display: flex; flex-direction: column; gap: 8px; }}
.cand-choice-box {{
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  padding: 10px 12px;
  transition: all 0.15s;
}}
.cand-choice-box.is-top-rec {{
  border-color: rgba(59, 130, 246, 0.35);
  background: rgba(30, 58, 138, 0.15);
}}
.cand-choice-box.selected-by-user {{
  border-color: #10B981 !important;
  background: rgba(16, 185, 129, 0.15) !important;
}}
.cand-choice-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }}
.badge-rec {{ font-size: 10.5px; font-weight: 700; color: #60A5FA; background: rgba(59, 130, 246, 0.18); padding: 2px 6px; border-radius: 4px; }}
.badge-alt-cand {{ font-size: 10.5px; font-weight: 600; color: var(--text-secondary); background: rgba(255, 255, 255, 0.06); padding: 2px 6px; border-radius: 4px; }}
.btn-choose {{
  background: rgba(59, 130, 246, 0.2);
  color: #93C5FD;
  border: 1px solid rgba(59, 130, 246, 0.4);
  padding: 3px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.15s;
}}
.btn-choose:hover {{
  background: #3B82F6;
  color: #FFF;
}}
.cand-choice-title {{ font-size: 13px; font-weight: 600; color: #FFF; }}
.cand-choice-meta {{
  font-size: 11.5px;
  color: var(--text-secondary);
  display: flex;
  gap: 12px;
  margin-top: 4px;
  flex-wrap: wrap;
}}
.clickable-code {{
  cursor: pointer;
  padding: 1px 4px;
  border-radius: 4px;
  transition: background 0.15s;
}}
.clickable-code:hover {{ background: rgba(255, 255, 255, 0.1); color: #FFF; }}

.review-actions-footer {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 4px;
}}
.btn-mark-unmatched {{
  background: transparent;
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: #F87171;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}}
.btn-mark-unmatched:hover {{ background: rgba(239, 68, 68, 0.15); }}
.selection-status-badge {{
  font-size: 11px;
  font-weight: 700;
  color: #34D399;
  background: rgba(16, 185, 129, 0.15);
  padding: 2px 8px;
  border-radius: 4px;
}}

/* UNMATCHED CARD CONTENT */
.match-card-unmatched {{
  background: rgba(239, 68, 68, 0.05);
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: 10px;
  padding: 16px;
  height: 100%;
  display: flex;
  align-items: center;
}}
.unmatched-banner {{ display: flex; flex-direction: column; gap: 8px; }}
.unmatched-icon {{ font-size: 24px; }}
.unmatched-title {{ font-size: 14px; font-weight: 700; color: #F87171; }}
.unmatched-desc {{ font-size: 12.5px; color: var(--text-secondary); line-height: 1.4; }}
.unmatched-action-hint {{ font-size: 12px; color: #E2E8F0; background: rgba(0, 0, 0, 0.3); padding: 8px 10px; border-radius: 6px; }}
.unmatched-action-hint code {{ color: #93C5FD; font-family: 'JetBrains Mono', monospace; }}

/* COMPACT TABLE VIEW */
.table-view-container {{
  display: none;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
  margin-bottom: 40px;
}}
table {{ width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; }}
th {{
  background: rgba(15, 23, 42, 0.95);
  color: var(--text-secondary);
  padding: 12px 14px;
  font-weight: 700;
  border-bottom: 1px solid var(--border-color);
  text-transform: uppercase;
  font-size: 11px;
  letter-spacing: 0.5px;
}}
td {{
  padding: 12px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  vertical-align: top;
}}
tr.data-row:hover td {{ background: var(--bg-card-hover); }}

.col-num {{ color: var(--text-muted); width: 45px; font-weight: 600; text-align: center; }}
.col-img {{ width: 75px; text-align: center; }}
.table-img-wrap {{
  width: 56px;
  height: 56px;
  background: #FFF;
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border: 1px solid rgba(255, 255, 255, 0.1);
}}
.table-img-wrap img {{ max-width: 90%; max-height: 90%; object-fit: contain; }}

.col-info {{ width: 280px; }}
.t-filename {{ font-weight: 600; color: #FFF; font-size: 12.5px; font-family: 'JetBrains Mono', monospace; word-break: break-all; margin-bottom: 2px; }}
.t-norm {{ color: #93C5FD; font-size: 12px; }}
.t-chips {{ margin-top: 4px; display: flex; gap: 4px; flex-wrap: wrap; }}
.chip-pack-mini {{ background: rgba(255, 255, 255, 0.06); padding: 1px 5px; border-radius: 4px; font-size: 10px; color: var(--text-muted); }}

.col-status {{ width: 140px; }}
.conf-meter-bar-mini {{ width: 100%; height: 4px; background: rgba(255, 255, 255, 0.08); border-radius: 2px; overflow: hidden; margin: 4px 0; }}
.conf-meter-bar-mini div {{ height: 100%; }}
.conf-val-mini {{ font-size: 11px; font-weight: 700; }}

.col-candidates {{ min-width: 300px; }}
.table-cand-matched .t-name {{ color: #34D399; font-size: 13px; }}
.table-cand-matched .t-meta {{ color: var(--text-secondary); font-size: 11.5px; margin-top: 2px; }}
.table-cand-item {{ margin-bottom: 4px; font-size: 12px; }}
.t-badge {{ color: #60A5FA; font-weight: 700; font-size: 11px; }}
.t-meta {{ color: var(--text-muted); font-size: 11px; }}

.col-reason {{ width: 220px; }}
.reason-cell {{ font-size: 11.5px; color: var(--text-secondary); line-height: 1.4; }}
.col-actions {{ width: 90px; text-align: center; }}
.btn-inspect-mini {{
  background: rgba(59, 130, 246, 0.15);
  border: 1px solid rgba(59, 130, 246, 0.3);
  color: #93C5FD;
  padding: 5px 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}}

/* LIGHTBOX MODAL WITH FULL COMPARISON & INSPECTOR */
.modal-overlay {{
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.88);
  backdrop-filter: blur(10px);
  z-index: 1000;
  align-items: center;
  justify-content: center;
  padding: 24px;
}}
.modal-container {{
  background: #111827;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 20px;
  width: 100%;
  max-width: 1100px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 25px 60px rgba(0, 0, 0, 0.6);
}}
.modal-header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background: rgba(15, 23, 42, 0.8);
  border-bottom: 1px solid var(--border-color);
}}
.modal-header-left {{ display: flex; align-items: center; gap: 12px; }}
.modal-item-nav {{ display: flex; gap: 6px; align-items: center; }}
.btn-nav {{
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid var(--glass-border);
  color: #FFF;
  padding: 5px 12px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  font-weight: 600;
}}
.btn-nav:hover {{ background: rgba(59, 130, 246, 0.3); }}
.modal-close-btn {{
  background: transparent;
  border: none;
  color: var(--text-secondary);
  font-size: 20px;
  cursor: pointer;
}}

.modal-body {{
  display: grid;
  grid-template-columns: 420px 1fr;
  padding: 24px;
  gap: 24px;
  overflow-y: auto;
}}
@media (max-width: 860px) {{
  .modal-body {{ grid-template-columns: 1fr; }}
}}
.modal-left {{
  display: flex;
  flex-direction: column;
  gap: 16px;
}}
.modal-big-img-wrap {{
  width: 100%;
  height: 380px;
  background: #FFF;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  padding: 16px;
}}
.modal-big-img-wrap img {{
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  transition: transform 0.3s;
}}
.modal-right {{
  display: flex;
  flex-direction: column;
  gap: 16px;
}}

/* TOAST NOTIFICATION */
#toastNotification {{
  position: fixed;
  bottom: 30px;
  right: 30px;
  background: #10B981;
  color: #FFF;
  padding: 12px 20px;
  border-radius: 10px;
  font-weight: 700;
  font-size: 13.5px;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.4);
  display: none;
  z-index: 2000;
  animation: slideUp 0.2s ease-out;
}}
@keyframes slideUp {{
  from {{ transform: translateY(20px); opacity: 0; }}
  to {{ transform: translateY(0); opacity: 1; }}
}}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="brand">
      <h1>Hệ Thống Đối Soát Trực Quan Dữ Liệu Sản Phẩm & POS</h1>
      <p>Giao diện trực quan đối chiếu hình ảnh thực tế với mã Barcode & SKU danh mục POS / Shopify</p>
    </div>
    <div class="header-meta">
      <span class="badge-client">Dự án: Shopbox / POS Reconciliation</span>
      <span class="badge-client" style="background: rgba(16, 185, 129, 0.15); color: #34D399; border-color: rgba(16, 185, 129, 0.3);">Data Live: {total} Hình Ảnh</span>
    </div>
  </header>

  <!-- KPI CARDS -->
  <div class="metrics-grid">
    <div class="metric-card card-total">
      <div class="metric-title">Tổng số hình ảnh</div>
      <div class="metric-val">{total} <span style="font-size: 14px; color: var(--text-muted);">ảnh</span></div>
      <div class="metric-sub">Pack 1 & Pack 2 nhà cung cấp</div>
    </div>
    <div class="metric-card card-auto">
      <div class="metric-title">Khớp tự động (100% Sẵn sàng)</div>
      <div class="metric-val" style="color: var(--accent-emerald);">{counts["AUTO_MATCHED"]} <span style="font-size: 16px;">({auto_pct}%)</span></div>
      <div class="metric-sub">Đã xuất vào <code>output/matched-images/</code> ({unique_pos_matched} POS duy nhất)</div>
    </div>
    <div class="metric-card card-review">
      <div class="metric-title">Cần xác nhận (Gợi ý Top 3)</div>
      <div class="metric-val" style="color: var(--accent-amber);">{counts["NEED_REVIEW"]} <span style="font-size: 16px;">({review_pct}%)</span></div>
      <div class="metric-sub">Đã gợi ý sẵn 3 lựa chọn tối ưu</div>
    </div>
    <div class="metric-card card-unmatched">
      <div class="metric-title">Chưa có trong POS</div>
      <div class="metric-val" style="color: var(--accent-rose);">{counts["UNMATCHED"]} <span style="font-size: 16px;">({unmatched_pct}%)</span></div>
      <div class="metric-sub">Sản phẩm mới cần tạo mã trên POS</div>
    </div>
  </div>

  <!-- INTERACTIVE WORKBENCH BAR -->
  <div class="review-workbench-bar">
    <div class="wb-left">
      <span class="wb-badge">BÀN LÀM VIỆC DUYỆT TRỰC QUAN</span>
      <div class="wb-info">
        Tiến độ duyệt phiên làm việc: <b id="wbApprovedCount">0</b> / {counts["NEED_REVIEW"]} mục đã chọn
      </div>
    </div>
    <div class="wb-actions">
      <button class="btn-export-json" onclick="exportReviewedDecisions()">
        📥 Tải File Quyết Định (JSON)
      </button>
      <button class="btn-copy-kb" onclick="copyKnowledgeJson()">
        📋 Copy Dữ Liệu Quyết Định
      </button>
    </div>
  </div>

  <!-- CONTROLS & TOOLBAR -->
  <div class="controls-container">
    <div class="controls-row-top">
      <div class="filter-tabs">
        <button class="tab-btn active" onclick="setStatusFilter('ALL', this)">Tất cả ({total})</button>
        <button class="tab-btn" onclick="setStatusFilter('AUTO_MATCHED', this)">✅ Đã khớp 100% ({counts["AUTO_MATCHED"]})</button>
        <button class="tab-btn" onclick="setStatusFilter('NEED_REVIEW', this)">⚠️ Cần duyệt ({counts["NEED_REVIEW"]})</button>
        <button class="tab-btn" onclick="setStatusFilter('UNMATCHED', this)">❌ Chưa có trong POS ({counts["UNMATCHED"]})</button>
      </div>

      <div class="view-mode-toggle">
        <button id="btnViewCards" class="toggle-btn active" onclick="setViewMode('cards')">
          🎴 Thẻ Đối Soát Trực Quan
        </button>
        <button id="btnViewTable" class="toggle-btn" onclick="setViewMode('table')">
          📋 Bảng Tổng Hợp
        </button>
      </div>
    </div>

    <div class="controls-row-bottom">
      <div class="sub-filters">
        <span style="font-size: 12px; color: var(--text-muted); font-weight: 600;">Lọc nhóm:</span>
        <button class="sub-filter-chip active" onclick="setClusterFilter('ALL', this)">Tất cả</button>
        <button class="sub-filter-chip" onclick="setClusterFilter('dup_barcode', this)">🔁 Trùng tên POS</button>
        <button class="sub-filter-chip" onclick="setClusterFilter('high_score', this)">🎯 Tương đồng cao (&ge;75%)</button>
        <button class="sub-filter-chip" onclick="setClusterFilter('size_diff', this)">⚖️ Quy cách / Trọng lượng</button>
        <button class="sub-filter-chip" onclick="setClusterFilter('ean13', this)">⚡ Mã Asropa EAN-13</button>
        <button class="sub-filter-chip" onclick="setPackFilter('unique_pack1', this)">📁 Pack 1</button>
        <button class="sub-filter-chip" onclick="setPackFilter('unique_pack2', this)">📁 Pack 2</button>
      </div>

      <div class="search-and-sort">
        <div class="search-input-wrap">
          <span class="search-icon">🔍</span>
          <input type="text" id="searchInput" class="search-input" placeholder="Tìm tên file, barcode, SKU, tên POS..." oninput="handleSearch()">
        </div>
        <select id="sortSelect" class="sort-select" onchange="handleSort()">
          <option value="default">Sắp xếp: Thứ tự STT</option>
          <option value="conf_asc">Độ tin cậy: Thấp &rarr; Cao (Duyệt ca khó)</option>
          <option value="conf_desc">Độ tin cậy: Cao &rarr; Thấp</option>
          <option value="name_asc">Tên file A &rarr; Z</option>
        </select>
      </div>
    </div>
  </div>

  <!-- VIEW MODE 1: VISUAL CARDS GRID -->
  <div id="cardsView" class="cards-grid">
    {cards_all_html}
  </div>

  <!-- VIEW MODE 2: COMPACT TABLE -->
  <div id="tableView" class="table-view-container">
    <table>
      <thead>
        <tr>
          <th class="col-num">#</th>
          <th class="col-img">Ảnh</th>
          <th class="col-info">Thông Tin Ảnh & Gốc</th>
          <th class="col-status">Trạng Thái & Độ Khớp</th>
          <th class="col-candidates">Sản Phẩm POS Đối Ứng (Gợi Ý)</th>
          <th class="col-reason">Căn Cứ Đối Soát</th>
          <th class="col-actions">Thao Tác</th>
        </tr>
      </thead>
      <tbody id="tableBody">
        {rows_all_html}
      </tbody>
    </table>
  </div>
</div>

<!-- LIGHTBOX INSPECTION MODAL -->
<div id="inspectModal" class="modal-overlay" onclick="closeModal()">
  <div class="modal-container" onclick="event.stopPropagation()">
    <div class="modal-header">
      <div class="modal-header-left">
        <span id="modalIdxBadge" class="item-index">#1</span>
        <span id="modalStatusBadge" class="badge">TRẠNG THÁI</span>
        <span id="modalFilenameTitle" style="font-weight: 700; font-size: 14px; color: #FFF;">Filename</span>
      </div>
      <div class="modal-item-nav">
        <button class="btn-nav" onclick="navModal(-1)">◄ Trước (Phím &larr;)</button>
        <button class="btn-nav" onclick="navModal(1)">Tiếp theo (Phím &rarr;) ►</button>
        <button class="modal-close-btn" onclick="closeModal()">&times;</button>
      </div>
    </div>
    <div class="modal-body">
      <div class="modal-left">
        <div class="modal-big-img-wrap">
          <img id="modalImg" src="" alt="Zoom Image">
        </div>
        <div id="modalImgDetails" style="font-size: 12.5px; color: var(--text-secondary); background: rgba(0,0,0,0.3); padding: 12px; border-radius: 8px;">
          <!-- Injected by JS -->
        </div>
      </div>
      <div class="modal-right" id="modalRightPanel">
        <!-- Injected by JS -->
      </div>
    </div>
  </div>
</div>

<!-- TOAST -->
<div id="toastNotification">Đã sao chép!</div>

<!-- DATA STORE FOR JS WORKBENCH -->
<script id="reportData" type="application/json">
{json_data_str}
</script>

<script>
const DATA = JSON.parse(document.getElementById('reportData').textContent);
let currentStatus = 'ALL';
let currentCluster = 'ALL';
let currentPack = 'ALL';
let currentSearch = '';
let currentSort = 'default';
let currentModalIdx = 1;

// Load user review decisions from localStorage
let userDecisions = {{}};
try {{
  const saved = localStorage.getItem('shopify_review_decisions');
  if (saved) userDecisions = JSON.parse(saved);
}} catch (e) {{}}

function updateWorkbenchCounters() {{
  const count = Object.keys(userDecisions).length;
  const el = document.getElementById('wbApprovedCount');
  if (el) el.textContent = count;

  // Highlight previously selected cards
  for (const [filename, dec] of Object.entries(userDecisions)) {{
    const item = DATA.find(x => x.filename === filename);
    if (!item) continue;
    const card = document.getElementById(`card-${{item.id}}`);
    if (card) {{
      card.classList.add('is-human-approved');
      const statusBadge = document.getElementById(`selection-status-${{item.id}}`);
      if (statusBadge) {{
        statusBadge.style.display = 'inline-block';
        statusBadge.textContent = `✓ Đã chọn: ${{dec.barcode || dec.selection}}`;
      }}
    }}
  }}
}}

function setStatusFilter(status, btn) {{
  currentStatus = status;
  document.querySelectorAll('.filter-tabs .tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  applyFilters();
}}

function setClusterFilter(cluster, btn) {{
  currentCluster = cluster;
  currentPack = 'ALL';
  document.querySelectorAll('.sub-filters .sub-filter-chip').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  applyFilters();
}}

function setPackFilter(pack, btn) {{
  currentPack = pack;
  currentCluster = 'ALL';
  document.querySelectorAll('.sub-filters .sub-filter-chip').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  applyFilters();
}}

function handleSearch() {{
  currentSearch = document.getElementById('searchInput').value.toLowerCase().trim();
  applyFilters();
}}

function handleSort() {{
  currentSort = document.getElementById('sortSelect').value;
  sortDOM();
}}

function setViewMode(mode) {{
  const cards = document.getElementById('cardsView');
  const table = document.getElementById('tableView');
  const btnCards = document.getElementById('btnViewCards');
  const btnTable = document.getElementById('btnViewTable');

  if (mode === 'cards') {{
    cards.style.display = 'grid';
    table.style.display = 'none';
    btnCards.classList.add('active');
    btnTable.classList.remove('active');
  }} else {{
    cards.style.display = 'none';
    table.style.display = 'block';
    btnTable.classList.add('active');
    btnCards.classList.remove('active');
  }}
}}

function applyFilters() {{
  const cards = document.querySelectorAll('.compare-card');
  const rows = document.querySelectorAll('.data-row');

  function checkMatch(el) {{
    const st = el.getAttribute('data-status');
    const cl = el.getAttribute('data-cluster');
    const pk = el.getAttribute('data-pack');
    const sr = el.getAttribute('data-search');

    const matchStatus = (currentStatus === 'ALL' || st === currentStatus);
    const matchCluster = (currentCluster === 'ALL' || cl === currentCluster);
    const matchPack = (currentPack === 'ALL' || pk === currentPack);
    const matchSearch = (!currentSearch || sr.includes(currentSearch));

    return matchStatus && matchCluster && matchPack && matchSearch;
  }}

  cards.forEach(card => {{
    card.style.display = checkMatch(card) ? '' : 'none';
  }});

  rows.forEach(row => {{
    row.style.display = checkMatch(row) ? '' : 'none';
  }});
}}

function sortDOM() {{
  const cardsContainer = document.getElementById('cardsView');
  const cards = Array.from(cardsContainer.children);

  cards.sort((a, b) => {{
    const idxA = parseInt(a.getAttribute('data-idx'));
    const idxB = parseInt(b.getAttribute('data-idx'));
    const confA = parseInt(a.getAttribute('data-conf'));
    const confB = parseInt(b.getAttribute('data-conf'));
    const nameA = a.querySelector('.meta-filename')?.textContent || '';
    const nameB = b.querySelector('.meta-filename')?.textContent || '';

    if (currentSort === 'conf_asc') return confA - confB;
    if (currentSort === 'conf_desc') return confB - confA;
    if (currentSort === 'name_asc') return nameA.localeCompare(nameB);
    return idxA - idxB;
  }});

  cards.forEach(c => cardsContainer.appendChild(c));
}}

function copyText(text, toastMsg) {{
  navigator.clipboard.writeText(text).then(() => {{
    showToast(toastMsg || `Đã sao chép: ${{text}}`);
  }});
}}

function showToast(msg) {{
  const t = document.getElementById('toastNotification');
  t.textContent = msg;
  t.style.display = 'block';
  setTimeout(() => {{ t.style.display = 'none'; }}, 2500);
}}

function selectCandidate(itemIdx, filename, barcode, sku, productName, choiceIdx) {{
  userDecisions[filename] = {{
    barcode: barcode,
    sku: sku,
    product_name: productName,
    choice_index: choiceIdx,
    selection: `Candidate #${{choiceIdx}}`,
    verified_at: new Date().toISOString()
  }};
  try {{ localStorage.setItem('shopify_review_decisions', JSON.stringify(userDecisions)); }} catch (e) {{}}
  
  const card = document.getElementById(`card-${{itemIdx}}`);
  if (card) {{
    card.classList.add('is-human-approved');
    for (let i = 1; i <= 3; i++) {{
      const b = document.getElementById(`cand-box-${{itemIdx}}-${{i}}`);
      if (b) b.classList.remove('selected-by-user');
    }}
    const chosenBox = document.getElementById(`cand-box-${{itemIdx}}-${{choiceIdx}}`);
    if (chosenBox) chosenBox.classList.add('selected-by-user');

    const statusBadge = document.getElementById(`selection-status-${{itemIdx}}`);
    if (statusBadge) {{
      statusBadge.style.display = 'inline-block';
      statusBadge.textContent = `✓ Đã chọn Barcode: ${{barcode}}`;
    }}
  }}
  updateWorkbenchCounters();
  showToast(`Đã chọn Barcode: ${{barcode}} cho ${{filename}}`);
}}

function markUnmatched(itemIdx, filename) {{
  userDecisions[filename] = {{
    selection: "No Match",
    barcode: "",
    sku: "",
    product_name: "",
    verified_at: new Date().toISOString()
  }};
  try {{ localStorage.setItem('shopify_review_decisions', JSON.stringify(userDecisions)); }} catch (e) {{}}

  const card = document.getElementById(`card-${{itemIdx}}`);
  if (card) {{
    card.classList.add('is-human-approved');
    const statusBadge = document.getElementById(`selection-status-${{itemIdx}}`);
    if (statusBadge) {{
      statusBadge.style.display = 'inline-block';
      statusBadge.textContent = `✕ Đã đánh dấu: Không khớp`;
      statusBadge.style.background = 'rgba(239, 68, 68, 0.2)';
      statusBadge.style.color = '#FCA5A5';
    }}
  }}
  updateWorkbenchCounters();
  showToast(`Đã đánh dấu ${{filename}} là Hàng Mới / Không khớp`);
}}

function exportReviewedDecisions() {{
  if (Object.keys(userDecisions).length === 0) {{
    alert('Chưa có mục nào được duyệt trong phiên làm việc này. Hãy nhấp "✓ Chọn phương án này" ở các mục cần duyệt!');
    return;
  }}
  const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(userDecisions, null, 2));
  const downloadAnchor = document.createElement('a');
  downloadAnchor.setAttribute("href", dataStr);
  downloadAnchor.setAttribute("download", "reviewed_knowledge.json");
  document.body.appendChild(downloadAnchor);
  downloadAnchor.click();
  downloadAnchor.remove();
}}

function copyKnowledgeJson() {{
  const count = Object.keys(userDecisions).length;
  if (count === 0) {{
    alert('Chưa có quyết định duyệt nào.');
    return;
  }}
  navigator.clipboard.writeText(JSON.stringify(userDecisions, null, 2)).then(() => {{
    showToast(`Đã sao chép ${{count}} quyết định vào bộ nhớ tạm!`);
  }});
}}

// LIGHTBOX MODAL
function openModalByIdx(idx) {{
  currentModalIdx = idx;
  const item = DATA.find(x => x.id === idx);
  if (!item) return;

  document.getElementById('modalIdxBadge').textContent = `#${{item.id}}`;
  document.getElementById('modalFilenameTitle').textContent = item.filename;
  document.getElementById('modalImg').src = item.image_url;

  const stBadge = document.getElementById('modalStatusBadge');
  stBadge.textContent = item.status === 'AUTO_MATCHED' ? 'KHỚP TỰ ĐỘNG' : (item.status === 'NEED_REVIEW' ? 'CẦN DUYỆT' : 'CHƯA CÓ TRONG POS');
  stBadge.className = `badge status-badge-${{item.status.toLowerCase().replace('_', '-')}}`;

  document.getElementById('modalImgDetails').innerHTML = `
    <div><b>Tên gốc:</b> ${{item.filename}}</div>
    <div style="margin-top:4px;"><b>Tên chuẩn hóa:</b> <span style="color:#93C5FD;">${{item.normalized_name}}</span></div>
    <div style="margin-top:4px;"><b>Thương hiệu:</b> ${{item.brand || 'Chưa nhận diện'}}</div>
    <div style="margin-top:4px;"><b>Quy cách / Trọng lượng:</b> ${{item.packaging || 'N/A'}}</div>
    <div style="margin-top:4px;"><b>Thư mục nguồn:</b> ${{item.pack}} (${{item.source}})</div>
  `;

  let rightHtml = '';
  if (item.status === 'AUTO_MATCHED' && item.matched_product) {{
    const p = item.matched_product;
    rightHtml = `
      <div style="background:rgba(16,185,129,0.1); border:1px solid rgba(16,185,129,0.3); padding:16px; border-radius:12px;">
        <div style="font-size:12px; font-weight:800; color:#34D399; margin-bottom:6px;">✓ ĐÃ KHỚP TỰ ĐỘNG 100%</div>
        <div style="font-size:16px; font-weight:700; color:#FFF;">${{p.name}}</div>
        <div style="margin-top:10px; display:grid; grid-template-columns:1fr 1fr; gap:8px;">
          <div style="background:rgba(0,0,0,0.3); padding:8px; border-radius:6px;">
            <div style="font-size:10px; color:#9CA3AF;">BARCODE</div>
            <div style="font-size:13px; font-weight:700; color:#FBBF24;">${{p.barcode}}</div>
          </div>
          <div style="background:rgba(0,0,0,0.3); padding:8px; border-radius:6px;">
            <div style="font-size:10px; color:#9CA3AF;">SKU</div>
            <div style="font-size:13px; font-weight:700; color:#FFF;">${{p.sku}}</div>
          </div>
        </div>
        <div style="margin-top:12px; font-size:12px; color:#D1D5DB;"><b>Căn cứ khớp:</b> ${{item.reason}}</div>
      </div>
    `;
  }} else if (item.status === 'NEED_REVIEW') {{
    const candBlocks = item.candidates.map(c => `
      <div style="background:rgba(0,0,0,0.35); border:1px solid rgba(255,255,255,0.08); padding:12px; border-radius:10px; margin-bottom:8px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <span style="font-size:11px; font-weight:700; color:#60A5FA;">Gợi ý #${{c.index}} (${{c.score}}% tương đồng)</span>
          <button class="btn-choose" onclick="selectCandidate(${{item.id}}, '${{item.filename}}', '${{c.barcode}}', '${{c.sku}}', '${{c.name.replace(/'/g, "\\\\\\'")}}', ${{c.index}})">
            ✓ Chọn phương án này
          </button>
        </div>
        <div style="font-size:13.5px; font-weight:700; color:#FFF; margin-top:4px;">${{c.name}}</div>
        <div style="font-size:12px; color:#9CA3AF; margin-top:4px;">
          Barcode: <b>${{c.barcode}}</b> | SKU: ${{c.sku}} ${{c.price ? '| Giá: ' + c.price + ' DKK' : ''}}
        </div>
      </div>
    `).join('');

    rightHtml = `
      <div style="background:rgba(245,158,11,0.08); border:1px solid rgba(245,158,11,0.25); padding:14px; border-radius:12px;">
        <div style="font-size:12px; font-weight:700; color:#FBBF24;">⚠️ CẦN XÁC NHẬN - CÁC PHƯƠNG ÁN GỢI Ý</div>
        <div style="font-size:12px; color:#D1D5DB; margin-top:4px; margin-bottom:12px;">${{item.reason}}</div>
        <div>${{candBlocks}}</div>
      </div>
    `;
  }} else {{
    rightHtml = `
      <div style="background:rgba(239,68,68,0.08); border:1px solid rgba(239,68,68,0.25); padding:16px; border-radius:12px;">
        <div style="font-size:14px; font-weight:700; color:#F87171;">❌ CHƯA CÓ TRONG DANH MỤC POS</div>
        <div style="font-size:12.5px; color:#D1D5DB; margin-top:6px;">Không tìm thấy mã sản phẩm nào trong POS đạt ngưỡng tương đồng.</div>
      </div>
    `;
  }}

  document.getElementById('modalRightPanel').innerHTML = rightHtml;
  document.getElementById('inspectModal').style.display = 'flex';
}}

function closeModal() {{
  document.getElementById('inspectModal').style.display = 'none';
}}

function navModal(delta) {{
  let newIdx = currentModalIdx + delta;
  if (newIdx < 1) newIdx = DATA.length;
  if (newIdx > DATA.length) newIdx = 1;
  openModalByIdx(newIdx);
}}

// Keyboard Navigation
document.addEventListener('keydown', (e) => {{
  const modal = document.getElementById('inspectModal');
  if (modal.style.display === 'flex') {{
    if (e.key === 'Escape') closeModal();
    if (e.key === 'ArrowLeft') navModal(-1);
    if (e.key === 'ArrowRight') navModal(1);
    if (e.key === '1' || e.key === '2' || e.key === '3') {{
      const item = DATA.find(x => x.id === currentModalIdx);
      if (item && item.candidates) {{
        const cIdx = parseInt(e.key);
        const cand = item.candidates.find(x => x.index === cIdx);
        if (cand) selectCandidate(item.id, item.filename, cand.barcode, cand.sku, cand.name, cIdx);
      }}
    }}
  }}
}});

// Initialize
updateWorkbenchCounters();
</script>
</body>
</html>
"""
    (output / "review_report.html").write_text(html, encoding="utf-8")
