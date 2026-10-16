# Front Gemini Semantic Quality Gate

## ADDED Requirements

### Requirement: Semantic visual evidence is bound to the exact candidate
The batch SHALL evaluate every candidate that clears Python's hard file, identity and geometry checks with the configured Gemini Pro model. The request SHALL include the oriented immutable source, rendered candidate, catalog barcode/Record ID/product name and available customer W/Y references, with the role of each image labelled. The model SHALL return structured `PASS`, `REVIEW` or `FAIL`, per-criterion observations for subject identity, front/back face, sale-unit count, package completeness/detail preservation, external background and reference consistency, evidence text, reason codes and an allowlisted repair recommendation. The system MUST NOT interpret a model confidence value as calibrated probability or convert model text into an unmeasured numeric pixel metric.

#### Scenario: Product and package survive processing
- **WHEN** Python's hard technical gates pass and Gemini can verify the candidate against the source and reliable W/Y references
- **THEN** the semantic gates record PASS with input hashes, model version, prompt/schema version and criterion evidence

#### Scenario: A clear semantic defect is visible
- **WHEN** the product is missing/wrong, the face is wrong, multiple sale units remain, a package detail is lost or external wood/carton background remains
- **THEN** the relevant semantic gate records FAIL and the candidate cannot be promoted

#### Scenario: A reference conflicts or a transparent edge is uncertain
- **WHEN** W/Y contradict the catalog/source or the model cannot distinguish clear film from surrounding background
- **THEN** the relevant gate records REVIEW and the candidate cannot be promoted

### Requirement: Gemini and Python decisions fail closed
Python SHALL remain authoritative for exact file identity, dimensions, rotation, scale, saved JPEG parameters, fingerprints and available numeric evidence. Gemini SHALL NOT override a failed deterministic gate. A missing API key, timeout, exhausted budget, authorization error, unavailable model, refusal, malformed/schema-invalid response or missing evidence SHALL produce REVIEW, never PASS. The pilot SHALL pin model `gemini-3.1-pro-preview`, response model version and prompt/schema versions; automatic model fallback is prohibited.

#### Scenario: Native resolution is insufficient
- **WHEN** strict render reports an upscale would be required
- **THEN** Python rejects that attempt and Gemini cannot override the resolution gate

#### Scenario: Gemini cannot return a valid judgement
- **WHEN** a request errors, times out or cannot be parsed against the response schema
- **THEN** the row remains REVIEW with the bounded error and current request-budget usage recorded

### Requirement: Repair attempts are bounded and reproducible
The system SHALL render no more than three candidates per barcode, each independently from an immutable original. A failure may trigger at most two Python-selected, allowlisted repair recipes using an alternate source, corrected subject selection, expanded complete-package bounds or safer background removal. Gemini may recommend a recipe but SHALL NOT produce or edit product pixels or select an unapproved recipe. Every attempt SHALL retain source/output hashes, gate evidence and predecessor-attempt id. Uncertain evidence, no remaining source, or no safe recipe SHALL end in REVIEW; CUSTOMER_RESHOOT requires all eligible sources to be exhausted and an explicit reviewer decision.

#### Scenario: First candidate has a correctable crop defect
- **WHEN** a candidate is semantically rejected for a crop/boundary error and a different valid source is available
- **THEN** the Python repair selector creates a new render attempt from that source and reruns both gates

#### Scenario: Repair limit is reached
- **WHEN** three total renders have not produced a candidate that clears all gates
- **THEN** the row remains REVIEW with the attempt history; the system does not loop or promote

### Requirement: Shared budget and concurrency apply across runners
All main and shard runners SHALL use one concurrency limiter allowing no more than two Gemini requests in flight and one atomic pilot budget of 200 requests, counting retries and detail-image calls. Budget state and cache entries SHALL be durable and keyed by exact input hashes, model/version, prompt/schema versions and image-preparation configuration. Duplicate identical judgements MAY be reused. Reaching the cap stops new requests and preserves pending rows for resume.

#### Scenario: Multiple shards share the pilot
- **WHEN** multiple shard processes request Gemini concurrently
- **THEN** their combined in-flight request count never exceeds two and their shared request count never exceeds 200

### Requirement: Promotion requires current all-gate evidence
Workers SHALL write candidates only under an isolated run directory. A candidate SHALL be promoted to `tagged/front-v5` only when Q1–Q6 are PASS and hashes/fingerprints still match. Promotion SHALL be per-barcode locked and atomic, shall preserve a hash-bound rollback copy of an existing non-curated destination, and SHALL abort on an active competing writer or unexpected file change. `apptance` entries are skipped and immutable. Workbook embedding still requires a separate release manifest and human review.

#### Scenario: All current gates pass
- **WHEN** the exact candidate passes current Python and Gemini gates under an approved enforce policy
- **THEN** the candidate is promoted atomically and its manifest links the source, QA, output hash and prior destination snapshot

#### Scenario: Candidate changes after review or another writer is active
- **WHEN** its output/input hash changed or an active/competing writer is detected
- **THEN** promotion aborts and the barcode stays in REVIEW

### Requirement: Quality upgrades are benchmarked and human-labelled
Every version change SHALL carry a versioned prompt/model/configuration identity and be evaluated against separate frozen development and holdout manifests with source/reference/output hashes and separate human labels. The report SHALL include critical-defect false accepts, false rejects, REVIEW counts, repair results, package-group counts and API usage. No candidate version with a critical-defect false accept or holdout regression SHALL become active. Human labels SHALL NOT be generated from the tested model's predictions.

#### Scenario: Proposed upgrade regresses on an edge case
- **WHEN** a new prompt, model or algorithm accepts a known critical case or regresses on holdout
- **THEN** the current active version remains unchanged and the report records the failure
