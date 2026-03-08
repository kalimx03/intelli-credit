# Intelli-Credit — Requirements

Functional and non-functional requirements for the Intelli-Credit corporate credit decision engine.

---

## Table of Contents

- [Product Overview](#product-overview)
- [Users](#users)
- [Functional Requirements](#functional-requirements)
  - [FR-1 Document Ingestion](#fr-1-document-ingestion)
  - [FR-2 AI Data Extraction](#fr-2-ai-data-extraction)
  - [FR-3 Validation](#fr-3-validation)
  - [FR-4 Five Cs Scoring Engine](#fr-4-five-cs-scoring-engine)
  - [FR-5 Credit Decision Output](#fr-5-credit-decision-output)
  - [FR-6 CAM Report Generation](#fr-6-cam-report-generation)
  - [FR-7 Analysis Persistence](#fr-7-analysis-persistence)
  - [FR-8 Frontend Interface](#fr-8-frontend-interface)
  - [FR-9 API](#fr-9-api)
- [Non-Functional Requirements](#non-functional-requirements)
  - [NFR-1 Correctness and Determinism](#nfr-1-correctness-and-determinism)
  - [NFR-2 Reliability and Error Handling](#nfr-2-reliability-and-error-handling)
  - [NFR-3 Security](#nfr-3-security)
  - [NFR-4 Performance](#nfr-4-performance)
  - [NFR-5 Observability](#nfr-5-observability)
  - [NFR-6 Portability and Deployment](#nfr-6-portability-and-deployment)
- [Constraints](#constraints)
- [Out of Scope](#out-of-scope)

---

## Product Overview

Intelli-Credit is an AI-assisted corporate credit appraisal system for Indian banks and NBFCs. It automates the extraction of financial data from uploaded PDF documents, scores the borrower using a deterministic Five Cs framework aligned with RBI and other Indian regulatory norms, and generates a professional Credit Appraisal Memorandum (CAM) PDF.

**Non-negotiable principle:** The LLM (Claude) is used only for data extraction and narrative text generation. All credit scoring and decision logic is deterministic Python. The same inputs must always produce the same credit score.

---

## Users

| User | Description |
|------|-------------|
| **Credit Analyst** | Primary user. Uploads financial documents, reviews extracted data and scores, generates CAM reports, and uses the results to support credit decisions. |
| **Branch Manager / Sanctioning Authority** | Reviews the generated CAM. Does not interact with the system directly but is the consumer of the output. |
| **System Administrator** | Manages deployment, monitors logs, rotates API keys, re-ingests the knowledge base when regulations are updated. |

---

## Functional Requirements

### FR-1 Document Ingestion

**FR-1.1** The system shall accept PDF files uploaded via a web interface or REST API.

**FR-1.2** The system shall reject non-PDF files with a clear error message identifying the received file type.

**FR-1.3** The system shall reject PDF files larger than 20 MB with an error message stating the actual size and the limit.

**FR-1.4** The system shall reject empty files (0 bytes).

**FR-1.5** The system shall process at most 60 pages from any single PDF. If the document is longer, the first 60 pages shall be processed and the truncation shall be noted in the analysis warnings.

**FR-1.6** Text extraction shall cap output per page at 4,000 characters and total output at 60,000 characters. Truncations shall be marked with explicit markers in the extracted text.

**FR-1.7** A single corrupted or unreadable page shall not abort extraction of the rest of the document. Failed pages shall be skipped and noted in warnings.

**FR-1.8** Table content extracted from a page shall be deduplicated against freeform text already extracted from the same page to avoid double-counting of values.

**FR-1.9** If no text can be extracted from any page (e.g. fully scanned document), the system shall return a `422` error with a message indicating the document may be image-based.

---

### FR-2 AI Data Extraction

**FR-2.1** The system shall use Claude Sonnet 4 (`claude-sonnet-4-20250514`) to extract financial and compliance data from the document text.

**FR-2.2** The following 22 fields shall be extracted when present in the document:

| Field | Type | Description |
|-------|------|-------------|
| `revenue` | numeric | Annual revenue / turnover (INR) |
| `ebitda` | numeric | EBITDA (INR) |
| `pat` | numeric | Profit after tax (INR) |
| `net_worth` | numeric | Net worth / shareholders' equity (INR) |
| `total_debt` | numeric | Total outstanding debt (INR) |
| `current_ratio` | numeric | Current assets / current liabilities |
| `debt_equity_ratio` | numeric | Debt / equity ratio |
| `interest_coverage_ratio` | numeric | EBIT / interest expense |
| `dscr` | numeric | Debt service coverage ratio |
| `auditor_qualification` | boolean | Auditor issued qualified/adverse opinion |
| `gst_mismatch` | boolean | GST 2A/3B reconciliation mismatch found |
| `mca_filing_status` | boolean | MCA filing default present |
| `rbi_regulatory_risk` | boolean | RBI risk classification or NPA flag present |
| `litigation_pending` | boolean | Active material litigation present |
| `contingent_liabilities` | numeric | Total contingent liabilities (INR) |
| `related_party_transactions` | boolean | Irregular RPTs present |
| `years_in_operation` | numeric | Years since incorporation |
| `promoter_experience_years` | numeric | Promoter industry experience (years) |
| `industry_sector` | string | Industry classification |
| `collateral_value` | numeric | Collateral value (INR) |
| `collateral_type` | string | Type of collateral offered |
| `loan_amount_requested` | numeric | Loan amount requested (INR) |

**FR-2.3** Every extracted field shall be returned as an object containing three sub-fields: `value` (the extracted value or null), `confidence` (float 0.0–1.0), and `evidence` (a short verbatim quote from the document supporting the value).

**FR-2.4** If a field cannot be found in the document, it shall be returned with `value: null`. The system shall never fabricate or infer a value not explicitly present in the document.

**FR-2.5** All monetary values shall be converted to absolute INR (rupees). Values expressed in crores shall be multiplied by 10,000,000.

**FR-2.6** If the analyst supplies a `loan_amount_requested` value in the submission form and the LLM did not extract one, the system shall inject the user-provided value with `confidence: 1.0` and `evidence: "Explicitly provided by user in submission form."`.

**FR-2.7** The system shall retry Claude API calls up to two times on rate limit or transient API errors before returning an error to the caller.

**FR-2.8** If Claude returns malformed JSON, the system shall attempt to recover using four sequential strategies: direct parse, markdown fence stripping, regex extraction of the first `{...}` block, and balanced-brace scanning. If all strategies fail, a fully-null skeleton shall be returned and a warning logged.

**FR-2.9** Extraction keys not present in the known 22-field schema shall be stripped before the data reaches validation. The system shall never pass unknown keys to the scoring engine.

---

### FR-3 Validation

**FR-3.1** All extracted data shall pass through a five-gate validation layer before reaching the scoring engine.

**FR-3.2 Gate 1 — Schema format:** Each field entry must be a dict with `value`, `confidence`, and `evidence` keys. Entries that are not dicts shall be nulled and flagged.

**FR-3.3 Gate 2 — Type coercion and plausibility bounds:**
- Numeric fields shall be coerced to float. Non-coercible values shall be nulled and flagged.
- The following fields shall be flagged (not nulled) if outside plausibility bounds:

| Field | Min | Max |
|-------|-----|-----|
| `current_ratio` | 0.0 | 30.0 |
| `debt_equity_ratio` | 0.0 | 50.0 |
| `interest_coverage_ratio` | −50.0 | 200.0 |
| `dscr` | −10.0 | 50.0 |
| `years_in_operation` | 0.0 | 200.0 |
| `promoter_experience_years` | 0.0 | 80.0 |

- `revenue`, `collateral_value`, and `loan_amount_requested` shall be flagged (not nulled) if negative.

**FR-3.4 Gate 3 — Boolean coercion:** Boolean fields shall accept `true/false`, `1/0`, `yes/no`, and string equivalents. Ambiguous values shall be nulled and flagged.

**FR-3.5 Gate 4 — Confidence threshold:** Fields with `confidence < 0.6` shall be flagged for manual review. They shall not be nulled — low-confidence data may still be approximately correct and shall inform scoring while remaining visible to the analyst.

**FR-3.6 Gate 5 — Cross-field consistency:**
- PAT > Revenue shall be flagged on both fields.
- EBITDA > Revenue shall be flagged on the EBITDA field.

**FR-3.7** Every flag shall include a human-readable `flag_reason` string.

**FR-3.8** Any non-null `ExtractedField` whose `evidence` string is empty shall be automatically flagged by the Pydantic model validator with the reason "No evidence for non-null value — hallucination risk".

**FR-3.9** The validated `ExtractedFinancials` model shall expose `safe_value(field_name)` and `safe_confidence(field_name)` methods that return `None` / `0.0` respectively for absent or null fields, ensuring the scoring engine can never raise `AttributeError`.

---

### FR-4 Five Cs Scoring Engine

**FR-4.1** The scoring engine shall accept only validated `ExtractedFinancials` and `ManagementInsightFlags` objects. It shall have no dependency on the LLM service.

**FR-4.2** The engine shall score five pillars independently, each on a 0–100 scale, before applying weights:

| Pillar | Weight |
|--------|--------|
| Character | 25% |
| Capacity | 30% |
| Capital | 20% |
| Collateral | 15% |
| Conditions | 10% |

**FR-4.3** The final score shall be the weighted sum of the five pillar scores, expressed as a float in [0, 100].

**FR-4.4** The engine shall implement at minimum the following scoring rules:

**Character rules:**
- `AUDITOR_QUALIFICATION`: auditor_qualification == true → −20
- `LITIGATION_PENDING`: litigation_pending == true → −15
- `PROMOTER_CONCERN`: management flag set → −15
- `YEARS_IN_OP_LOW`: years_in_operation < 5 → −15
- `RPT`: related_party_transactions == true → −10
- `YEARS_IN_OP_MODERATE`: years_in_operation 5–10 → −5
- `SUCCESSION_RISK`: management flag set → −8
- `MGMT_POSITIVE`: management flag set → +5 (capped at 100)

**Capacity rules:**
- `DSCR_CRITICAL`: dscr < 1.2 → −35
- `ICR_CRITICAL`: interest_coverage_ratio < 1.5 → −25
- `EBITDA_WEAK`: ebitda/revenue < 0.08 → −20
- `NEGATIVE_PAT`: pat < 0 → −20
- `DSCR_MARGINAL`: dscr 1.2–1.5 → −15
- `ICR_MARGINAL`: icr 1.5–3.0 → −10
- `EBITDA_MARGINAL`: ebitda/revenue 0.08–0.15 → −10

**Capital rules:**
- `NEGATIVE_NET_WORTH`: net_worth < 0 → −30
- `HIGH_LEVERAGE`: debt_equity_ratio > 4 → −30
- `CURRENT_RATIO_CRITICAL`: current_ratio < 1.0 → −25
- `CONTINGENT_LIAB`: contingent_liabilities > 0.5 × net_worth → −15
- `MODERATE_LEVERAGE`: debt_equity_ratio 2–4 → −15
- `CURRENT_RATIO_WEAK`: current_ratio 1.0–1.5 → −10

**Collateral rules (base-minus-penalty approach):**
- `LTV_CRITICAL`: ltv > 0.90 → −70 from base
- `LTV_HIGH`: ltv 0.75–0.90 → −45 from base
- `LTV_MODERATE`: ltv 0.60–0.75 → −20 from base
- `COLLATERAL_IMMOVABLE`: immovable property → +10
- `COLLATERAL_CURRENT`: current assets only → −10

**Conditions rules:**
- `RBI_RISK`: rbi_regulatory_risk == true → −25
- `GST_MISMATCH`: gst_mismatch == true → −20
- `SECTOR_HEADWIND`: management flag → −15
- `MCA_DEFAULT`: mca_filing_status == true → −10
- `CONCENTRATION_RISK`: management flag → −10

**FR-4.5** A null field value shall cause the corresponding rule to not fire. Missing data shall never default to a penalty.

**FR-4.6** Every rule, whether triggered or not, shall produce a `RuleLog` entry containing: `rule_name`, `category`, `triggered` (bool), `impact` (float), `explanation` (string), `raw_value`.

**FR-4.7** The scoring engine shall also score management insights if analyst notes are provided. Management flags shall influence the Character and Conditions pillars only.

---

### FR-5 Credit Decision Output

**FR-5.1** The system shall determine a credit decision based on the final weighted score:

| Score range | Decision |
|-------------|----------|
| ≥ 75 | Approve |
| 50–74 | Conditional Approval |
| < 50 | Reject |

**FR-5.2** The system shall determine a risk band:

| Score range | Risk band |
|-------------|-----------|
| ≥ 75 | Low |
| 50–74 | Moderate |
| < 50 | High |

**FR-5.3** The system shall suggest a loan limit based on the decision and extracted revenue:

| Decision | Loan limit |
|----------|------------|
| Approve | Revenue × 0.40 |
| Conditional Approval | Revenue × 0.25 |
| Reject | Revenue × 0.10 |

If revenue is null, the suggested loan limit shall be 0.

**FR-5.4** The system shall suggest an indicative interest rate based on the decision:

| Decision | Rate |
|----------|------|
| Approve | 8.5% p.a. |
| Conditional Approval | 10.5% p.a. |
| Reject | 13.5% p.a. |

**FR-5.5** The `ScoringResult` returned to the caller shall include: `five_cs` (per-pillar scores), `rule_log` (all rules), `final_score`, `risk_band`, `decision`, `suggested_loan_limit`, `suggested_interest_rate`, and `management_flags`.

---

### FR-6 CAM Report Generation

**FR-6.1** The system shall generate a Credit Appraisal Memorandum as a PDF document upon request (`POST /generate-cam/{id}`).

**FR-6.2** The CAM PDF shall contain 10 sections:
1. Cover page (company name, analysis ID, date, decision badge)
2. Executive Summary (AI-generated narrative)
3. Company Profile (AI-generated narrative)
4. Financial Metrics Table (all extracted fields with confidence and evidence)
5. Five Cs Breakdown (pillar scores with weighted totals)
6. Compliance and GST Review (AI-generated narrative)
7. Litigation and Legal Risk (AI-generated narrative)
8. Sector and Regulatory Conditions (AI-generated narrative)
9. Risk Trigger Log (all triggered rules with impact and explanation)
10. Final Decision and Recommendation (score, decision, loan limit, rate, justification narrative)

**FR-6.3** AI-generated narrative sections shall be produced by calling Claude with the company name, financial summary, and scoring summary as context. The prompt shall instruct Claude not to fabricate information not present in the input data.

**FR-6.4** If Claude fails to generate any narrative section, a pre-written fallback text shall be used. CAM generation shall never return an error due solely to a narrative generation failure.

**FR-6.5** All values inserted into the PDF shall be null-safe. A null value shall render as "N/A" or "Not available." — never as the string "None" or a Python exception.

**FR-6.6** All string values inserted into the PDF shall be XML-escaped to prevent ReportLab rendering errors caused by special characters (`&`, `<`, `>`).

**FR-6.7** The CAM PDF file shall be saved to the local filesystem under `./cam_reports/` (or the configured `CAM_OUTPUT_DIR`). The path shall be stored in the database against the analysis ID.

**FR-6.8** The CAM filename shall follow the pattern `CAM_{CompanyName}_{first8charsOfAnalysisId}.pdf`.

**FR-6.9** Once generated, the CAM shall be downloadable via `GET /download-cam/{id}`. If the file is not found on disk, the response shall be `410 Gone` (not `404 Not Found`), indicating the file existed but is no longer available.

**FR-6.10** The CAM footer shall state that it is system-generated, that all credit decisions are deterministic and rule-based, and that the final credit decision rests with the sanctioning authority.

---

### FR-7 Analysis Persistence

**FR-7.1** Every completed analysis shall be persisted to SQLite with a unique UUID, company name, timestamp, extracted financials (JSON), scoring result (JSON), and validation warnings (JSON array).

**FR-7.2** A stored analysis shall be retrievable by UUID via `GET /analysis/{id}`.

**FR-7.3** The last 20 analyses shall be listable via `GET /analyses`, ordered by creation time descending. Each entry shall return `id`, `company_name`, and `created_at` only (not the full JSON blobs).

**FR-7.4** A database persistence failure shall not cause the `/analyze` endpoint to return an error. The analysis result shall still be returned to the caller, with a warning in `validation_warnings` noting that the result could not be saved.

**FR-7.5** The database shall be initialised on startup (`CREATE TABLE IF NOT EXISTS`). The init function shall be idempotent.

---

### FR-8 Frontend Interface

**FR-8.1** The web interface shall provide a PDF upload page with drag-and-drop support. Files can also be selected via a standard file browser.

**FR-8.2** The upload form shall include fields for: company name (required), loan amount in crores (optional), and primary management insights (optional textarea).

**FR-8.3** The upload form shall validate client-side that only `.pdf` files are selected before submission.

**FR-8.4** While analysis is in progress, the submit button shall be disabled and a loading state shall be displayed.

**FR-8.5** On successful analysis, the browser shall redirect to the results dashboard at `/dashboard?id={analysis_id}`.

**FR-8.6** The results dashboard shall display:
- A score gauge showing the final score and decision, colour-coded (green = Approve, amber = Conditional, red = Reject)
- The Five Cs breakdown table with per-pillar raw scores, weights, and weighted contributions, with visual progress bars
- The extracted financials table showing value, confidence bar, and evidence quote for each field
- Only flagged fields or fields with low confidence shall be visually highlighted
- The full rule trigger log, showing triggered rules only with impact badges
- A validation warnings panel if any warnings are present
- "Generate CAM" and "Download CAM" buttons

**FR-8.7** The "Generate CAM" button shall call `POST /generate-cam/{id}` and on success display the "Download CAM" link. Both states shall be reflected in the UI without a page refresh.

**FR-8.8** All API errors shall be caught and displayed to the user as readable messages — not raw JSON, not unhandled exceptions.

---

### FR-9 API

**FR-9.1** The API shall be a REST API served by FastAPI on the configured port (default 8000).

**FR-9.2** The API shall include CORS middleware configured to allow requests from the frontend origin.

**FR-9.3** Interactive API documentation shall be available at `/docs` (Swagger UI).

**FR-9.4** All error responses shall follow the shape `{"detail": "..."}`.

**FR-9.5** A global exception handler shall catch any unhandled exception and return a structured JSON response with status 500. The server shall never return an HTML error page.

**FR-9.6** All `{analysis_id}` path parameters shall be validated as UUID v4 format before reaching the database. Invalid formats shall return `400`.

**FR-9.7** `GET /health` shall return `{"status": "ok", "claude_api_key_configured": true/false}`. This endpoint shall always succeed regardless of whether the database or LLM service is reachable.

---

## Non-Functional Requirements

### NFR-1 Correctness and Determinism

**NFR-1.1** Given identical input (same PDF bytes, same form fields), the system shall produce identical `scoring_result` values on every run.

**NFR-1.2** The credit decision (Approve / Conditional / Reject), final score, and every rule trigger must not vary across re-runs of the same analysis.

**NFR-1.3** The LLM shall have no influence on the numeric score or the credit decision. Score-relevant logic shall exist only in `scoring.py` as pure Python.

**NFR-1.4** Every triggered rule shall have an explanation string that a credit analyst can read and understand without reference to the source code.

### NFR-2 Reliability and Error Handling

**NFR-2.1** No single input (no matter how malformed) shall cause an unhandled exception that returns a non-JSON HTTP response.

**NFR-2.2** A failure in any non-critical subsystem (management insight analysis, CAM narrative generation, database persistence) shall degrade gracefully and never prevent the primary response from being returned.

**NFR-2.3** Claude API rate limit errors shall be retried with exponential backoff (delays of 1s, 2s). The system shall surface a `502` error to the caller only after all retries are exhausted.

**NFR-2.4** Malformed JSON from Claude shall trigger the 4-strategy recovery pipeline. If all strategies fail, a null skeleton shall be used and a warning added — the request shall still complete.

**NFR-2.5** A corrupt or unreadable page in an otherwise valid PDF shall not abort the analysis. Unreadable pages shall be skipped and logged.

**NFR-2.6** The scoring engine shall never raise an exception due to a null or missing field. All field accesses shall use null-safe accessors.

### NFR-3 Security

**NFR-3.1** The Anthropic API key shall be read from an environment variable (`CLAUDE_API_KEY`). It shall never be hardcoded, logged, or returned in any API response.

**NFR-3.2** Company names and other user-supplied strings shall be sanitised (control character removal, length cap) before use in filenames, SQL queries, and PDF content.

**NFR-3.3** Analysis IDs in URL path parameters shall be validated as UUID v4 before reaching the database layer to prevent SQL injection via malformed ID strings.

**NFR-3.4** PDF files shall be processed in memory (never written to disk during extraction). Only the generated CAM PDF shall be written to the filesystem.

**NFR-3.5** The CAM output directory shall be created automatically if it does not exist (`os.makedirs(..., exist_ok=True)`).

### NFR-4 Performance

**NFR-4.1** For a typical 10-page corporate balance sheet, the end-to-end analysis (upload → score → response) shall complete within 30 seconds under normal Claude API latency.

**NFR-4.2** CAM PDF generation shall complete within 10 seconds for a standard analysis.

**NFR-4.3** The server shall be able to handle one concurrent analysis request without resource exhaustion on a 4 GB RAM instance. (Sentence-transformers are not included in the base build; this applies to the core extraction + scoring pipeline.)

**NFR-4.4** The PDF extraction step shall not load the entire file into a Python string unnecessarily. The 60,000-character cap ensures the LLM context window is never exceeded.

### NFR-5 Observability

**NFR-5.1** The application shall use Python's `logging` module with a consistent format: `%(asctime)s [%(levelname)s] %(name)s — %(message)s`.

**NFR-5.2** The following events shall be logged at INFO level: API startup, database initialisation, PDF extraction completion (pages processed, pages failed, chars extracted).

**NFR-5.3** The following events shall be logged at WARNING level: management insight analysis failures, CAM narrative generation failures, database save failures, LLM JSON parse failures and recovery strategy used, page-level PDF extraction failures.

**NFR-5.4** The following events shall be logged at ERROR level: unhandled exceptions caught by the global handler, LLM API failures after all retries, scoring engine exceptions, PDF generation failures.

**NFR-5.5** Log output shall go to stdout so it can be captured by `journalctl`, Docker, or any log aggregation service.

### NFR-6 Portability and Deployment

**NFR-6.1** The backend shall run on Python 3.11 or later on any Linux x86-64 host.

**NFR-6.2** The frontend shall build and run with Node.js 18 or later.

**NFR-6.3** All Python dependencies shall be pinned to exact versions in `requirements.txt`.

**NFR-6.4** The application shall be configurable entirely via environment variables. No configuration shall require editing source code.

**NFR-6.5** The database initialisation function shall be idempotent — calling `init_db()` on an already-initialised database shall not destroy existing data.

**NFR-6.6** The application shall start up cleanly on a fresh server with no pre-existing database, CAM directory, or prior state.

---

## Constraints

**C-1 LLM model** — The system uses `claude-sonnet-4-20250514`. This is the model specified in `llm_service.py` (`MODEL` constant). Changing the model requires changing this constant.

**C-2 PDF format** — Only text-based PDFs are supported. Image-based (scanned) PDFs are not supported in the current implementation (no OCR integration).

**C-3 Currency** — All monetary values are expected in INR. The system does not perform currency conversion.

**C-4 Single instance** — SQLite as the persistence layer and local filesystem for CAM PDFs constrains the system to single-instance deployment. Multi-instance deployment requires replacing both with PostgreSQL and object storage (e.g. S3).

**C-5 No authentication** — The API has no authentication layer in the current implementation. All endpoints are publicly accessible on the configured port.

**C-6 Static knowledge base** — Scoring rules and regulatory thresholds are hardcoded. Changes to RBI norms or other regulations require code updates to `scoring.py`.

---

## Out of Scope

The following are explicitly not requirements for the current version:

- OCR for scanned / image-based PDFs
- Multi-user authentication and role-based access control
- Multi-tenancy (separate data isolation per bank or branch)
- Real-time RBI circular ingestion or automated regulatory updates
- Integration with CIBIL, CRILC, or any external credit bureau
- Multi-currency support
- Batch processing of multiple PDFs in a single request
- Mobile application
- Workflow management (approval queues, comment trails, versioning of analyses)
- Email or notification delivery of CAM reports
- Audit logging for regulatory compliance (changes, approvals, access log)
