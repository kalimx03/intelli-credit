# Intelli-Credit — Design Document

Architecture, module responsibilities, data flow, and the reasoning behind every significant technical choice.

---

## Table of Contents

- [Core Constraint](#core-constraint)
- [System Architecture](#system-architecture)
- [Data Flow](#data-flow)
- [Module Responsibilities](#module-responsibilities)
- [Anti-Hallucination Stack](#anti-hallucination-stack)
- [Scoring Engine Design](#scoring-engine-design)
- [API Design](#api-design)
- [Database Design](#database-design)
- [Frontend Architecture](#frontend-architecture)
- [Key Design Decisions](#key-design-decisions)
- [Known Limitations](#known-limitations)

---

## Core Constraint

**An LLM must never make a credit decision.**

Every design choice follows from this. Credit decisions must be reproducible — a borrower who scores 68.5 today must score 68.5 if the same document is re-analysed in a regulatory audit six months later. LLMs are stochastic. Rules are deterministic.

The architecture enforces a hard boundary:

```
  ┌─────────────── LLM ZONE ────────────────┐    ┌──── RULES ZONE ────┐
  │                                         │    │                    │
  │  PDF text ──→ Claude ──→ raw JSON       │    │  ExtractedFinancials│
  │                              │          │    │        │           │
  │                         Validation ─────────→  Five Cs engine    │
  │                         (5 gates)       │    │  (pure Python)     │
  │                                         │    │        │           │
  └─────────────────────────────────────────┘    │  ScoringResult     │
                                                  └────────────────────┘
```

Nothing crosses from the LLM zone to the rules zone except validated, typed `ExtractedFinancials` objects with known structure and null-safe accessors.

---

## System Architecture

```
┌──────────────────────────────────────────────────────────┐
│                       CLIENT LAYER                        │
│   Next.js 14 — Upload · Dashboard · CAM Download         │
│   lib/api.ts — typed fetch wrappers                      │
└──────────────────────────┬───────────────────────────────┘
                           │ HTTP REST
┌──────────────────────────▼───────────────────────────────┐
│                       API LAYER                           │
│   FastAPI + Uvicorn                                       │
│   Global exception handler → always returns JSON         │
│   Input sanitisation (_validate_uuid, _sanitise_company) │
│                                                           │
│   POST /analyze  GET /analysis/:id  POST /generate-cam   │
│   GET /download-cam  GET /analyses  GET /health           │
└──────┬──────────────────┬────────────────┬───────────────┘
       │                  │                │
  ┌────▼────┐       ┌──────▼──────┐  ┌─────▼──────┐
  │   PDF   │       │     LLM     │  │  Scoring   │
  │Extractor│       │   Service   │  │   Engine   │
  │         │       │  (Claude)   │  │ (28+ rules)│
  └────┬────┘       └──────┬──────┘  └─────▲──────┘
       │                   │               │
       │            ┌──────▼──────┐        │
       │            │  Validation │────────┘
       │            │  (5 gates)  │
       │            └─────────────┘
       │
┌──────▼─────────────────────────────────────────────────┐
│                     DATA LAYER                          │
│   SQLite — analyses table (JSON blobs)                 │
│   Filesystem — CAM PDFs in ./cam_reports/              │
└────────────────────────────────────────────────────────┘
```

---

## Data Flow

### POST /analyze — full pipeline

```
1. main.py
   - Validates file extension (.pdf only)
   - Validates loan_amount_requested ≥ 0
   - Sanitises company_name (strip control chars, cap 200 chars)
   - Generates UUID analysis_id

2. pdf_extractor.extract_text_from_pdf(file_bytes)
   - Rejects empty files and files > 20 MB
   - Opens with pdfplumber
   - Iterates pages (max 60), try/except per page
   - Extracts page text (cap 4000 chars/page) + table rows
   - Deduplicates table rows already present in page text
   - Hard caps total output at 60,000 chars with truncation marker
   - Returns: str

3. llm_service.extract_financials_from_text(document_text)
   - Calls _call_claude(EXTRACTION_SYSTEM_PROMPT, ..., max_tokens=4096)
     - Retry on RateLimitError (exponential backoff: 1s, 2s)
     - Retry on APIStatusError (1s delay)
     - Raises RuntimeError after max retries (→ HTTP 502)
   - Calls _extract_json_from_text(raw):
       Strategy 1: direct json.loads()
       Strategy 2: strip markdown fences
       Strategy 3: regex first {...} block
       Strategy 4: balanced-brace scan from rfind("{")
       On failure: returns _build_null_extraction_skeleton()
   - Calls _sanitise_extraction(parsed):
       Strips unknown keys (only KNOWN_EXTRACTION_KEYS pass through)
       Ensures every entry is {value, confidence, evidence}
   - Returns: Dict[str, Any]

4. main.py
   - If loan_amount_requested was provided and LLM missed it,
     injects it with confidence=1.0, evidence="User provided"

5. validation.validate_and_flag(raw_data)
   Gate 1: each field must be a dict
   Gate 2: numeric fields → float coercion, plausibility bounds check
   Gate 3: boolean fields → strict coercion (true/false/null)
   Gate 4: confidence < 0.6 → flagged (not nulled)
   Gate 5: PAT > Revenue → flagged; EBITDA > Revenue → flagged
   - Returns: (ExtractedFinancials, List[str] warnings)
   - ExtractedFinancials constructor runs Pydantic @model_validator:
     → any value != null with empty evidence → auto-flagged

6. llm_service.analyze_management_insights(primary_insights)
   - Only runs if primary_insights was provided
   - Non-critical: on any failure returns ManagementInsightFlags() (all False)
   - Returns: ManagementInsightFlags

7. scoring.run_scoring(financials, mgmt_flags)
   - Pure Python, no I/O, no LLM calls
   - Calls score_character, score_capacity, score_capital,
     score_collateral, score_conditions
   - Each returns (pillar_score, List[RuleLog])
   - Computes weighted total, risk_band, decision, loan limit, rate
   - Returns: ScoringResult

8. database.save_analysis(...)
   - Writes to SQLite analyses table
   - Non-critical: failure adds a warning, does not crash the request

9. Return full analysis JSON
```

### POST /generate-cam/{id}

```
1. Retrieve analysis row from SQLite
2. Deserialise extracted_financials and scoring_result JSON
3. Build concise summaries (values only, no evidence blobs)
4. llm_service.generate_cam_narratives(company, fin_summary, scoring_summary)
   - On any failure: returns pre-written fallback narratives
5. cam_generator.generate_cam_pdf(...)
   - All values accessed through _ss() / _sf() null-safe helpers
   - All strings XML-escaped for ReportLab safety
   - Generates 10-section A4 PDF with ReportLab
6. Save PDF path to database
7. Return download_url
```

---

## Module Responsibilities

### `main.py`
Single responsibility: HTTP boundary. Validates inputs, orchestrates calls to service modules, maps exceptions to HTTP status codes. Contains no business logic. The global `@app.exception_handler(Exception)` ensures the server never returns an HTML 500 page — every error is JSON.

Two utility functions live here because they're purely about request sanitisation:
- `_validate_uuid(value)` — rejects malformed IDs before they reach the database
- `_sanitise_company_name(name)` — strips control characters, caps at 200 chars

### `models.py`
Defines the typed data contracts. Nothing in the app passes raw dicts between modules — everything is a Pydantic model. Key design choices:

- `ExtractedField.safe_value()` / `safe_confidence()` — null-safe accessors used throughout the scoring engine to eliminate `AttributeError` crashes
- `@field_validator("confidence")` — clamps to [0.0, 1.0] and coerces non-numeric values to 0.0
- `@field_validator("evidence")` — coerces None to `""` and caps at 500 chars
- `@model_validator("flag_missing_evidence")` — the hallucination guard: value without evidence → auto-flagged

### `pdf_extractor.py`
Defensive PDF parsing with four hard limits: 20 MB file size, 60 pages, 4000 chars per page, 60,000 chars total. All four are configurable via module-level constants. Page processing is isolated in try/except — a corrupted page generates a warning and is skipped, not an exception. Table deduplication prevents double-counting values that appear in both freeform text and extracted table cells.

### `llm_service.py`
All Claude API calls live here. Nothing else in the codebase imports `anthropic` directly. Three principles:

1. **Lazy client init** — `_get_client()` creates the Anthropic client on first call, so importing the module never crashes if the API key is missing
2. **Retry with backoff** — `RateLimitError` triggers exponential backoff; `APIStatusError` gets one retry after 1s
3. **Never propagate bad JSON** — `_extract_json_from_text()` tries four strategies; on total failure, `_build_null_extraction_skeleton()` returns a fully-null dict so the pipeline can continue with warnings

`_sanitise_extraction()` strips any keys Claude may have hallucinated that aren't in `KNOWN_EXTRACTION_KEYS`, and ensures every remaining entry has exactly `{value, confidence, evidence}`.

### `validation.py`
The firewall between the LLM zone and the rules zone. Processes the raw dict from `llm_service` into a typed `ExtractedFinancials` through five sequential gates. Key design: fields that fail type coercion are nulled (the scoring rule won't fire), but fields that fail plausibility bounds are flagged and retained (the value may still be correct, just surprising). This preserves information while clearly marking uncertainty.

### `scoring.py`
Pure deterministic Python. No I/O, no network calls, no randomness. `_get(fin, field)` is the only field accessor — a two-liner that returns `None` if the field or its value is absent. Every rule function returns a `(score, List[RuleLog])` tuple. Both triggered and non-triggered rules are logged so the full rule set is visible in the CAM.

Pillar scores are clamped to [0, 100] before weighting. The weighted total is therefore always in [0, 100]. Loan limit and interest rate are computed from the final score and extracted revenue using fixed lookup bands.

### `cam_generator.py`
ReportLab PDF generation. All external data passes through three helper functions before touching any ReportLab object:
- `_ss(v, n)` — null-safe string, capped at n chars
- `_sf(v)` — null-safe float conversion
- `_sn(v, n)` — narrative string with XML special char stripping and control char removal

This means a None value anywhere in the scoring or financials dicts renders as `"N/A"` or `"Not available."`, not a Python exception in the middle of PDF generation. The 10 sections are assembled into a ReportLab `story` list and built with `SimpleDocTemplate`.

### `database.py`
Thin SQLite wrapper using the stdlib `sqlite3` directly (no ORM overhead for five simple queries). All JSON blobs are serialised/deserialised at this layer. `init_db()` is idempotent (uses `CREATE TABLE IF NOT EXISTS`) so it's safe to call on every startup.

---

## Anti-Hallucination Stack

The six layers are defence-in-depth — each independently catches a different failure mode.

| Failure mode | Layer that catches it |
|---|---|
| Claude invents a revenue figure with no document basis | Layer 1: prompt requires evidence quote |
| Claude returns value without evidence | Layer 2: `@model_validator` auto-flags |
| Claude returns DSCR as a string `"1.38x"` | Layer 3: type coercion nulls it |
| Claude returns `current_ratio: 999` (implausible) | Layer 3: plausibility bounds flag it |
| Claude returns `confidence: 0.3` for a critical field | Layer 3: confidence gate flags it |
| Claude wraps output in ` ```json ``` ` fences | Layer 5: fence-stripping strategy |
| Claude returns prose before the JSON | Layer 5: regex/brace-scan strategies |
| Claude API is down entirely | Layer 6: null skeleton, pipeline continues |

The scoring engine completes this chain by never defaulting to a penalty for missing data. If DSCR is null, the DSCR rules simply don't fire. The score is lower because fewer rules fired positively, but the system never invents a bad DSCR to justify a rejection.

---

## Scoring Engine Design

### Why deterministic rules, not a trained model?

1. **Reproducibility** — regulators require that the same inputs produce the same output. ML models don't guarantee this even with the same weights.
2. **Explainability** — every rule has a human-readable name and explanation. The rule log is a complete audit trail that can be shown to a borrower or examiner.
3. **Regulatory alignment** — each rule maps to a specific RBI circular, Tandon Committee guideline, or GST compliance requirement, documented and verifiable.
4. **No training data** — an ML credit model requires thousands of labelled decisions. Deterministic rules can be written from regulatory documents immediately.

### Pillar independence

Pillars are scored independently before weighting. A catastrophic Capacity score (negative PAT, low DSCR) cannot be masked by a perfect Collateral score. This reflects how loan committees actually evaluate credit — a single critical failing in one dimension is not offset by strengths elsewhere, just moderated by the weighting.

### Null-safe rule execution

Every rule function uses the pattern:
```python
v = _get(fin, "dscr")   # returns None if field absent or value is None
if v is not None and v < 1.2:
    score -= 35
    logs.append(_rule("DSCR_CRITICAL", "capacity", True, -35, "DSCR below 1.2x", v))
else:
    logs.append(_rule("DSCR_CRITICAL", "capacity", False, 0, "DSCR not critical or not available", v))
```

Non-triggered rules are still logged. This means the full rule set appears in every CAM, not just the triggered rules — giving the analyst visibility into what was checked.

### Collateral scoring

Collateral uses a base-minus-LTV-penalty approach rather than additive deductions. This reflects how banks think about collateral: the coverage ratio is the primary signal. A borrower with 55% LTV has adequate coverage regardless of other factors; a borrower with 95% LTV has almost no buffer regardless of other strengths.

```python
base = 100.0
if ltv > 0.90:    base -= 70
elif ltv > 0.75:  base -= 45
elif ltv > 0.60:  base -= 20
# LTV ≤ 60%: full base score (conservative coverage)

if collateral_type == "immovable": base += 10   # hard asset
if collateral_type == "current":   base -= 10   # soft asset
```

---

## API Design

### REST over GraphQL

The data model is fixed and the clients have well-defined query patterns. REST with clear resource URLs is simpler to debug, document, and test. The Swagger UI at `/docs` is useful for hackathon demos without needing any additional tooling.

### Sync vs async endpoints

`POST /analyze` is `async def` because it calls `await file.read()`. All other endpoints are `def` — they do database lookups and CPU-bound work (ReportLab, scoring) that don't benefit from async execution in a single-process Uvicorn deployment.

### Input sanitisation in main.py, not in service modules

Validation of HTTP-specific concerns (UUID format, file extension, negative loan amount) lives in `main.py` close to the HTTP boundary. Domain validation (field types, plausibility bounds) lives in `validation.py`. This separation means service modules can be tested without instantiating an HTTP request.

### Error response design

Every non-2xx response returns `{"detail": "..."}` — FastAPI's default shape for `HTTPException`. The global `@app.exception_handler(Exception)` catches anything that escapes the try/except blocks and returns the same shape with a generic message. This means the frontend's error handling can always do `err.detail` and get a readable string.

---

## Database Design

### Schema

```sql
CREATE TABLE IF NOT EXISTS analyses (
    id                   TEXT PRIMARY KEY,   -- UUID v4
    company_name         TEXT,
    created_at           TEXT,               -- ISO 8601 UTC
    extracted_financials TEXT,               -- JSON (ExtractedFinancials.model_dump())
    scoring_result       TEXT,               -- JSON (ScoringResult.model_dump())
    validation_warnings  TEXT,               -- JSON array of strings
    cam_pdf_path         TEXT                -- filesystem path, NULL until generated
);
```

Storing Pydantic models as JSON blobs trades query flexibility for simplicity. The app never queries inside the JSON (all filtering is done in Python after retrieval), so the lack of SQL access to nested fields is not a constraint.

### Why SQLite

For a single-instance deployment with low write volume, SQLite eliminates all operational complexity. There's no server to manage, no connection pooling to configure, no credentials to rotate. The database is a single file that can be backed up with `cp`. SQLAlchemy is not used here — five simple queries don't justify the ORM layer. Migrating to PostgreSQL later would require replacing `database.py` only; no other module knows about the persistence layer.

---

## Frontend Architecture

### Pages

**`/` (Upload)**  
PDF drag-and-drop input, company name, optional loan amount override, optional analyst notes. On submit: calls `POST /analyze`, redirects to `/dashboard?id={analysis_id}`.

**`/dashboard?id=...` (Results)**  
On mount: calls `GET /analysis/{id}`. Renders:
- Score gauge and decision banner (colour-coded green/amber/red)
- Five Cs breakdown table with visual progress bars per pillar
- Extracted financials table with confidence bars and evidence strings
- Rule trigger log — triggered rules only, with impact badges
- Validation warnings panel (yellow, collapsible)
- "Generate CAM" button → `POST /generate-cam/{id}`
- "Download CAM" link → `GET /download-cam/{id}`

### State management

No global state library. Each page manages its own state with `useState`. The analysis result from `GET /analysis/{id}` is fetched once on mount — analyses are immutable after creation, so no polling or cache invalidation is needed.

### API client (`lib/api.ts`)

All API calls are centralised in one file. No raw `fetch` calls in page components. This makes error handling consistent and makes the API contract visible in one place. `formatINR()` lives here too — value formatting is a concern of how data is displayed, not how it's fetched, but co-locating it with the API types keeps the dependency clear.

---

## Key Design Decisions

### Pydantic `@model_validator` for evidence enforcement

**Alternative:** Check evidence in `validation.py`.  
**Why model_validator:** The check fires at construction time regardless of which code path created the `ExtractedField`. Putting it in validation would mean it only fires when `validate_and_flag` is called — but fields can also be constructed directly in tests or via the user-provided loan amount injection path. The model validator is unconditional.

### Retry on `RateLimitError` only, not all errors

**Alternative:** Retry all exceptions with backoff.  
**Reason:** Rate limits are transient by definition and should be retried. `APIStatusError` might indicate a bad request (e.g. malformed prompt) — retrying it is wasteful and can hide bugs. Unknown exceptions are not retried because they might indicate a logic error. The distinction is explicit in `_call_claude()`.

### `_sanitise_extraction()` strips unknown keys

**Alternative:** Pass all keys Claude returns to Pydantic (unknown fields are ignored).  
**Reason:** An LLM occasionally hallucinates a key like `"total_revenue_including_gst"`. Passing it to `ExtractedFinancials` would silently discard it. Stripping it explicitly in `_sanitise_extraction()` before Pydantic sees the dict makes the boundary visible and prevents any future code from accidentally reading a hallucinated field.

### CAM narratives use fallback text, not an error response

**Alternative:** Return `500` if Claude fails to generate narratives.  
**Reason:** By the time `/generate-cam` is called, the extraction and scoring are already done and stored. The quantitative sections of the CAM (metrics table, Five Cs, rule log, decision) don't depend on Claude at all. Failing the entire PDF generation because the narrative prose couldn't be generated would lose significant value. The fallback narratives are honest — they say "refer to quantitative sections" rather than inventing prose.

### SQLite instead of PostgreSQL from day one

**Alternative:** PostgreSQL for production-readiness.  
**Reason:** The application runs as a single process on a single instance. SQLite's concurrency model (single writer) is fine for this. Every additional operational component (database server, connection pooling, credentials management) increases the probability of a demo failure at an inconvenient moment. `database.py` is isolated enough that swapping the backend is a one-file change.

### ReportLab instead of headless Chrome PDF

**Alternative:** Render an HTML template and print to PDF with Puppeteer or weasyprint.  
**Reason:** ReportLab is a pure Python library with no external process dependency. Headless Chrome requires a separate binary, additional memory, and process management. In a constrained server environment (t3.medium, systemd service), ReportLab is significantly more reliable. The output is less visually polished than a pixel-perfect HTML render, but it's consistent and crash-resistant.

---

## Known Limitations

**No OCR support**  
pdfplumber cannot extract text from scanned PDFs. The error message ("The document may be image-based") is clear, but the user has no recourse within the app. Adding Tesseract as a fallback would be the highest-impact enhancement.

**Single-instance only**  
SQLite (single writer) and local CAM PDF storage (filesystem) mean the app can only run as one process. Multi-instance deployment would require PostgreSQL and S3 (both are straightforward substitutions, but require configuration).

**No authentication**  
All endpoints are publicly accessible. For a bank deployment this would need API key auth or OAuth 2.0 at the FastAPI middleware layer.

**Knowledge base is static**  
The scoring rules and all regulatory thresholds are hardcoded in `scoring.py`. RBI circulars change. A missed threshold update (e.g. RBI revising the minimum DSCR requirement) would silently produce wrong scores until the code is updated.

**Management insights are qualitative only**  
The `ManagementInsightFlags` from `analyze_management_insights()` are boolean flags derived from analyst-supplied freeform text. They have no document grounding. A dishonest analyst could suppress a `promoter_concern` flag by not mentioning it. The flags affect only the Character pillar (max −23 points combined) and are logged in the rule output.

**CAM PDFs are ephemeral by default**  
Generated PDFs are stored on the local filesystem. If the server restarts or the instance is replaced, the PDFs are lost. The `cam_pdf_path` in the database will point to a non-existent file, which returns a `410 Gone`. Integrating S3 storage (the boto3 dependency is already in the project) is the fix.
