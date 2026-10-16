# Spec Delta

## Purpose

Enforces universal zero-gap touching product separation across bottles, cartons, cans, and pouches using Column W ground-truth guidance, and establishes soft-edge white-bleed defringing to preserve delicate packaging edges on pure white canvases.

## ADDED Requirements

### Requirement: Universal Zero-Gap Touching Cluster Detection via Aspect Ratio Anomaly
The system SHALL compare the aspect ratio ($W/H$) of any detected foreground bounding box against the ground-truth aspect ratio of the Column W master demo thumbnail. When the raw bounding box aspect ratio exceeds $1.6 \times$ the demo aspect ratio, the system SHALL flag the region as a multi-item touching cluster, even if binary connected-component analysis returns only a single contour.

#### Scenario: Detecting 3 touching bottles merged into a single contour
- **WHEN** a raw photograph contains 3 fish sauce bottles standing side-by-side touching with zero gap, producing a single connected bounding box with $W/H = 0.85$ while the demo thumbnail has $W/H = 0.28$
- **THEN** system flags the bounding box as a touching cluster ($0.85 / 0.28 = 3.03 \ge 1.6$) and initiates archetype-specific cleaving

#### Scenario: Detecting 2 touching carton boxes merged into a single contour
- **WHEN** a photograph contains 2 spice boxes standing touching face-to-face with $W/H = 1.35$ while demo thumbnail has $W/H = 0.70$
- **THEN** system flags the region as a touching cluster ($1.35 / 0.70 = 1.93 \ge 1.6$) and initiates vertical seam detection

### Requirement: Archetype-Specific Boundary Cleaving for Touching Objects
The system SHALL apply packaging-geometry-specific boundary cleaving across the 4 major packaging archetypes:
1. **Carton Boxes (`Hộp`)**: The system SHALL compute horizontal Sobel gradient energy to detect the continuous vertical seam line between adjacent flat box surfaces.
2. **Metal Cans (`Lon`)**: The system SHALL identify discrete top/bottom circular chime rims and slice along the minimum-intensity valley formed by the cylindrical tangent contact shadow.
3. **Bottles (`Chai`)**: The system SHALL detect shoulder/neck V-groove concavities in the upper 35% height and cleave vertically along the crevice shadow.
4. **Pouches and Bags (`Gói`)**: The system SHALL locate top-notch and heat-seal crimp indentations and leverage SIFT homography corners to isolate the front-facing pouch boundary.

#### Scenario: Cleaving 2 touching cardboard boxes along vertical seam
- **WHEN** a touching cluster of 2 cardboard cartons is detected
- **THEN** system calculates the horizontal gradient profile, pinpoints the vertical seam peak, and splits the cluster into distinct left and right candidate boxes

#### Scenario: Cleaving 3 touching bottles along shoulder V-grooves
- **WHEN** a touching cluster of 3 bottles is evaluated
- **THEN** system detects 2 V-groove concavities at the bottle shoulders and cleaves the cluster into 3 distinct vertical candidate boxes (Left, Center, Right)

### Requirement: Demo Ground-Truth Guided Front Hero Selection
The system SHALL NOT assume that the front hero item is positioned in the horizontal center of the scene. When a cluster is cleaved into multiple candidate items (Left, Center, Right), the system SHALL evaluate each candidate independently against the Column W demo image using SIFT inlier count and deep visual feature cosine similarity. The candidate possessing the highest similarity score SHALL be designated as the front hero product.

#### Scenario: Front fish sauce bottle located on the left
- **WHEN** an image contains 3 bottles where the Left bottle displays the front label matching the Column W demo while Center and Right bottles show angled or back views
- **THEN** system computes similarity across all 3 candidates, selects the Left bottle as the Front Hero, and crops out Center and Right companion bottles

#### Scenario: Front bottle located on the right
- **WHEN** an image contains 3 bottles where the Right bottle matches the Column W demo
- **THEN** system selects the Right bottle as Front Hero and crops out the Left and Center bottles

### Requirement: Soft-Edge Margin Preservation and White-Bleed Defringing
The system SHALL maintain a soft alpha transition zone ($15 \le \alpha \le 235$) around product perimeters to preserve transparent bottle glass, thin plastic packaging film, and hanging tabs. Within the transition margin ($10 < \alpha < 180$), if the original pixel color has a Euclidean distance to the border studio backdrop of less than 32.0, the system SHALL execute White-Bleed Defringing by shifting the RGB values towards pure white (`[255, 255, 255]`) proportional to background confidence:
$RGB_{adj} = \frac{\alpha}{255} \cdot RGB_{orig} + (1 - \frac{\alpha}{255}) \cdot [255, 255, 255]$
The system SHALL composite the defringed product onto a `#FFFFFF` canvas without dark halos or gray fringing.

#### Scenario: Preserving transparent glass bottle neck without dark halo
- **WHEN** a transparent glass bottle is matted onto the 2048x2048 white canvas
- **THEN** system preserves translucent edge pixels without binary clipping, bleeds backdrop-colored edge pixels to white, and eliminates dark gray boundary halos

#### Scenario: Preserving cellophane pouch crinkles and hanging tabs
- **WHEN** a cellophane food bag with transparent edges is processed
- **THEN** system preserves outer crinkles and hanging slots without interior erosion while blending external backdrop residue seamlessly into the white canvas

### Requirement: Mathematical Safety and Modulo Overflow Elimination
The system SHALL enforce numerical safety limits across all image distance and mask calculations:
1. In `HeroCropper._get_foreground_mask`, the system SHALL clip the sum of absolute channel differences to the range $[0, 255]$ before casting to `uint8`, preventing modulo 256 wrap-around errors.
2. In `StudioStandardizer.standardize`, the system SHALL NOT wipe out secondary contours unless they represent floor-reflection noise (satisfying $Y_{centroid} > 0.85 \times H$ and $W/H > 4.5$). Legitimate secondary components belonging to the product body (such as hanging loops, two-tray food compartments, and attached accessories) SHALL be preserved in the canvas composite.

#### Scenario: Preventing dark high-contrast product from wrapping around to background
- **WHEN** an image contains a dark bottle whose channel difference sum against background equals 256 or 512
- **THEN** system clips difference to 255 instead of overflowing to 0, correctly identifying the dark product as foreground

#### Scenario: Preserving 2-compartment wonton tray and hanging tab
- **WHEN** a product has a 2-compartment tray or a distinct hanging loop separated by a transparent gap
- **THEN** system preserves both components on the standardized canvas rather than deleting the non-centered piece
