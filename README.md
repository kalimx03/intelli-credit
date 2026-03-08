# Intelli-Credit

**AI-Powered Corporate Credit Decision Engine**

Intelli-Credit automates the full corporate credit appraisal workflow. Upload any financial PDF — balance sheet, audit report, CMA data — and the system extracts structured data using Claude, scores it through a deterministic Five Cs engine grounded in real Indian banking regulations, and produces a professional Credit Appraisal Memorandum PDF in seconds.

> **Core principle:** LLM extracts. Rules decide. Same inputs always produce the same output.

---

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)
- [Five Cs Scoring Engine](#five-cs-scoring-engine)
- [Anti-Hallucination Architecture](#anti-hallucination-architecture)
- [Environment Variables](#environment-variables)
- [Tech Stack](#tech-stack)
- [Demo Checklist](#demo-checklist)

---

## Features

| | |
|---|---|
| **PDF Intelligence** | Parses any corporate financial document up to 20 MB / 60 pages. Per-page isolation means one corrupt page never aborts the run. |
| **AI Extraction** | Claude Sonnet 4 extracts 22 structured fields. Every field carries a `confidence` score (0–1) and an `evidence` quote from the document. No quote → null returned, never a guess. |
| **Deterministic Scoring** | 28+ pure Python rules across the Five Cs (Character, Capacity, Capital, Collateral, Conditions). Zero LLM involvement in the score path. |
| **Explainable Decisions** | Every triggered rule is logged with its impact, raw value, and plain-English explanation. The full rule log is included in the CAM PDF. |
| **CAM Report** | One-click 10-section professional Credit Appraisal Memorandum PDF generated server-side with ReportLab. |
| **Indian Regulatory Context** | Scoring rules and compliance signals are mapped directly to RBI DSCR norms, GST 2A/3B reconciliation, MCA filing obligations, and Tandon Committee working capital norms. |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- An Anthropic API key — get one at [console.anthropic.com](https://console.anthropic.com)

### 1. Backend

```bash
cd backend
pip install -r requirements.txt

# Copy and fill in your API key
cp ../.env.example .env
# Edit .env → set CLAUDE_API_KEY=sk-ant-...

uvicorn main:app --reload --port 8000
```

The API starts at `http://localhost:8000`.  
Interactive docs at `http://localhost:8000/docs`.

### 2. Frontend

```bash
cd frontend
npm install

echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

npm run dev
```

Frontend starts at `http://localhost:3000`.

### 3. Verify

```bash
# Health check
curl http://localhost:8000/health
# → {"status":"ok","claude_api_key_configured":true}

# Quick analysis test (replace with any real PDF)
curl -X POST http://localhost:8000/analyze \
  -F "file=@sample.pdf" \
  -F "company_name=Acme Industries Ltd" \
  -F "loan_amount_requested=50000000"
```

---

## Project Structure

```
intelli-credit/
├── .env.example
├── README.md
├── DESIGN.md
├── REQUIREMENTS.md
│
├── backend/
│   ├── requirements.txt
│   ├── main.py              # FastAPI app, all endpoints, global error handler
│   ├── models.py            # Pydantic models with hallucination-guard validators
│   ├── prompts.py           # All Claude system prompts (extraction, CAM, chat)
│   ├── pdf_extractor.py     # PDF parsing with hard safety limits
│   ├── llm_service.py       # Claude API calls, 4-strategy JSON recovery, fallbacks
│   ├── validation.py        # 5-gate validation layer before scoring
│   ├── scoring.py           # Deterministic Five Cs scoring engine (28+ rules)
│   ├── cam_generator.py     # ReportLab 10-section CAM PDF generation
│   └── database.py          # SQLite persistence via sqlite3
│
└── frontend/
    ├── package.json
    ├── tsconfig.json
    ├── next.config.js
    ├── lib/
    │   └── api.ts           # Typed API client (fetch-based)
    └── app/
        ├── page.tsx         # Upload form with drag-and-drop
        └── dashboard/
            └── page.tsx     # Results dashboard (Five Cs, rule log, CAM download)
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Root — returns version string |
| `GET` | `/health` | Liveness check, confirms API key is set |
| `GET` | `/analyses` | List last 20 analyses (id, company, timestamp) |
| `POST` | `/analyze` | Full pipeline: PDF → extract → validate → score |
| `GET` | `/analysis/{id}` | Retrieve a stored analysis by UUID |
| `POST` | `/generate-cam/{id}` | Generate CAM PDF for an existing analysis |
| `GET` | `/download-cam/{id}` | Download the generated CAM PDF |

### POST `/analyze`

**Request:** `multipart/form-data`

| Field | Type | Required | Notes |
|---|---|---|---|
| `file` | PDF | ✅ | Max 20 MB |
| `company_name` | string | — | Defaults to `"Unknown Company"` |
| `primary_insights` | string | — | Analyst notes on management quality |
| `loan_amount_requested` | float | — | Overrides value if not found in document |

**Response:**
```json
{
  "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
  "company_name": "Acme Industries Ltd",
  "extracted_financials": {
    "revenue":        { "value": 120000000, "confidence": 0.94, "evidence": "Revenue: Rs 12 Cr", "flagged": false },
    "dscr":           { "value": 1.38,      "confidence": 0.87, "evidence": "DSCR: 1.38x",       "flagged": false },
    "gst_mismatch":   { "value": false,     "confidence": 0.91, "evidence": "No mismatch noted",  "flagged": false }
  },
  "scoring_result": {
    "final_score": 68.5,
    "risk_band": "Moderate",
    "decision": "Conditional Approval",
    "suggested_loan_limit": 30000000,
    "suggested_interest_rate": 10.5,
    "five_cs": {
      "character": 80.0, "capacity": 62.0, "capital": 70.0,
      "collateral": 65.0, "conditions": 75.0, "weighted_total": 68.5
    },
    "rule_log": [
      {
        "rule_name": "DSCR_MARGINAL",
        "category": "capacity",
        "triggered": true,
        "impact": -15.0,
        "explanation": "DSCR 1.38x is between 1.2x–1.5x — marginal debt coverage.",
        "raw_value": 1.38
      }
    ]
  },
  "validation_warnings": [],
  "timestamp": "2025-03-08T10:30:00Z"
}
```

### Error responses

All errors follow a consistent shape:
```json
{ "detail": "Human-readable description of what went wrong" }
```

| Status | When |
|--------|------|
| `400` | Wrong file type, invalid UUID, negative loan amount |
| `404` | Analysis ID not found |
| `410` | CAM PDF was generated but file is no longer on disk |
| `422` | PDF is empty, unreadable, or contains no extractable text |
| `500` | Scoring engine or PDF generation error |
| `502` | Claude API unreachable after retries |

---

## Five Cs Scoring Engine

The scoring engine is pure deterministic Python. Claude's output never enters the scoring path — only validated, typed `ExtractedFinancials` objects do.

### Weights

| Pillar | Weight | What it measures |
|--------|--------|-----------------|
| Character | 25% | Auditor opinion, litigation, RPTs, years in business, promoter track record |
| Capacity | 30% | DSCR, ICR, EBITDA margin, PAT sign |
| Capital | 20% | D/E ratio, current ratio, net worth sign, contingent liabilities |
| Collateral | 15% | LTV ratio, collateral type (immovable vs current assets) |
| Conditions | 10% | GST compliance, MCA filings, RBI risk classification, sector headwinds |

### Rules quick-reference

**Capacity (weight 30%)**

| Rule | Trigger | Impact |
|------|---------|--------|
| `DSCR_CRITICAL` | DSCR < 1.2x | −35 |
| `ICR_CRITICAL` | ICR < 1.5x | −25 |
| `EBITDA_WEAK` | EBITDA margin < 8% | −20 |
| `NEGATIVE_PAT` | PAT < 0 | −20 |
| `DSCR_MARGINAL` | DSCR 1.2–1.5x | −15 |
| `ICR_MARGINAL` | ICR 1.5–3.0x | −10 |
| `EBITDA_MARGINAL` | EBITDA margin 8–15% | −10 |

**Capital (weight 20%)**

| Rule | Trigger | Impact |
|------|---------|--------|
| `NEGATIVE_NET_WORTH` | Net worth < 0 | −30 |
| `HIGH_LEVERAGE` | D/E > 4x | −30 |
| `CURRENT_RATIO_CRITICAL` | Current ratio < 1.0x | −25 |
| `CONTINGENT_LIAB` | Contingent liab > 50% net worth | −15 |
| `MODERATE_LEVERAGE` | D/E 2–4x | −15 |
| `CURRENT_RATIO_WEAK` | Current ratio 1.0–1.5x | −10 |

**Character (weight 25%)**

| Rule | Trigger | Impact |
|------|---------|--------|
| `AUDITOR_QUALIFICATION` | Qualified/adverse opinion | −20 |
| `LITIGATION_PENDING` | Active litigation | −15 |
| `PROMOTER_CONCERN` | Integrity concerns in notes | −15 |
| `YEARS_IN_OP_LOW` | Business < 5 years | −15 |
| `RPT` | Related party transactions | −10 |
| `YEARS_IN_OP_MODERATE` | Business 5–10 years | −5 |
| `SUCCESSION_RISK` | Single-promoter dependence | −8 |
| `MGMT_POSITIVE` | Strong management noted | +5 |

**Collateral (weight 15%)**

| Rule | Trigger | Impact |
|------|---------|--------|
| `LTV_CRITICAL` | LTV > 90% | −70 |
| `LTV_HIGH` | LTV 75–90% | −45 |
| `LTV_MODERATE` | LTV 60–75% | −20 |
| `COLLATERAL_IMMOVABLE` | Immovable property | +10 |
| `COLLATERAL_CURRENT` | Current assets only | −10 |

**Conditions (weight 10%)**

| Rule | Trigger | Impact |
|------|---------|--------|
| `RBI_RISK` | RBI regulatory risk / NPA flag | −25 |
| `GST_MISMATCH` | GST 2A/3B mismatch | −20 |
| `SECTOR_HEADWIND` | Sector downturn flagged | −15 |
| `MCA_DEFAULT` | MCA filing default | −10 |
| `CONCENTRATION_RISK` | Revenue concentration | −10 |

### Decision thresholds

| Final score | Decision | Loan limit | Rate |
|-------------|----------|------------|------|
| ≥ 75 | **Approve** | Revenue × 0.40 | 8.5% |
| 50–74 | **Conditional Approval** | Revenue × 0.25 | 10.5% |
| < 50 | **Reject** | Revenue × 0.10 | 13.5% |

Null fields do not trigger rules. A missing DSCR means the DSCR rules simply don't fire — the engine never defaults to a penalty for missing data.

---

## Anti-Hallucination Architecture

Six independent layers prevent the LLM from influencing credit decisions with invented data.

**Layer 1 — Evidence-bound extraction**  
The extraction system prompt requires Claude to supply an exact document quote for every non-null value. No quote → null is returned. The prompt is explicit: *"NEVER fabricate or infer values not explicitly stated."*

**Layer 2 — Pydantic model validator**  
`ExtractedField` has a `@model_validator` that auto-flags any field where `value is not None` but `evidence.strip()` is empty. This fires before any data reaches the scoring layer.

```python
@model_validator(mode="after")
def flag_missing_evidence(self) -> "ExtractedField":
    if self.value is not None and not self.evidence.strip():
        self.flagged = True
        self.flag_reason = "No evidence for non-null value — hallucination risk"
    return self
```

**Layer 3 — 5-gate validation (`validation.py`)**  
Before scoring: type coercion → plausibility bounds → non-negative enforcement → confidence threshold (≥ 0.6) → cross-field consistency (PAT > Revenue is flagged). Fields that fail coercion are nulled; fields that fail plausibility are flagged but retained.

**Layer 4 — Scoring engine isolation**  
The Five Cs engine only receives validated `ExtractedFinancials` objects. Every field access uses `safe_value()` — a null-safe method on the model. All 28+ rule functions are pure Python with zero LLM calls.

**Layer 5 — 4-strategy JSON recovery (`llm_service.py`)**  
Claude occasionally wraps output in markdown fences or prepends text. The parser tries four strategies before failing: direct `json.loads()` → strip code fences → regex first `{...}` block → balanced-brace scan. On total failure, a null skeleton is returned rather than crashing.

**Layer 6 — Null skeleton fallback**  
If all JSON recovery strategies fail, `_build_null_extraction_skeleton()` returns a dict where every field is `{value: null, confidence: 0.0, evidence: ""}`. Validation and scoring proceed normally, generating warnings. The app never returns a 500 because of a bad LLM response.

---

## Environment Variables

Copy `.env.example` to `.env`:

```bash
# Required
CLAUDE_API_KEY=sk-ant-...

# Optional — database path (defaults to ./intelli_credit.db)
DB_PATH=./intelli_credit.db

# Optional — CAM PDF output directory (defaults to ./cam_reports/)
CAM_OUTPUT_DIR=./cam_reports
```

The frontend reads one variable:
```bash
# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Tech Stack

**Backend**

| Package | Version | Role |
|---------|---------|------|
| FastAPI | 0.111.0 | REST API framework |
| Uvicorn | 0.29.0 | ASGI server |
| anthropic | 0.25.0 | Claude API client |
| pdfplumber | 0.11.0 | PDF text and table extraction |
| Pydantic | 2.7.1 | Data validation and models |
| ReportLab | 4.2.0 | CAM PDF generation |
| SQLAlchemy / SQLite | 2.0.30 | Analysis persistence |
| python-dotenv | 1.0.1 | Environment variable loading |
| python-multipart | 0.0.9 | Multipart form file uploads |

**Frontend**

| Package | Version | Role |
|---------|---------|------|
| Next.js | 14.2.3 | React framework |
| React | 18.3.1 | UI library |
| Axios / fetch | 1.7.2 | API client |
| Lucide React | 0.379.0 | Icon system |
| TypeScript | — | Type safety |
| Tailwind CSS | — | Utility styling |

**LLM**

| | |
|---|---|
| Model | `claude-sonnet-4-20250514` |
| Extraction | Up to 4096 output tokens |
| CAM narratives | Up to 4096 output tokens |
| Management analysis | Up to 1024 output tokens |

---

## Demo Checklist

Run through this before any live presentation.

**Pre-demo (5 min before)**
- [ ] `GET /health` returns `{"status":"ok","claude_api_key_configured":true}`
- [ ] Frontend loads at your URL without console errors
- [ ] Upload a known-good PDF and confirm it scores correctly
- [ ] "Generate CAM" button produces a downloadable PDF

**Edge cases to have ready**
- [ ] Non-PDF file upload → expect `400` with a clear message
- [ ] Oversized PDF (> 20 MB) → expect `422` with size message
- [ ] Scanned-only PDF → expect `422` "No extractable text"
- [ ] No `CLAUDE_API_KEY` set → `GET /health` shows `claude_api_key_configured: false`

**Known-good test scenarios**

| Scenario | Key signals | Expected decision |
|----------|------------|-------------------|
| Strong borrower | DSCR 1.8x, D/E 0.8x, clean audit | Approve |
| Marginal borrower | DSCR 1.3x, D/E 2.5x, no issues | Conditional Approval |
| Weak borrower | Negative PAT, D/E 5x, GST mismatch | Reject |

**If things break mid-demo**
- Backend crashed → `uvicorn main:app --reload --port 8000`
- Slow Claude response → check `CLAUDE_API_KEY` is valid, network is up
- CAM PDF missing from disk → re-run `POST /generate-cam/{id}`

---

## Indian Regulatory Context

Intelli-Credit models compliance signals specific to Indian corporate lending.

**GST 2A/3B Mismatch** — GSTR-2A records purchases as reported by suppliers; GSTR-3B is the borrower's self-declaration. A discrepancy of more than 5–10% signals ITC fraud or revenue suppression and triggers a −20 penalty.

**MCA Filing Default** — Companies Act 2013 requires MGT-7 (annual return) and AOC-4 (financial statements) within 60 days of the AGM. Multi-year default can result in director disqualification under Section 164(2). Triggers −10 penalty.

**RBI DSCR Norms** — Per RBI circular DBOD.BP.BC.No.110/21.04.048/2013-14, banks must monitor DSCR quarterly for exposures above ₹5 crore. DSCR below 1.0x for two consecutive quarters triggers SMA-1 classification. The engine's DSCR_CRITICAL rule (−35 at < 1.2x) is more conservative than the regulatory floor.

**Tandon Committee Working Capital** — MPBF (Maximum Permissible Bank Finance) norms govern working capital limits. A current ratio below 1.33x signals inadequate net working capital margin under Method 2 of the Tandon Committee framework.

**Contingent Liabilities** — Off-balance-sheet exposures exceeding 50% of net worth are flagged per standard credit appraisal practice. Common triggers: bank guarantees, disputed tax liabilities, pending arbitration awards.

---

## License

MIT — see `LICENSE`.
