# Rabuta bulk front reprocessing — agent handoff

Updated: 2026-10-15 (Asia/Saigon)

## Objective and authorization

Continue correcting the Rabuta webshop front images from the Audit 2 queue and publish verified results into:

`D:\Work\shopify\output\catalog_pairs\tagged\front-v3`

The user explicitly authorized overwriting this directory. The live folder must be updated only with a candidate bound to the exact Excel row, barcode, Record ID, reviewed native source and complete true-front package boundary. The customer reference image in workbook column W and all workbook cells remain unchanged. The workbook's embedded X previews have not been refreshed by this folder-only operation.

Do not treat an uninspected source candidate, an AI/logo contour, an Excel preview, or a source that needs upscaling as a verified package boundary. Unresolved records retain their current image and a review/blocker disposition. Do not label the catalog QA PASS.

## Current state after the first bulk wave

- The full Audit 2 set of **1,351** records was reconciled against the delivery workbook.
- **70** records have source-aligned reviewed annotations and were rendered to 2400 × 2400 candidates.
- **64** were published into `front-v3`: **54 replacements** and **10 newly added front files**.
- **6** rendered candidates were held because the product itself would need upscaling: Excel rows **197, 317, 571, 622, 669 and 1351**.
- Remaining full-catalog statuses: **1,102 NEEDS_MANUAL_REVIEW**, **177 BLOCKED_NEEDS_SOURCE**, **2 BLOCKED_IDENTITY_CONFLICT** (1,281 records). Total accounting is 64 published + 6 rendered but held for upscaling + 1,281 pending/blocked = 1,351.
- `front-v3` contained 1,169 files before the first wave and contains **1,179** now.
- The delivery workbook is unchanged; verified SHA-256: `c8a58d9a294799cd4bb12c13bf32109ef8681d096875dd84ddca23d947c1eb11`.
- At the end of the first publication, the publisher verified every live file against its original snapshot or journaled publication hash. The original 1,169-file snapshot is in `output/catalog_pairs/front-v3-backups/before-bulk-2026-10-15/`.
- Publication journal: `output/catalog_pairs/front-v3-backups/before-bulk-2026-10-15/publication.json` (`APPLIED`, QA is explicitly false). Original snapshot manifest and files are next to it.
- First-wave full run and report are under `output/catalog_pairs/reprocess-v4/bulk-2026-10-15/`. The contact sheet is `bulk_contact_70.jpg`; machine-readable report is `bulk_publication_report.json` and `bulk_publication_report.md`.
- Annotation ledger: `output/catalog_pairs/reprocess-v4/bulk_annotations_2026-10-15.jsonl` (70 unique identities). Per-group evidence is in `bulk_group1_annotations.jsonl`, `bulk_group2_annotations.jsonl`, and `bulk_group3_annotations.jsonl`; each group has its own disposition JSONL and visual review sheets under `scratch/rabuta_bulk_group1/`, `scratch/rabuta_bulk_group2/`, and `scratch/rabuta_bulk_group3/`.
- Publisher safety code is `scripts/publish_rabuta_fronts.py`; renderer/runner details are in `docs/rabuta-background-reprocessing.md` and `src/product_mapper/vision/package_packshot.py`.
- At stop time, no `*round2*` output file existed under `output/catalog_pairs/reprocess-v4`, no Python processing process was running, and all three review agents were interrupted. Recheck for partial scratch artifacts before resuming.
- Publisher tests and repository suite passed after the transaction fixes: **15 publisher tests, 89 total tests**. This validates code behavior, not image QA.

### Current-state recheck for the receiving agent

The handoff verification found **two later changes outside the first-wave journal**, with no added/removed filenames:

| Live filename | Excel row | Record ID |
|---|---:|---|
| `4045198851054-front.jpg` | 1011 | `G3-0122` |
| `4045198851566-front.jpg` | 1008 | `G3-0119` |

The provenance of these later edits is not established by the first-wave journal. Preserve both current files. Reconcile their source, masks and any partial scratch artifacts before including them in the next publication. Do not restore or overwrite them just to match the historical snapshot. The exact expected/current hashes and timestamps are recorded in `docs/rabuta-handoff-current-state-2026-10-15.json`. That check also verified all 1,169 backup files, the unchanged workbook hash, 1,179 current files, 305 remaining queue identities, and the absence of final round-two output files.

## Queue still to review

Audit 2 queue: `C:\Users\HP\Downloads\Rabuta_QA_Reprocess_Queue.jsonl` (**375 records**). Subtracting the 70 existing annotation identities left **305 queue records** at handoff:

| Excel rows | Remaining queue records |
|---|---:|
| 4–454 | 74 |
| 455–904 | 67 |
| 905–1354 | 164 |

The second-wave agents were assigned those non-overlapping ranges but interrupted before producing final output files. The counts above are the queue scope to reconcile; inspect the queue and current per-group scratch directories before restarting. The authoritative full-catalog audit is `C:\Users\HP\Downloads\Rabuta_QA_Reaudit_All_1351.jsonl`.

Known blockers to keep visible:

- Barcode `8938500075070` maps to two records at rows **576** (`G2-0117`, Fresh Nua) and **605** (`G2-0149`, Fresh Bud). Both are blocked until product identity is resolved.
- Row **1333** has a photographed ROSNEUNG pack while the catalog identity is RosDee; keep blocked as an identity mismatch.
- Row **1340** has a candidate front with a natural hanging hole. The current renderer rejects mask holes; do not erase the hole or claim a normal cutout.
- Row **597** source recovery showed the tapioca-starch front, but empty transparent film still needs a dedicated matting review.
- Rows **110, 134 and 140** have clipping/film-edge limitations in the reviewed sources; use a complete alternate source if found.
- Audit 2 barcode exceptions remain semantic: barcode presence by itself is not a wrong-face finding. Validate package identity and face.

## Annotation gate

Use native original photographs only. `output/catalog_pairs/originals/<barcode>/` and the direct source paths in the first-wave annotations are common locations. The historical `front_v3_source_map.json` and `front_v3_master_plan.json` contain candidate paths; their face/mode labels are not evidence. Never use old cutouts, `front-v3`, `front-v2`, `back-v2`, workbook previews, or generated images as restoration sources.

For each accepted annotation, visually compare the source with the exact catalog record, confirm one real sales unit and its true front, and trace the whole visible package boundary in the EXIF-oriented native source coordinates. Keep all labels and artwork inside the mask. Reject clipped edges, ambiguous face or identity, multiple products, unresolved transparent film, holes, or a boundary enclosing only a logo. Store evidence concise enough for another reviewer to understand why the identity and boundary were accepted.

Required JSONL fields:

```json
{
  "excel_row": 123,
  "barcode": "string-preserved-barcode",
  "record_id": "exact-record-id",
  "source_path": "absolute native source path",
  "source_sha256": "sha256 of source bytes",
  "source_size": [3024, 4032],
  "identity_verified": true,
  "single_product_verified": true,
  "complete_package": true,
  "face": "front",
  "evidence": "What establishes this exact product and complete true front",
  "polygon": [[100, 100], [1000, 100], [1000, 2000], [100, 2000]]
}
```

The numeric polygon above only illustrates valid JSON syntax. Trace the actual package boundary for each source; never reuse this example rectangle as a mask.

Optional fields are `rotation_ccw` (0/90/180/270), `shape`, and `film_matting_required`. Set the film flag when that review is needed; such a row must remain blocked. Coordinates refer to the EXIF-oriented source size. The runner checks exact row/barcode/Record ID against the current workbook and detects barcode collisions across the whole workbook.

Write round-two work to new files, for example:

- `output/catalog_pairs/reprocess-v4/bulk_group1_round2_annotations.jsonl`
- `output/catalog_pairs/reprocess-v4/bulk_group1_round2_dispositions.jsonl`
- Equivalent `group2` and `group3` filenames.

Every queue record in the assigned range needs a disposition, including uninspected, missing-source, wrong-face, cropped, identity-conflict and matting cases. An annotation is accepted only after its rendered 2400 × 2400 result and source-overlay have been reviewed. Do not edit the first-wave annotation/disposition files.

## Render and incremental publication procedure

1. Reconcile the two later live-file changes recorded above. Read the current workbook and verify exact identities for every queue record. Read the existing first-wave ledgers and subtract their keys `(barcode, record_id, excel_row)` before reviewing. Reconcile the round-two dispositions so no queued row disappears.
2. Merge unique annotations into a new JSONL. Stop on duplicate identity or a workbook mismatch; do not pick one silently.
3. Render the full Audit 2 catalog (or a source-audited subset) to a **new, unused** review directory. The runner requires the complete catalog to enforce collision checks. Example:

   ```powershell
   C:\Python313\python.exe scripts/reprocess_rabuta_verified.py `
     --records C:\Users\HP\Downloads\Rabuta_QA_Reaudit_All_1351.jsonl `
     --annotations output/catalog_pairs/reprocess-v4/bulk_annotations_round2.jsonl `
     --output-dir output/catalog_pairs/reprocess-v4/bulk-2026-10-15-round2
   ```

   Exit code 2 means review/blocker records remain; that is expected and is not a processing failure. Inspect the result JSONL and every new rendered candidate.
4. Only publish newly reviewed rows from the second wave. Filter the full results into a separate JSONL whose identity keys are the round-two annotations. Candidates with `layout.source_resolution_warning=true` are skipped by the publisher; find a larger native source or leave the current image and disposition unchanged.
5. Take a new snapshot of the **current post-first-wave** live folder at a new path, such as `output/catalog_pairs/front-v3-backups/after-bulk64-before-round2-2026-10-15/`. Do not reuse the original first-wave snapshot for an incremental publication; the live folder has changed.
6. Use the authorized publication tool, binding to the full workbook:

   ```powershell
   C:\Python313\python.exe scripts/publish_rabuta_fronts.py `
     --results output/catalog_pairs/reprocess-v4/round2_results_only.jsonl `
     --backup-dir output/catalog_pairs/front-v3-backups/after-bulk64-before-round2-2026-10-15 `
     --target-dir output/catalog_pairs/tagged/front-v3 `
     --workbook output/catalog_pairs/Rabuta_master_final_Delivery_Embedded.xlsx `
     --apply
   ```

   The user has already authorized overwriting `front-v3`; no new confirmation is needed for the same scope. The publisher validates the snapshot, all live/backup hashes, catalog identity, barcode collision, annotation-to-result identity, native source hash/size, mask hash and exact polygon-to-mask match, candidate canvas, white border and upscale status. It atomically journals state and rolls back on interruption or failed replacement. Stop if it reports an unexpected live edit or provenance conflict.
7. Verify the incremental journal is `APPLIED`, published filenames/hash match, every original snapshot file remains available, the workbook SHA is still the value above, and `front-v3` contains only expected replacements/additions. Create a cumulative report with published/replaced/added/skipped counts and all unresolved records. Keep `qa_pass=false` while any row lacks final image QA.

## Current limitations and user-facing result

The first wave used manually reviewed package polygons and preserved source RGB; it addressed the known segmentation behavior for 64 files. This is not an automatic segmentation fix proven across all catalog images. The remaining records require inspection/source evidence, and the workbook still has its preexisting embedded webshop previews because only the `front-v3` folder was authorized for writing. Report those facts plainly; do not imply that Shopify can be uploaded from the unchanged workbook without refreshing its embedded X images.

## Prompt to paste into the receiving agent

```text
Tiếp tục xử lý ảnh Rabuta tại D:\Work\shopify. Trước tiên đọc:
1. docs/rabuta-bulk-reprocessing-handoff-2026-10-15.md
2. docs/rabuta-handoff-current-state-2026-10-15.json
3. docs/rabuta-background-reprocessing.md

Mục tiêu: tiếp tục xử lý catalog, ưu tiên 305 hồ sơ Audit 2 còn lại, tạo ảnh mặt trước giữ nguyên toàn bộ bao bì và ghi các kết quả đã xác minh vào output/catalog_pairs/tagged/front-v3. Tôi đã cho phép ghi đè thư mục này; mỗi đợt phải có backup và nhật ký xuất bản.

Đối soát trước hai file thay đổi ngoài journal tại dòng 1008 và 1011, giữ nguyên chúng trong khi xác minh. Kiểm tra scratch để tránh làm lại hoặc bỏ sót phần đang dở. Không sửa workbook hay cột W; không dùng preview/cutout cũ để phục hồi, không tự tạo nhãn hoặc thông tin sản phẩm, không coi P3 là QA PASS. Các ca thiếu nguồn, sai identity/mặt, bị cắt, film chưa xử lý hoặc cần upscale phải có trạng thái rõ ràng.

Tiếp tục theo procedure trong spec, dùng scripts/reprocess_rabuta_verified.py và scripts/publish_rabuta_fronts.py. Tạo thư mục review và backup mới cho mỗi đợt; không dùng lại snapshot trước đợt 64 ảnh. Báo số ảnh thực sự thay/bổ sung, hồ sơ còn bị chặn và bằng chứng kiểm tra. Không commit, push hoặc upload Shopify khi chưa được yêu cầu.
```

