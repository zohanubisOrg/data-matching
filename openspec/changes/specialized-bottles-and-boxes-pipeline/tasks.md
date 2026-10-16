# Tasks

## 1. Container Classification Engine

- [x] 1.1 Implement `RigidContainerDetector` in `src/product_mapper/zohanubis/container_detector.py` combining volume regex, category/packaging keyword matches, and geometric aspect ratio ($H/W \ge 1.6$). Verify unit tests classify sample items from G1, G2, and G3 accurately.
- [x] 1.2 Integrate container detection flags into catalog loader to produce an indexed list of container candidate items across G1, G2, G3, and G4. Verify execution by printing container totals per partition.

## 2. Multi-Column Valley Separator & Hero Selector

- [x] 2.1 Implement `MultiColumnValleySeparator` in `src/product_mapper/zohanubis/valley_separator.py` using horizontal density projections to compute valley minima between 2 or 3 adjacent containers. Verify on `IMG_1261` (2 bottles) and `IMG_1268` (3 bottles) isolating individual bounding boxes.
- [x] 2.2 Implement `FrontHeroSelector` to evaluate brand label gradient energy, typography sharpness, and barcode exclusions across candidate boxes to select the single front hero view. Verify on `IMG_1261` selecting the front view.

## 3. Dedicated Partition-Mirrored Pipeline Script

- [x] 3.1 Create `scripts/run_bottles_and_boxes_pipeline.py` that processes detected container candidates and saves deliverables directly to `output/shopify-zohanubis-image/webshop_bottles_boxes/<partition_name>/[barcode]-front.jpg`.
- [x] 3.2 Add glass/reflection protection and contact shadow grounding in `StudioStandardizer` specifically for isolated container packshots. Verify output packshots center single containers on 2048x2048 white canvas.

## 4. QualityGate Tuning & End-to-End Verification

- [x] 4.1 Update `QualityGate` in `src/product_mapper/zohanubis/quality_gate.py` with an adaptive container profile that accepts tall aspect ratios ($H/W \le 3.5$) and verifies single-component integrity ($n\_components = 1$).
- [x] 4.2 Run end-to-end dry run on test cases (`IMG_1261`, `IMG_1268`, and G2 sample `8850206111022`), verify files are created in `webshop_bottles_boxes/<partition>/`, and verify zero alterations occur in `webshop_front_hd`.
