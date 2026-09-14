from __future__ import annotations

from html import escape
import json
from pathlib import Path

from ..models import MatchResult


def _relative_image_url(result: MatchResult, output: Path) -> str:
    try:
        return "../" + str(result.image.path.relative_to(output.parent)).replace("\\", "/")
    except Exception:
        return str(result.image.path).replace("\\", "/")


def _item(result: MatchResult, index: int, output: Path) -> dict:
    matched = None
    if result.candidate:
        product = result.candidate.product
        matched = {
            "name": product.product_name,
            "product_id": product.product_id,
            "sku": product.sku,
            "barcode": product.barcode or "",
        }

    candidates = []
    for candidate_index, candidate in enumerate(result.top_candidates[:3], 1):
        product = candidate.product
        candidates.append({
            "index": candidate_index,
            "name": product.product_name,
            "product_id": product.product_id,
            "sku": product.sku,
            "barcode": product.barcode or "",
            "evidence": candidate.evidence,
        })

    return {
        "id": index,
        "filename": result.image.filename,
        "image_url": _relative_image_url(result, output),
        "source": result.image.source or "",
        "capture_id": result.image.capture_id or "",
        "side": result.image.image_side or "",
        "normalized_name": result.image.normalized_name,
        "status": result.status,
        "match_method": result.match_method,
        "reason": result.reason,
        "evidence": result.evidence,
        "matched": matched,
        "candidates": candidates,
    }


def write_html(results: list[MatchResult], output: Path) -> None:
    """Write a lightweight deterministic-evidence review report.

    The report intentionally avoids probability/similarity language. It embeds source
    data once and renders only the current page in the browser, which keeps 1000+ image
    reviews responsive instead of duplicating every item into multiple DOM views.
    """
    output.mkdir(parents=True, exist_ok=True)
    statuses = ["AUTO_MATCHED", "NEED_REVIEW", "UNMATCHED", "ERROR"]
    counts = {status: sum(result.status == status for result in results) for status in statuses}
    items = [_item(result, index, output) for index, result in enumerate(results, 1)]
    payload = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")

    html = f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Deterministic Product Reconciliation</title>
<style>
:root {{ color-scheme: dark; --bg:#0b1220; --panel:#111b2e; --line:#26344d; --text:#edf2f7; --muted:#9fb0c6; --ok:#34d399; --warn:#fbbf24; --bad:#fb7185; --blue:#60a5fa; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif; background:var(--bg); color:var(--text); }}
main {{ max-width:1500px; margin:auto; padding:24px; }}
h1 {{ margin:0 0 6px; font-size:24px; }}
.sub {{ color:var(--muted); margin-bottom:20px; }}
.metrics {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:12px; margin-bottom:18px; }}
.metric {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:14px; }}
.metric b {{ display:block; font-size:24px; margin-top:4px; }}
.controls {{ display:flex; flex-wrap:wrap; gap:10px; align-items:center; background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px; margin-bottom:14px; }}
input,select,button {{ background:#0d1728; color:var(--text); border:1px solid var(--line); border-radius:7px; padding:8px 10px; }}
input {{ min-width:300px; flex:1; }}
button {{ cursor:pointer; }}
button:hover {{ border-color:var(--blue); }}
.table-wrap {{ overflow:auto; border:1px solid var(--line); border-radius:10px; }}
table {{ width:100%; border-collapse:collapse; background:var(--panel); min-width:1100px; }}
th,td {{ text-align:left; vertical-align:top; padding:10px; border-bottom:1px solid var(--line); }}
th {{ position:sticky; top:0; background:#0e192a; z-index:1; color:#c8d6e8; }}
.thumb {{ width:72px; height:72px; object-fit:contain; background:white; border-radius:7px; }}
.status {{ white-space:nowrap; font-weight:700; }}
.auto {{ color:var(--ok); }} .review {{ color:var(--warn); }} .unmatched,.error {{ color:var(--bad); }}
.code {{ font-family:ui-monospace,SFMono-Regular,Consolas,monospace; font-size:12px; }}
.muted {{ color:var(--muted); }}
.reason {{ max-width:280px; }}
.candidate {{ padding:7px; margin:0 0 6px; border:1px solid var(--line); border-radius:7px; background:#0d1728; }}
.candidate button {{ margin-top:5px; font-size:12px; }}
.pager {{ display:flex; gap:8px; align-items:center; justify-content:flex-end; margin-top:12px; }}
.decision {{ color:var(--ok); font-size:12px; margin-top:5px; }}
.notice {{ border-left:3px solid var(--blue); padding:9px 12px; background:#0e192a; color:#c8d6e8; margin-bottom:14px; }}
@media(max-width:700px) {{ main {{ padding:12px; }} input {{ min-width:100%; }} }}
</style>
</head>
<body>
<main>
<h1>Đối soát sản phẩm bằng bằng chứng định danh</h1>
<div class="sub">Barcode / GTIN, human approval, exact canonical identity và OCR deterministic. Báo cáo này không dùng similarity score để chứng minh SKU identity.</div>
<div class="notice">AUTO_MATCHED nghĩa là pipeline có bằng chứng deterministic đủ mạnh theo policy hiện tại; đây không phải tuyên bố accuracy đã được đo bằng gold dataset.</div>
<div class="metrics">
  <div class="metric">Tổng ảnh<b>{len(results)}</b></div>
  <div class="metric">Đã khớp deterministic<b style="color:var(--ok)">{counts['AUTO_MATCHED']}</b></div>
  <div class="metric">Cần xác nhận<b style="color:var(--warn)">{counts['NEED_REVIEW']}</b></div>
  <div class="metric">Chưa xác định<b style="color:var(--bad)">{counts['UNMATCHED']}</b></div>
</div>
<div class="controls">
  <input id="search" placeholder="Tìm filename, tên, barcode, SKU, reason...">
  <select id="status"><option value="ALL">Tất cả trạng thái</option><option>AUTO_MATCHED</option><option>NEED_REVIEW</option><option>UNMATCHED</option><option>ERROR</option></select>
  <select id="pageSize"><option>25</option><option selected>50</option><option>100</option></select>
  <button id="exportBtn">Tải quyết định duyệt JSON</button>
</div>
<div class="table-wrap">
<table>
<thead><tr><th>#</th><th>Ảnh</th><th>Input</th><th>Trạng thái</th><th>POS / Candidates</th><th>Bằng chứng / Lý do</th></tr></thead>
<tbody id="rows"></tbody>
</table>
</div>
<div class="pager"><button id="prev">← Trước</button><span id="pageInfo"></span><button id="next">Sau →</button></div>
</main>
<script id="data" type="application/json">{payload}</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
let page = 1;
let decisions = {{}};
try {{ decisions = JSON.parse(localStorage.getItem('deterministic_review_decisions') || '{{}}'); }} catch (_) {{}}

const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
const statusLabel = status => ({{AUTO_MATCHED:'Đã khớp deterministic',NEED_REVIEW:'Cần xác nhận',UNMATCHED:'Chưa xác định',ERROR:'Lỗi'}}[status] || status);
const statusClass = status => status === 'AUTO_MATCHED' ? 'auto' : status === 'NEED_REVIEW' ? 'review' : status === 'ERROR' ? 'error' : 'unmatched';

function searchable(item) {{
  return [item.filename,item.normalized_name,item.source,item.capture_id,item.side,item.status,item.match_method,item.reason,
    item.matched?.name,item.matched?.barcode,item.matched?.sku,
    ...item.candidates.flatMap(c => [c.name,c.product_id,c.barcode,c.sku])].filter(Boolean).join(' ').toLowerCase();
}}
function filtered() {{
  const query = document.getElementById('search').value.trim().toLowerCase();
  const status = document.getElementById('status').value;
  return DATA.filter(item => (status === 'ALL' || item.status === status) && (!query || searchable(item).includes(query)));
}}
function choose(itemId, candidateIndex) {{
  const item = DATA.find(row => row.id === itemId);
  const candidate = item?.candidates.find(c => c.index === candidateIndex);
  if (!item || !candidate) return;
  decisions[item.filename] = {{
    selection: String(candidateIndex),
    product_id: candidate.product_id,
    sku: candidate.sku,
    barcode: candidate.barcode,
    product_name: candidate.name,
    source: 'review_report_html'
  }};
  localStorage.setItem('deterministic_review_decisions', JSON.stringify(decisions));
  render();
}}
function markNoMatch(itemId) {{
  const item = DATA.find(row => row.id === itemId);
  if (!item) return;
  decisions[item.filename] = {{selection:'No Match',product_id:'',sku:'',barcode:'',product_name:'',source:'review_report_html'}};
  localStorage.setItem('deterministic_review_decisions', JSON.stringify(decisions));
  render();
}}
function matchedBlock(item) {{
  if (!item.matched) return '<span class="muted">Không có identity đã chốt</span>';
  const p = item.matched;
  return `<b>${{esc(p.name)}}</b><div class="code">PID: ${{esc(p.product_id)}} · SKU: ${{esc(p.sku)}} · BC: ${{esc(p.barcode)}}</div>`;
}}
function candidateBlock(item) {{
  if (!item.candidates.length) return '<span class="muted">Không có candidate deterministic</span>';
  return item.candidates.map(c => `<div class="candidate"><b>#${{c.index}} ${{esc(c.name)}}</b><div class="code">PID: ${{esc(c.product_id)}} · SKU: ${{esc(c.sku)}} · BC: ${{esc(c.barcode)}}</div><div class="muted">${{esc((c.evidence||[]).join('; '))}}</div><button onclick="choose(${{item.id}},${{c.index}})">Chọn candidate này</button></div>`).join('') + `<button onclick="markNoMatch(${{item.id}})">No Match</button>`;
}}
function render() {{
  const data = filtered();
  const size = Number(document.getElementById('pageSize').value);
  const pages = Math.max(1, Math.ceil(data.length / size));
  page = Math.min(page, pages);
  const visible = data.slice((page-1)*size, page*size);
  document.getElementById('rows').innerHTML = visible.map(item => {{
    const decision = decisions[item.filename];
    const decisionText = decision ? `<div class="decision">Đã duyệt: ${{esc(decision.selection)}} ${{esc(decision.sku || '')}}</div>` : '';
    const pos = item.status === 'AUTO_MATCHED' ? matchedBlock(item) : candidateBlock(item);
    return `<tr><td>${{item.id}}</td><td><img class="thumb" loading="lazy" src="${{esc(item.image_url)}}"></td><td><b>${{esc(item.filename)}}</b><div class="muted">${{esc(item.normalized_name)}}</div><div class="code">capture=${{esc(item.capture_id)}} side=${{esc(item.side)}}</div></td><td><span class="status ${{statusClass(item.status)}}">${{statusLabel(item.status)}}</span><div class="code">${{esc(item.match_method)}}</div>${{decisionText}}</td><td>${{pos}}</td><td class="reason">${{esc(item.reason)}}<div class="muted">${{esc((item.evidence||[]).join('; '))}}</div></td></tr>`;
  }}).join('');
  document.getElementById('pageInfo').textContent = `${{page}} / ${{pages}} · ${{data.length}} items`;
  document.getElementById('prev').disabled = page <= 1;
  document.getElementById('next').disabled = page >= pages;
}}

document.getElementById('search').addEventListener('input', () => {{ page=1; render(); }});
document.getElementById('status').addEventListener('change', () => {{ page=1; render(); }});
document.getElementById('pageSize').addEventListener('change', () => {{ page=1; render(); }});
document.getElementById('prev').addEventListener('click', () => {{ if(page>1){{page--;render();}} }});
document.getElementById('next').addEventListener('click', () => {{ page++; render(); }});
document.getElementById('exportBtn').addEventListener('click', () => {{
  const blob = new Blob([JSON.stringify(decisions,null,2)], {{type:'application/json'}});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href=url; a.download='reviewed_knowledge.json'; a.click(); URL.revokeObjectURL(url);
}});
render();
</script>
</body>
</html>
"""
    (output / "review_report.html").write_text(html, encoding="utf-8")
